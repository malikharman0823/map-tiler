from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from functions.raster_transform.algorithm import (
    extract_raster_corners_wgs84,
    polygon_is_simple_and_convex,
    warp_raster_to_corners,
)
from functions.raster_transform.function import (
    get_raster_transform_status,
    handle_raster_transform,
)
from functions.raster_transform.request import (
    CoordinatePoint,
    RasterCorners,
    RasterTransformRequest,
)
from models.dataset import Dataset
from storage.session import SessionRepository


class TestRasterTransform:
    @pytest.fixture(autouse=True)
    def setup_method_fixture(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.session_id = f"test_sess_{uuid4().hex}"
        self.db = SessionRepository(session_id=self.session_id, session_dir=self.dir_path)
        yield
        self.temp_dir.cleanup()

    def create_test_geotiff(self, path: Path, width=20, height=20) -> None:
        """Create a simple georeferenced RGBA GeoTIFF in EPSG:3857."""
        path.parent.mkdir(parents=True, exist_ok=True)
        # Web Mercator bounds around 10 to 11 lng, 20 to 21 lat
        transform = from_bounds(1113194.0, 2273030.0, 1224514.0, 2391600.0, width, height)
        data = np.full((4, height, width), 200, dtype=np.uint8)
        data[3, :, :] = 255  # alpha
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=4,
            dtype="uint8",
            crs=CRS.from_epsg(3857),
            transform=transform,
        ) as dst:
            dst.write(data)

    def test_convex_polygon_validation(self):
        # Valid rectangle
        corners = RasterCorners(
            top_left=CoordinatePoint(longitude=10.0, latitude=21.0),
            top_right=CoordinatePoint(longitude=11.0, latitude=21.0),
            bottom_right=CoordinatePoint(longitude=11.0, latitude=20.0),
            bottom_left=CoordinatePoint(longitude=10.0, latitude=20.0),
        )
        assert polygon_is_simple_and_convex(corners) is True

        # Degenerate / self-intersecting butterfly
        butterfly = RasterCorners(
            top_left=CoordinatePoint(longitude=10.0, latitude=21.0),
            top_right=CoordinatePoint(longitude=11.0, latitude=20.0),
            bottom_right=CoordinatePoint(longitude=11.0, latitude=21.0),
            bottom_left=CoordinatePoint(longitude=10.0, latitude=20.0),
        )
        assert polygon_is_simple_and_convex(butterfly) is False

    def test_extract_and_warp(self):
        src_path = self.dir_path / "source.tif"
        self.create_test_geotiff(src_path)

        corners, bounds, w, h = extract_raster_corners_wgs84(src_path)
        assert w == 20
        assert h == 20
        assert abs(corners.top_left.longitude - 10.0) < 0.01
        assert abs(corners.top_left.latitude - 21.0) < 0.01

        # Warp by translating 0.5 degrees east
        translated = RasterCorners(
            top_left=CoordinatePoint(longitude=corners.top_left.longitude + 0.5, latitude=corners.top_left.latitude),
            top_right=CoordinatePoint(longitude=corners.top_right.longitude + 0.5, latitude=corners.top_right.latitude),
            bottom_right=CoordinatePoint(longitude=corners.bottom_right.longitude + 0.5, latitude=corners.bottom_right.latitude),
            bottom_left=CoordinatePoint(longitude=corners.bottom_left.longitude + 0.5, latitude=corners.bottom_left.latitude),
        )
        dst_path = self.dir_path / "warped.tif"
        res = warp_raster_to_corners(src_path, dst_path, translated, "EPSG:3857")
        assert dst_path.is_file()
        assert res["width"] > 0
        assert res["height"] > 0
        assert res["bounds"][0] >= 10.4

    def test_workflow_status_preview_apply_undo_redo_reset(self):
        dataset_id = uuid4()
        p_dir = self.db.get_processed_dir(dataset_id)
        p_dir.mkdir(parents=True, exist_ok=True)
        tif_path = p_dir / "processed.tif"
        self.create_test_geotiff(tif_path)

        dataset = Dataset(
            id=dataset_id,
            filename="floorplan.tif",
            file_size=tif_path.stat().st_size,
            content_type="image/tiff",
            file_hash="test_hash_123",
            storage_path=tif_path.as_posix(),
            extracted_metadata={"format": "tiff"},
            georeference_status="completed",
            process_status="completed",
            tile_status="completed",
        )
        self.db.insert_dataset(dataset)

        # 1. Check status
        status_resp = get_raster_transform_status(dataset_id, self.db)
        assert status_resp.data.status in ("not_configured", "completed")
        assert status_resp.data.corners is not None
        orig_corners = status_resp.data.corners

        # 2. Preview action
        moved_corners = RasterCorners(
            top_left=CoordinatePoint(longitude=orig_corners.top_left.longitude + 0.1, latitude=orig_corners.top_left.latitude + 0.1),
            top_right=CoordinatePoint(longitude=orig_corners.top_right.longitude + 0.1, latitude=orig_corners.top_right.latitude + 0.1),
            bottom_right=CoordinatePoint(longitude=orig_corners.bottom_right.longitude + 0.1, latitude=orig_corners.bottom_right.latitude + 0.1),
            bottom_left=CoordinatePoint(longitude=orig_corners.bottom_left.longitude + 0.1, latitude=orig_corners.bottom_left.latitude + 0.1),
        )
        preview_req = RasterTransformRequest(action="preview", corners=moved_corners)
        preview_resp = handle_raster_transform(dataset_id, preview_req, self.db)
        assert preview_resp.data.status == "preview"
        assert preview_resp.data.corners is not None
        assert preview_resp.data.corners.top_left.longitude == moved_corners.top_left.longitude

        # 3. Apply action
        apply_req = RasterTransformRequest(action="apply", corners=moved_corners, mode="move")
        apply_resp = handle_raster_transform(dataset_id, apply_req, self.db)
        assert apply_resp.data.status == "completed"
        assert apply_resp.data.can_undo is True
        assert (p_dir / "processed.tif").is_file()

        # 4. Undo action
        undo_req = RasterTransformRequest(action="undo")
        undo_resp = handle_raster_transform(dataset_id, undo_req, self.db)
        assert undo_resp.data.status == "undone"
        assert undo_resp.data.can_redo is True

        # 5. Redo action
        redo_req = RasterTransformRequest(action="redo")
        redo_resp = handle_raster_transform(dataset_id, redo_req, self.db)
        assert redo_resp.data.status == "redone"
        assert redo_resp.data.can_undo is True

        # 6. Reset action
        reset_req = RasterTransformRequest(action="reset")
        reset_resp = handle_raster_transform(dataset_id, reset_req, self.db)
        assert reset_resp.data.status == "reset"
        assert reset_resp.data.can_undo is False
