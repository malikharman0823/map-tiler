import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_bounds

from storage.repository import SessionRepository
from storage.session import remove_directory
from functions.formats.function import build_mbtiles
from functions.map_projects import export as project_export
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError


class FolderTileExportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_backend_directory = project_export.BACKEND_DIRECTORY
        project_export.BACKEND_DIRECTORY = self.root
        self.db = SessionRepository(
            session_id="test_folder_tile_export",
            session_dir=self.root / "session",
        )

        source = self.root / "storage" / "uploads" / "source.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source")
        self.dataset = Dataset(
            filename="New Adam.png",
            file_size=source.stat().st_size,
            content_type="image/png",
            file_hash="source-hash",
            storage_path=source.relative_to(self.root).as_posix(),
            extracted_metadata={"format": "png", "category": "raster"},
        )
        processed = self.root / "storage" / "processed" / str(self.dataset.id) / "processed.tif"
        processed.parent.mkdir(parents=True)
        with rasterio.open(
            processed,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_bounds(86.19514353, 22.79400822, 86.20217385, 22.79928916, 2, 2),
        ) as destination:
            destination.write(numpy.ones((1, 2, 2), dtype="uint8"))

        tile_root = self.root / "storage" / "tiles" / str(self.dataset.id)
        for zoom, column, row in ((15, 24229, 13824), (16, 48459, 27648)):
            tile = tile_root / str(zoom) / str(column) / f"{row}.png"
            tile.parent.mkdir(parents=True, exist_ok=True)
            tile.write_bytes(b"png-tile")

        self.dataset.processed_path = processed.relative_to(self.root).as_posix()
        self.dataset.process_status = "completed"
        self.dataset.tile_path = tile_root.relative_to(self.root).as_posix()
        self.dataset.tile_min_zoom = 15
        self.dataset.tile_max_zoom = 16
        self.dataset.tile_status = "completed"
        self.db.insert_dataset(self.dataset)
        self.project = MapProject(
            name="New Adam",
            dataset_id=self.dataset.id,
            configuration={
                "opacity": 0.7,
                "layerVisibility": {"dataset": True, "iconPoints": True},
            },
        )
        self.db.insert_map_project(self.project)
        self.db.insert_control_point(
            ControlPoint(
                dataset_id=self.dataset.id,
                image_x=12.5,
                image_y=34.5,
                longitude=86.2,
                latitude=22.79,
            )
        )
        self.db.insert_icon_point(
            IconPoint(
                dataset_id=self.dataset.id,
                longitude=86.201,
                latitude=22.795,
                icon_key="marker",
                description="Saved user point",
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        project_export.BACKEND_DIRECTORY = self.original_backend_directory
        remove_directory(self.root)
        self.temporary.cleanup()

    async def test_export_contains_reference_viewers_metadata_and_xyz_tiles(self) -> None:
        response = project_export.export_project(self.dataset.id, self.db)
        package_path = Path(response.path)
        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("New_Adam.zip", response.headers["content-disposition"])

        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            metadata = json.loads(archive.read("metadata.json"))
            mapstudio = json.loads(archive.read("mapstudio.json"))
            leaflet = archive.read("leaflet.html").decode("utf-8")
            index = archive.read("index.html").decode("utf-8")

        self.assertEqual(
            names,
            {
                "metadata.json",
                "mapstudio.json",
                "index.html",
                "leaflet.html",
                "openlayers.html",
                "googlemaps.html",
                "assets/source/source.png",
                "15/24229/13824.png",
                "16/48459/27648.png",
            },
        )
        self.assertEqual(metadata["name"], "New Adam")
        self.assertEqual(metadata["format"], "png")
        self.assertEqual(metadata["profile"], "mercator")
        self.assertEqual(metadata["minzoom"], "15")
        self.assertEqual(metadata["maxzoom"], "16")
        self.assertEqual(
            metadata["bounds"],
            [86.19514353, 22.79400822, 86.20217385, 22.79928916],
        )
        self.assertIn("{z}/{x}/{y}.png", leaflet)
        self.assertIn('"type": "overlay"', index)
        self.assertEqual(mapstudio["format"], "mapstudio-folder")
        self.assertEqual(mapstudio["version"], 1)
        self.assertEqual(mapstudio["project"]["configuration"], self.project.configuration)
        self.assertEqual(mapstudio["dataset"]["source_asset"], "assets/source/source.png")
        self.assertEqual(mapstudio["control_points"][0]["image_x"], 12.5)
        self.assertEqual(mapstudio["icon_points"][0]["description"], "Saved user point")
        self.assertFalse(any(name.endswith((".mtmap", ".mbtiles", ".tif", ".gpkg", ".geojson")) for name in names))

        await response.background()
        self.assertFalse(package_path.exists())

    async def test_raster_mbtiles_is_extracted_to_xyz_png_folder(self) -> None:
        source_tiles = self.root / "mbtiles-source"
        for row in (0, 1):
            tile = source_tiles / "1" / "0" / f"{row}.png"
            tile.parent.mkdir(parents=True, exist_ok=True)
            tile.write_bytes(f"png-{row}".encode())
        mbtiles_path = self.root / "storage" / "uploads" / str(self.dataset.id) / "source.mbtiles"
        mbtiles_path.parent.mkdir(parents=True, exist_ok=True)
        build_mbtiles(source_tiles, mbtiles_path, name="New Adam")

        self.dataset.filename = "source.mbtiles"
        self.dataset.storage_path = mbtiles_path.relative_to(self.root).as_posix()
        self.dataset.extracted_metadata = {
            "format": "mbtiles",
            "category": "tiles",
            "tile_format": "png",
            "bounds": None,
        }
        self.dataset.processed_path = None
        self.dataset.process_status = "not_started"
        self.dataset.tile_path = None
        self.dataset.tile_min_zoom = None
        self.dataset.tile_max_zoom = None
        self.dataset.tile_status = "not_started"
        self.db.save_dataset(self.dataset)
        self.db.commit()

        response = project_export.export_project(self.dataset.id, self.db)
        package_path = Path(response.path)
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            metadata = json.loads(archive.read("metadata.json"))
            mapstudio = json.loads(archive.read("mapstudio.json"))
            self.assertEqual(archive.read("1/0/0.png"), b"png-0")
            self.assertEqual(archive.read("1/0/1.png"), b"png-1")

        self.assertIn("1/0/0.png", names)
        self.assertIn("1/0/1.png", names)
        self.assertEqual(metadata["minzoom"], "1")
        self.assertEqual(metadata["maxzoom"], "1")
        self.assertAlmostEqual(metadata["bounds"][0], -180.0)
        self.assertAlmostEqual(metadata["bounds"][2], 0.0)
        self.assertIsNone(mapstudio["dataset"]["source_asset"])
        self.assertFalse(any(name.endswith((".mtmap", ".mbtiles")) for name in names))

        await response.background()
        self.assertFalse(package_path.exists())

    def test_export_rejects_incomplete_or_empty_tile_sets(self) -> None:
        self.dataset.tile_status = "processing"
        self.db.save_dataset(self.dataset)
        self.db.commit()
        with self.assertRaises(ApplicationError) as incomplete:
            project_export.export_project(self.dataset.id, self.db)
        self.assertEqual(incomplete.exception.status_code, 409)
        self.assertEqual(incomplete.exception.code, "TILES_NOT_AVAILABLE")

        self.dataset.tile_status = "completed"
        tile_root = self.root / self.dataset.tile_path
        for tile in tile_root.rglob("*.png"):
            tile.unlink()
        self.db.save_dataset(self.dataset)
        self.db.commit()
        with self.assertRaises(ApplicationError) as empty:
            project_export.export_project(self.dataset.id, self.db)
        self.assertEqual(empty.exception.status_code, 409)
        self.assertEqual(empty.exception.code, "TILES_NOT_AVAILABLE")

    def test_api_registers_only_the_formatless_export_route(self) -> None:
        from main import app

        export_paths = {
            route.path for route in app.routes if "/export" in getattr(route, "path", "")
        }
        self.assertEqual(export_paths, {"/datasets/{dataset_id}/export"})
