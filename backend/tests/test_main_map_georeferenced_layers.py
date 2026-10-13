import tempfile
import unittest
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_bounds

from storage.repository import SessionRepository
from functions.dataset_detail import function as dataset_detail
from functions.dataset_detail.request import DatasetDetailRequest
from functions.georeference.function import mark_georeference_publication_failed
from models.dataset import Dataset
from models.georeference_config import GeoreferenceConfig
from schemas.error import ApplicationError


class MainMapGeoreferencedLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.processed = self.root / "storage" / "processed"
        self.tiles = self.root / "storage" / "tiles"
        self.db = SessionRepository(
            session_id="test_georeferenced_layers",
            session_dir=self.root / "session",
        )

        self.dataset = Dataset(
            filename="building_a.png",
            file_size=100,
            content_type="image/png",
            file_hash="building-a-hash",
            storage_path="storage/uploads/building_a.png",
            extracted_metadata={"width": 100, "height": 50},
            georeferenced_path=(
                f"storage/processed/pending/georeferenced.tif"
            ),
            georeference_status="completed",
            processed_path="storage/processed/pending/processed.tif",
            process_status="completed",
            tile_path="storage/tiles/pending",
            tile_min_zoom=0,
            tile_max_zoom=18,
            tile_status="completed",
        )
        self.dataset.georeferenced_path = (
            f"storage/processed/{self.dataset.id}/georeferenced.tif"
        )
        self.dataset.processed_path = (
            f"storage/processed/{self.dataset.id}/processed.tif"
        )
        self.dataset.tile_path = f"storage/tiles/{self.dataset.id}"
        self.db.insert_dataset(self.dataset)
        self.config = GeoreferenceConfig(
            dataset_id=self.dataset.id,
            transformation="affine",
            source_file_hash=self.dataset.file_hash,
            source_crs=None,
            target_crs="EPSG:4326",
            source_width=100,
            source_height=50,
            control_point_count=4,
            source_coordinate_system={"x": "image_x", "y": "-image_y"},
            transformation_parameters={
                "a": 0.01,
                "b": 0.0,
                "c": 10.0,
                "d": 0.0,
                "e": 0.02,
                "f": 21.0,
            },
            output_path=self.dataset.georeferenced_path,
            output_format="GeoTIFF",
            status="completed",
            is_active=True,
        )
        self.db.save_georeference_config(self.config)
        self.db.commit()

        output = self.root / self.dataset.georeferenced_path
        output.parent.mkdir(parents=True)
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            width=100,
            height=50,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_bounds(10, 20, 11, 21, 100, 50),
        ) as destination:
            destination.write(numpy.ones((1, 50, 100), dtype="uint8"))

        tile = self.root / self.dataset.tile_path / "0" / "0" / "0.png"
        tile.parent.mkdir(parents=True)
        tile.write_bytes(b"png")

        self.original_constants = (
            dataset_detail.BACKEND_DIRECTORY,
            dataset_detail.PROCESSED_DIRECTORY,
            dataset_detail.TILES_DIRECTORY,
        )
        dataset_detail.BACKEND_DIRECTORY = self.root
        dataset_detail.PROCESSED_DIRECTORY = self.processed
        dataset_detail.TILES_DIRECTORY = self.tiles

    def tearDown(self) -> None:
        self.db.close()
        (
            dataset_detail.BACKEND_DIRECTORY,
            dataset_detail.PROCESSED_DIRECTORY,
            dataset_detail.TILES_DIRECTORY,
        ) = self.original_constants
        self.temporary.cleanup()

    def detail(self):
        return dataset_detail.get_dataset_detail(
            DatasetDetailRequest(dataset_id=self.dataset.id), self.db
        ).data

    def test_completed_layer_uses_raster_bounds_and_dataset_identity(self) -> None:
        layer = self.detail().map_layer

        self.assertEqual(layer.name, "building_a")
        self.assertEqual(layer.source_crs, "EPSG:4326")
        self.assertEqual(layer.bounds_crs, "EPSG:4326")
        self.assertAlmostEqual(layer.bounds.min_longitude, 10)
        self.assertAlmostEqual(layer.bounds.min_latitude, 20)
        self.assertAlmostEqual(layer.bounds.max_longitude, 11)
        self.assertAlmostEqual(layer.bounds.max_latitude, 21)
        self.assertEqual(layer.tile_min_zoom, 0)
        self.assertEqual(layer.tile_max_zoom, 18)
        self.assertEqual(
            layer.tile_url_template,
            f"/datasets/{self.dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
        )

    def test_pending_configuration_is_not_exposed(self) -> None:
        self.config.status = "pending"
        self.db.save_georeference_config(self.config)
        self.db.commit()

        self.assertIsNone(self.detail().map_layer)

    def test_missing_raster_returns_structured_error(self) -> None:
        (self.root / self.dataset.georeferenced_path).unlink()

        with self.assertRaises(ApplicationError) as raised:
            self.detail()
        self.assertEqual(raised.exception.code, "RASTER_OUTPUT_NOT_FOUND")
        self.assertNotIn(str(self.root), raised.exception.details)

    def test_missing_tiles_returns_structured_error(self) -> None:
        (self.root / self.dataset.tile_path / "0" / "0" / "0.png").unlink()

        with self.assertRaises(ApplicationError) as raised:
            self.detail()
        self.assertEqual(raised.exception.code, "TILE_SOURCE_NOT_FOUND")
        self.assertNotIn(str(self.root), raised.exception.details)

    def test_publication_failure_hides_partial_layer(self) -> None:
        mark_georeference_publication_failed(self.dataset.id, self.db)

        failed_dataset = self.db.get_dataset(self.dataset.id)
        failed_config = self.db.get_active_georeference_config(self.dataset.id)
        self.assertEqual(failed_dataset.georeference_status, "failed")
        self.assertEqual(failed_dataset.tile_status, "failed")
        self.assertIsNone(failed_dataset.tile_path)
        self.assertEqual(failed_config.status, "failed")
        self.assertIsNone(self.detail().map_layer)


if __name__ == "__main__":
    unittest.main()
