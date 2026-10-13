import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi import UploadFile

from storage.repository import SessionRepository
from storage.session import remove_directory
from functions.dataset_detail import function as dataset_detail
from functions.dataset_detail.request import DatasetDetailRequest
from functions.map_projects import export as project_export
from functions.map_projects import import_folder
from functions.map_projects import import_func
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError


class FolderProjectRoundTripTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = SessionRepository(
            session_id="test_folder_project_round_trip",
            session_dir=self.root / "session",
        )

        self.original_constants = (
            project_export.BACKEND_DIRECTORY,
            import_folder.BACKEND_DIRECTORY,
            import_folder.UPLOAD_DIRECTORY,
            import_folder.TILES_DIRECTORY,
            import_func.BACKEND_DIRECTORY,
            import_func.UPLOAD_DIRECTORY,
            import_func.TILES_DIRECTORY,
            dataset_detail.BACKEND_DIRECTORY,
            dataset_detail.UPLOAD_DIRECTORY,
            dataset_detail.TILES_DIRECTORY,
        )
        project_export.BACKEND_DIRECTORY = self.root
        import_folder.BACKEND_DIRECTORY = self.root
        import_folder.UPLOAD_DIRECTORY = self.root / "storage" / "uploads"
        import_folder.TILES_DIRECTORY = self.root / "storage" / "tiles"
        import_func.BACKEND_DIRECTORY = self.root
        import_func.UPLOAD_DIRECTORY = self.root / "storage" / "uploads"
        import_func.TILES_DIRECTORY = self.root / "storage" / "tiles"
        dataset_detail.BACKEND_DIRECTORY = self.root
        dataset_detail.UPLOAD_DIRECTORY = self.root / "storage" / "uploads"
        dataset_detail.TILES_DIRECTORY = self.root / "storage" / "tiles"

        self.dataset = Dataset(
            filename="campus.png",
            file_size=12,
            content_type="image/png",
            file_hash="original-source-hash",
            storage_path="pending",
            extracted_metadata={
                "format": "png",
                "category": "raster",
                "bounds": [77.1, 28.5, 77.2, 28.6],
            },
            georeference_status="completed",
            process_status="completed",
            tile_min_zoom=1,
            tile_max_zoom=1,
            tile_status="completed",
        )
        source = self.root / "storage" / "uploads" / str(self.dataset.id) / "campus.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-image")
        tile = self.root / "storage" / "tiles" / str(self.dataset.id) / "1" / "1" / "1.png"
        tile.parent.mkdir(parents=True)
        tile.write_bytes(b"tile-data")
        self.dataset.storage_path = source.relative_to(self.root).as_posix()
        self.dataset.tile_path = tile.parents[2].relative_to(self.root).as_posix()
        self.db.insert_dataset(self.dataset)
        self.project = MapProject(
            name="Campus Project",
            dataset_id=self.dataset.id,
            configuration={
                "opacity": 0.42,
                "layerVisibility": {
                    "basemap": True,
                    "dataset": True,
                    "controlPoints": True,
                    "iconPoints": True,
                },
            },
        )
        self.db.insert_map_project(self.project)
        self.db.insert_control_point(
            ControlPoint(
                dataset_id=self.dataset.id,
                image_x=10,
                image_y=20,
                longitude=77.15,
                latitude=28.55,
            )
        )
        self.db.insert_icon_point(
            IconPoint(
                dataset_id=self.dataset.id,
                longitude=77.16,
                latitude=28.56,
                icon_key="pin",
                description="Main gate",
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        (
            project_export.BACKEND_DIRECTORY,
            import_folder.BACKEND_DIRECTORY,
            import_folder.UPLOAD_DIRECTORY,
            import_folder.TILES_DIRECTORY,
            import_func.BACKEND_DIRECTORY,
            import_func.UPLOAD_DIRECTORY,
            import_func.TILES_DIRECTORY,
            dataset_detail.BACKEND_DIRECTORY,
            dataset_detail.UPLOAD_DIRECTORY,
            dataset_detail.TILES_DIRECTORY,
        ) = self.original_constants
        remove_directory(self.root)
        self.temporary.cleanup()

    async def _exported_files(self) -> dict[str, bytes]:
        response = project_export.export_project(self.dataset.id, self.db)
        package_path = Path(response.path)
        try:
            with zipfile.ZipFile(package_path) as archive:
                return {
                    name: archive.read(name)
                    for name in archive.namelist()
                    if not name.endswith("/")
                }
        finally:
            await response.background()

    @staticmethod
    def _uploads(files: dict[str, bytes]) -> tuple[list[UploadFile], list[str]]:
        names = sorted(files)
        return (
            [UploadFile(filename=Path(name).name, file=io.BytesIO(files[name])) for name in names],
            [f"Campus Project/{name}" for name in names],
        )

    async def test_exported_folder_restores_project_points_source_and_map_layer(self) -> None:
        files = await self._exported_files()
        uploads, paths = self._uploads(files)

        imported = await import_folder.import_project_folder(uploads, paths, self.db)

        self.assertNotEqual(imported.dataset_id, self.dataset.id)
        self.assertEqual(imported.name, "Campus Project")
        self.assertEqual(imported.configuration, self.project.configuration)
        restored = self.db.get_dataset(imported.dataset_id)
        self.assertEqual(restored.extracted_metadata["format"], "mapstudio_folder")
        self.assertEqual(restored.tile_status, "completed")
        self.assertEqual(restored.tile_min_zoom, 1)
        self.assertEqual(restored.tile_max_zoom, 1)
        self.assertEqual((self.root / restored.storage_path).read_bytes(), b"source-image")
        self.assertEqual(
            (self.root / restored.tile_path / "1" / "1" / "1.png").read_bytes(),
            b"tile-data",
        )
        self.assertEqual(len(self.db.list_control_points(imported.dataset_id)), 1)
        restored_icons = self.db.list_icon_points(imported.dataset_id)
        self.assertEqual(len(restored_icons), 1)
        self.assertEqual(restored_icons[0].description, "Main gate")

        detail = dataset_detail.get_dataset_detail(
            DatasetDetailRequest(dataset_id=imported.dataset_id),
            self.db,
        ).data
        self.assertEqual(detail.display_type, "raster")
        self.assertTrue(detail.is_spatial)
        self.assertEqual(detail.map_layer.tile_min_zoom, 1)
        self.assertEqual(detail.map_layer.bounds.min_longitude, 77.1)
        self.assertEqual(
            detail.map_layer.tile_url_template,
            f"/datasets/{imported.dataset_id}/tiles/{{z}}/{{x}}/{{y}}.png",
        )

        duplicate_uploads, duplicate_paths = self._uploads(files)
        duplicate = await import_folder.import_project_folder(
            duplicate_uploads,
            duplicate_paths,
            self.db,
        )
        self.assertEqual(duplicate.dataset_id, imported.dataset_id)

    async def test_exported_zip_restores_a_visible_raster_map_layer(self) -> None:
        response = project_export.export_project(self.dataset.id, self.db)
        try:
            package = Path(response.path).read_bytes()
        finally:
            await response.background()

        imported = await import_func.import_project(
            UploadFile(filename="campus-project.zip", file=io.BytesIO(package)),
            self.db,
        )

        restored = self.db.get_dataset(imported.dataset_id)
        self.assertEqual(restored.extracted_metadata["format"], "mapstudio_folder")
        detail = dataset_detail.get_dataset_detail(
            DatasetDetailRequest(dataset_id=imported.dataset_id),
            self.db,
        ).data
        self.assertIsNotNone(detail.map_layer)
        self.assertEqual(detail.map_layer.tile_min_zoom, 1)

    async def test_legacy_zip_import_with_tiles_remains_visible(self) -> None:
        files = await self._exported_files()
        uploads, paths = self._uploads(files)
        imported = await import_folder.import_project_folder(uploads, paths, self.db)
        restored = self.db.get_dataset(imported.dataset_id)
        restored.extracted_metadata = {
            "format": "png",
            "bounds": [77.1, 28.5, 77.2, 28.6],
            "minzoom": "1",
            "maxzoom": "1",
            "import_package_hash": "legacy-folder-zip",
        }
        restored.georeference_status = "not_started"
        restored.process_status = "not_started"
        self.db.save_dataset(restored)

        detail = dataset_detail.get_dataset_detail(
            DatasetDetailRequest(dataset_id=imported.dataset_id),
            self.db,
        ).data

        self.assertTrue(detail.is_spatial)
        self.assertIsNotNone(detail.map_layer)
        self.assertEqual(detail.map_layer.bounds.max_longitude, 77.2)

    async def test_unsafe_folder_path_is_rejected_without_external_write(self) -> None:
        upload = UploadFile(filename="mapstudio.json", file=io.BytesIO(b"{}"))
        with self.assertRaises(ApplicationError) as raised:
            await import_folder.import_project_folder(
                [upload],
                ["../outside.json"],
                self.db,
            )
        self.assertEqual(raised.exception.code, "UNSAFE_FOLDER_PATH")
        self.assertFalse((self.root / "outside.json").exists())

    async def test_invalid_points_remove_new_managed_directories(self) -> None:
        files = await self._exported_files()
        state = json.loads(files["mapstudio.json"])
        state["control_points"][0]["latitude"] = 200
        files["mapstudio.json"] = json.dumps(state).encode("utf-8")
        uploads, paths = self._uploads(files)
        upload_directories_before = set(import_folder.UPLOAD_DIRECTORY.iterdir())
        tile_directories_before = set(import_folder.TILES_DIRECTORY.iterdir())

        with self.assertRaises(ApplicationError) as raised:
            await import_folder.import_project_folder(uploads, paths, self.db)

        self.assertEqual(raised.exception.code, "INVALID_FOLDER_PROJECT")
        self.assertEqual(set(import_folder.UPLOAD_DIRECTORY.iterdir()), upload_directories_before)
        self.assertEqual(set(import_folder.TILES_DIRECTORY.iterdir()), tile_directories_before)

    def test_api_registers_folder_import_route(self) -> None:
        from main import app

        routes = {
            (route.path, method)
            for route in app.routes
            for method in (getattr(route, "methods", None) or set())
        }
        self.assertIn(("/map-projects/import-folder", "POST"), routes)


if __name__ == "__main__":
    unittest.main()
