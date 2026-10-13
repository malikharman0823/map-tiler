from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image
import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin

from functions.background_removal.algorithm import (
    generate_raster_preview,
    parse_hex_color,
    process_raster_background_removal,
    remove_background_array,
)
from functions.background_removal.function import (
    get_background_removal_status,
    handle_background_removal,
)
from functions.background_removal.request import BackgroundRemovalRequest
from models.dataset import Dataset
from schemas.error import ApplicationError
from storage.repository import SessionRepository


class BackgroundRemovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_bg_removal_"))
        self.session_id = f"test_session_{uuid4().hex}"
        self.session_dir = self.temp_dir / self.session_id
        self.db = SessionRepository(
            session_id=self.session_id,
            session_dir=self.session_dir,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Black-and-white floor plan
    def test_black_and_white_floor_plan(self) -> None:
        h, w = 100, 100
        # White background (255) with black walls (0)
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        img[10:20, 10:90] = 0  # Top wall
        img[80:90, 10:90] = 0  # Bottom wall
        img[10:90, 10:20] = 0  # Left wall
        img[10:90, 80:90] = 0  # Right wall

        bands = [img[:, :, 0], img[:, :, 1], img[:, :, 2]]
        rgba = remove_background_array(bands, target_color=(255, 255, 255), threshold=25, edge_softness=10)

        # Walls should be fully opaque (alpha == 255)
        self.assertTrue(np.all(rgba[3, 10:20, 10:90] == 255))
        # Interior white space should be fully transparent (alpha == 0)
        self.assertTrue(np.all(rgba[3, 30:70, 30:70] == 0))
        # Background exterior should be fully transparent (alpha == 0)
        self.assertTrue(np.all(rgba[3, 0:5, 0:5] == 0))

    # 2. White background with antialiased gray edges
    def test_white_background_with_antialiased_gray_edges(self) -> None:
        h, w = 50, 50
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        # Antialiased diagonal line drawn with OpenCV
        cv2.line(img, (5, 5), (45, 45), (0, 0, 0), 2, cv2.LINE_AA)

        bands = [img[:, :, 0], img[:, :, 1], img[:, :, 2]]
        rgba = remove_background_array(bands, target_color=(255, 255, 255), threshold=20, edge_softness=20)
        alpha = rgba[3]

        # Should have transparent background
        self.assertTrue(np.any(alpha == 0))
        # Should have opaque line core
        self.assertTrue(np.any(alpha == 255))
        # Should have intermediate antialiased alpha values between 0 and 255
        intermediate_pixels = np.sum((alpha > 0) & (alpha < 255))
        self.assertGreater(intermediate_pixels, 0)

    # 3. Grayscale raster (1 band)
    def test_grayscale_raster(self) -> None:
        h, w = 60, 60
        gray = np.full((h, w), 255, dtype=np.uint8)
        gray[15:45, 15:45] = 20  # Dark room outline

        rgba = remove_background_array([gray], target_color=(255, 255, 255), threshold=30, edge_softness=10)
        self.assertEqual(rgba.shape, (4, h, w))
        self.assertTrue(np.all(rgba[3, 15:45, 15:45] == 255))
        self.assertTrue(np.all(rgba[3, 0:10, 0:10] == 0))

    # 4. Raster with an existing alpha channel (4 bands)
    def test_raster_with_existing_alpha_channel(self) -> None:
        h, w = 60, 60
        r = np.full((h, w), 255, dtype=np.uint8)
        g = np.full((h, w), 255, dtype=np.uint8)
        b = np.full((h, w), 255, dtype=np.uint8)
        existing_a = np.full((h, w), 255, dtype=np.uint8)
        # Prior transparent margin in bottom-right
        existing_a[40:, 40:] = 0
        # Draw a black line in the upper area
        r[10:20, :] = 0
        g[10:20, :] = 0
        b[10:20, :] = 0

        rgba = remove_background_array(
            [r, g, b, existing_a],
            target_color=(255, 255, 255),
            threshold=30,
            edge_softness=10,
            existing_alpha=existing_a,
        )
        alpha = rgba[3]
        # Prior transparent margin must remain 0
        self.assertTrue(np.all(alpha[40:, 40:] == 0))
        # Line must be opaque
        self.assertTrue(np.all(alpha[10:20, :30] == 255))

    # 5. Raster with non-white background (e.g. blue blueprint)
    def test_raster_with_non_white_background(self) -> None:
        h, w = 60, 60
        blueprint_blue = (20, 50, 160)
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :] = blueprint_blue
        # White blueprint lines
        img[20:25, :] = (255, 255, 255)

        bands = [img[:, :, 0], img[:, :, 1], img[:, :, 2]]
        rgba = remove_background_array(bands, target_color=blueprint_blue, threshold=30, edge_softness=15)
        alpha = rgba[3]

        # Blueprint blue background becomes transparent
        self.assertTrue(np.all(alpha[0:15, :] == 0))
        # White lines remain opaque
        self.assertTrue(np.all(alpha[20:25, :] == 255))

    # 6. Thin 1-pixel architectural lines preserved
    def test_thin_architectural_lines_preserved(self) -> None:
        h, w = 80, 80
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        # Single pixel horizontal line
        img[30, 10:70] = 0
        # Single pixel vertical line
        img[10:70, 30] = 0

        bands = [img[:, :, 0], img[:, :, 1], img[:, :, 2]]
        rgba = remove_background_array(bands, target_color=(255, 255, 255), threshold=30, edge_softness=10)
        alpha = rgba[3]

        # The exact 1px lines must have alpha 255
        self.assertTrue(np.all(alpha[30, 10:70] == 255))
        self.assertTrue(np.all(alpha[10:70, 30] == 255))
        # Adjacent pixels away from the vertical intersection must be transparent
        self.assertTrue(np.all(alpha[28, 40:70] == 0))
        self.assertTrue(np.all(alpha[32, 40:70] == 0))

    # 7. Georeferenced GeoTIFF (CRS, affine transform, dimensions, bounds unchanged)
    def test_georeferenced_geotiff_preservation(self) -> None:
        h, w = 120, 120
        transform = from_origin(1500000.0, 6500000.0, 0.5, 0.5)
        crs = CRS.from_epsg(3857)
        data = np.full((3, h, w), 255, dtype=np.uint8)
        data[:, 30:50, 30:50] = 10  # Dark building box

        input_tif = self.temp_dir / "input_geotiff.tif"
        output_tif = self.temp_dir / "output_geotiff.tif"

        with rasterio.open(
            input_tif,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=3,
            dtype="uint8",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(data)

        meta = process_raster_background_removal(
            input_path=input_tif,
            output_path=output_tif,
            target_color=(255, 255, 255),
            threshold=30,
            edge_softness=10,
        )

        with rasterio.open(output_tif) as out:
            self.assertEqual(out.crs, crs)
            self.assertEqual(out.transform, transform)
            self.assertEqual(out.width, w)
            self.assertEqual(out.height, h)
            self.assertEqual(out.count, 4)
            self.assertEqual(out.colorinterp[3], ColorInterp.alpha)
            # Check transparency of background and opacity of box
            alpha = out.read(4)
            self.assertTrue(np.all(alpha[30:50, 30:50] == 255))
            self.assertTrue(np.all(alpha[0:15, 0:15] == 0))

    # 8. Invalid parameters and unsupported inputs
    def test_invalid_parameters_and_unsupported_inputs(self) -> None:
        # Invalid hex colors
        with self.assertRaises(ValueError):
            BackgroundRemovalRequest(color="xyz")
        with self.assertRaises(ValueError):
            BackgroundRemovalRequest(color="#12345")
        with self.assertRaises(ValueError):
            BackgroundRemovalRequest(color="#1234567")

        # Threshold out of range
        with self.assertRaises(Exception):
            BackgroundRemovalRequest.model_validate({"threshold": -5})
        with self.assertRaises(Exception):
            BackgroundRemovalRequest.model_validate({"threshold": 300})

        # Missing dataset in DB
        fake_id = uuid4()
        req = BackgroundRemovalRequest(action="status")
        with self.assertRaises(ApplicationError) as ctx:
            handle_background_removal(fake_id, req, self.db)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "DATASET_NOT_FOUND")

    # 9. Large raster within supported limits
    def test_large_raster_processing(self) -> None:
        h, w = 1500, 1500  # 2.25 megapixels
        data = np.full((3, h, w), 255, dtype=np.uint8)
        # Draw some architectural lines
        data[:, 500:510, :] = 0
        data[:, :, 700:710] = 0

        input_tif = self.temp_dir / "large_input.tif"
        output_tif = self.temp_dir / "large_output.tif"
        crs = CRS.from_epsg(3857)
        transform = from_origin(0.0, 0.0, 1.0, 1.0)

        with rasterio.open(
            input_tif,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=3,
            dtype="uint8",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(data)

        process_raster_background_removal(
            input_path=input_tif,
            output_path=output_tif,
            target_color=(255, 255, 255),
            threshold=30,
            edge_softness=10,
        )

        with rasterio.open(output_tif) as out:
            self.assertEqual(out.width, w)
            self.assertEqual(out.height, h)
            self.assertEqual(out.count, 4)
            alpha = out.read(4)
            self.assertTrue(np.all(alpha[500:510, :] == 255))
            self.assertTrue(np.all(alpha[0:50, 0:50] == 0))

    # 10. Enabling, previewing, applying, resetting, and disabling the feature
    def test_workflow_preview_apply_reset(self) -> None:
        dataset_id = uuid4()
        dataset_dir = self.db.get_dataset_dir(dataset_id)
        source_dir = self.db.get_source_dir(dataset_id)
        processed_dir = self.db.get_processed_dir(dataset_id)
        tiles_dir = self.db.get_tiles_dir(dataset_id)
        source_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)
        tiles_dir.mkdir(parents=True, exist_ok=True)

        h, w = 80, 80
        crs = CRS.from_epsg(3857)
        transform = from_origin(10.0, 50.0, 0.1, 0.1)
        data = np.full((3, h, w), 255, dtype=np.uint8)
        data[:, 20:40, 20:40] = 0

        source_file = source_dir / "floor_plan.png"
        Image.fromarray(np.transpose(data, (1, 2, 0))).save(source_file)

        processed_tif = processed_dir / "processed.tif"
        with rasterio.open(
            processed_tif,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=3,
            dtype="uint8",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(data)

        # Create dummy initial tile
        tile_file = tiles_dir / "0" / "0" / "0.png"
        tile_file.parent.mkdir(parents=True, exist_ok=True)
        tile_file.write_bytes(b"dummy_original_tile")

        dataset = Dataset(
            id=dataset_id,
            filename="floor_plan.png",
            file_size=source_file.stat().st_size,
            content_type="image/png",
            file_hash="test_hash",
            storage_path=source_file.as_posix(),
            extracted_metadata={"format": "png"},
            georeferenced_path=processed_tif.as_posix(),
            georeference_status="completed",
            processed_path=processed_tif.as_posix(),
            process_status="completed",
            tile_path=tiles_dir.as_posix(),
            tile_min_zoom=0,
            tile_max_zoom=1,
            tile_status="completed",
        )
        self.db.insert_dataset(dataset)

        # 10a. Check initial status
        status_resp = get_background_removal_status(dataset_id, self.db)
        self.assertFalse(status_resp.data.enabled)
        self.assertEqual(status_resp.data.status, "not_configured")

        # 10b. Preview
        preview_req = BackgroundRemovalRequest(action="preview", color="#ffffff", threshold=30)
        prev_resp = handle_background_removal(dataset_id, preview_req, self.db)
        self.assertEqual(prev_resp.data.status, "preview")
        preview_url = prev_resp.data.preview_data_url
        self.assertIsNotNone(preview_url)
        assert preview_url is not None
        self.assertTrue(preview_url.startswith("data:image/png;base64,"))
        self.assertIsNotNone(prev_resp.data.original_data_url)

        # 10c. Apply
        apply_req = BackgroundRemovalRequest(action="apply", color="#ffffff", threshold=30, edge_softness=10)
        apply_resp = handle_background_removal(dataset_id, apply_req, self.db)
        self.assertTrue(apply_resp.data.enabled)
        self.assertEqual(apply_resp.data.status, "completed")
        self.assertIsNotNone(apply_resp.data.tile_url_template)

        # Verify processed.tif is now 4-band RGBA
        with rasterio.open(processed_tif) as p_out:
            self.assertEqual(p_out.count, 4)
            alpha = p_out.read(4)
            self.assertTrue(np.all(alpha[20:40, 20:40] == 255))
            self.assertTrue(np.all(alpha[0:10, 0:10] == 0))

        # Verify backup exists
        backup_tif = processed_dir / "processed_original.tif"
        self.assertTrue(backup_tif.is_file())
        backup_tiles = processed_dir / "tiles_original"
        self.assertTrue(backup_tiles.is_dir())

        # 10d. Test duplicate processing reuse
        apply_again_resp = handle_background_removal(dataset_id, apply_req, self.db)
        self.assertTrue(apply_again_resp.data.enabled)
        msg = apply_again_resp.data.message
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("already applied", msg)

        # 10e. Reset
        reset_req = BackgroundRemovalRequest(action="reset")
        reset_resp = handle_background_removal(dataset_id, reset_req, self.db)
        self.assertFalse(reset_resp.data.enabled)
        self.assertEqual(reset_resp.data.status, "reset")

        # Verify original processed.tif is restored (3 bands)
        with rasterio.open(processed_tif) as p_restored:
            self.assertEqual(p_restored.count, 3)

        # Verify original tile is restored
        self.assertEqual(tile_file.read_bytes(), b"dummy_original_tile")

    # 11. Temporary output reuse and cleanup
    def test_cleanup_and_isolation(self) -> None:
        dataset_id = uuid4()
        dataset_dir = self.db.get_dataset_dir(dataset_id)
        source_dir = self.db.get_source_dir(dataset_id)
        source_dir.mkdir(parents=True, exist_ok=True)
        source_file = source_dir / "test.png"
        img = Image.new("RGB", (20, 20), color="white")
        img.save(source_file)

        # Preview generation must NOT leave stray files in the filesystem
        orig_count = len(list(self.temp_dir.rglob("*")))
        generate_raster_preview(source_file, target_color=(255, 255, 255), threshold=30)
        new_count = len(list(self.temp_dir.rglob("*")))
        self.assertEqual(orig_count, new_count, "Preview generation must not leak temporary disk files")


if __name__ == "__main__":
    unittest.main()
