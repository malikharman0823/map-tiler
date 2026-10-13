import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from fastapi import UploadFile

from storage.repository import SessionRepository
from functions.formats import function as formats
from functions.map_projects import export as project_export
from functions.map_projects import import_func as project_import
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError


SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "building-1",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]
                ],
            },
            "properties": {"name": "Main block", "level": 2},
        }
    ],
}


class FormatFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_json_structure_detection_and_invalid_coordinates(self) -> None:
        self.assertEqual(formats.classify_json_document(SAMPLE_GEOJSON), "geojson")
        style = {"version": 8, "sources": {}, "layers": []}
        self.assertEqual(formats.classify_json_document(style), "maplibre_style")
        broken = json.loads(json.dumps(SAMPLE_GEOJSON))
        broken["features"][0]["geometry"]["coordinates"][0][0][0] = float("nan")
        with self.assertRaises(ApplicationError) as error:
            formats.validate_geojson(broken)
        self.assertEqual(error.exception.code, "INVALID_GEOJSON")

    def test_wkb_round_trip_preserves_geometry(self) -> None:
        geometry = SAMPLE_GEOJSON["features"][0]["geometry"]
        self.assertEqual(formats.wkb_to_geojson(formats.geojson_to_wkb(geometry)), geometry)

    def test_geopackage_write_read_preserves_attributes(self) -> None:
        destination = self.root / "sample.gpkg"
        formats.write_geojson_to_geopackage(SAMPLE_GEOJSON, destination)
        info = formats.inspect_geopackage(destination)
        preview = formats.geopackage_preview(destination)
        self.assertEqual(info["feature_count"], 1)
        self.assertEqual(preview["geojson"]["features"][0]["properties"]["name"], "Main block")
        self.assertEqual(preview["geojson"]["features"][0]["properties"]["level"], 2)

    def test_mbtiles_build_uses_tms_rows_and_reads_xyz(self) -> None:
        tile_root = self.root / "tiles"
        first = tile_root / "1" / "0" / "0.png"
        second = tile_root / "1" / "0" / "1.png"
        first.parent.mkdir(parents=True)
        first.write_bytes(b"first-png")
        second.write_bytes(b"second-png")
        archive = self.root / "tiles.mbtiles"
        info = formats.build_mbtiles(tile_root, archive, name="Test tiles")
        self.assertEqual(info.tile_count, 2)
        with closing(sqlite3.connect(archive)) as connection:
            rows = connection.execute(
                "SELECT tile_row, tile_data FROM tiles ORDER BY tile_row"
            ).fetchall()
        self.assertEqual(rows, [(0, b"second-png"), (1, b"first-png")])
        data, media_type, compressed = formats.read_mbtiles_tile(archive, 1, 0, 0)
        self.assertEqual(data, b"first-png")
        self.assertEqual(media_type, "image/png")
        self.assertFalse(compressed)


class PortableProjectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.uploads = self.root / "storage" / "uploads"
        self.processed = self.root / "storage" / "processed"
        self.uploads.mkdir(parents=True)
        self.db = SessionRepository(
            session_id="test_portable_project",
            session_dir=self.root / "session",
        )

        self.original_constants = (
            formats.BACKEND_DIRECTORY,
            project_export.BACKEND_DIRECTORY,
            project_import.BACKEND_DIRECTORY,
            project_import.UPLOAD_DIRECTORY,
            project_import.PROCESSED_DIRECTORY,
        )
        formats.BACKEND_DIRECTORY = self.root
        project_export.BACKEND_DIRECTORY = self.root
        project_import.BACKEND_DIRECTORY = self.root
        project_import.UPLOAD_DIRECTORY = self.uploads
        project_import.PROCESSED_DIRECTORY = self.processed

        self.dataset = Dataset(
            filename="source.geojson",
            file_size=0,
            content_type="application/geo+json",
            file_hash="original-source-hash",
            storage_path="",
            extracted_metadata={
                **formats.geojson_metadata(SAMPLE_GEOJSON, 0),
                "format": "geojson",
                "category": "vector",
            },
        )
        source_directory = self.uploads / str(self.dataset.id)
        source_directory.mkdir()
        source = source_directory / self.dataset.filename
        source.write_text(json.dumps(SAMPLE_GEOJSON), encoding="utf-8")
        self.dataset.file_size = source.stat().st_size
        self.dataset.storage_path = source.relative_to(self.root).as_posix()
        self.db.insert_dataset(self.dataset)
        self.project = MapProject(
            name="Campus plan",
            dataset_id=self.dataset.id,
            configuration={"opacity": 0.7, "layerVisibility": {"dataset": True}},
        )
        self.db.insert_map_project(self.project)
        self.db.insert_control_point(
            ControlPoint(
                dataset_id=self.dataset.id,
                image_x=10,
                image_y=20,
                longitude=77.05,
                latitude=12.05,
            )
        )
        self.db.insert_icon_point(
            IconPoint(
                dataset_id=self.dataset.id,
                longitude=77.06,
                latitude=12.06,
                icon_key="marker",
                description="Entrance",
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        (
            formats.BACKEND_DIRECTORY,
            project_export.BACKEND_DIRECTORY,
            project_import.BACKEND_DIRECTORY,
            project_import.UPLOAD_DIRECTORY,
            project_import.PROCESSED_DIRECTORY,
        ) = self.original_constants
        self.temporary.cleanup()

    async def test_mtmap_import_remaps_ids_and_restores_assets(self) -> None:
        source_bytes = (self.root / self.dataset.storage_path).read_bytes()
        project_bytes = json.dumps(
            {
                "schema_version": 1,
                "project": {
                    "id": str(self.project.id),
                    "name": self.project.name,
                    "configuration": self.project.configuration,
                },
                "dataset": {
                    "id": str(self.dataset.id),
                    "filename": self.dataset.filename,
                    "content_type": self.dataset.content_type,
                },
                "control_points": [
                    {
                        "image_x": 10,
                        "image_y": 20,
                        "longitude": 77.05,
                        "latitude": 12.05,
                    }
                ],
                "icon_points": [
                    {
                        "icon_key": "marker",
                        "description": "Entrance",
                        "longitude": 77.06,
                        "latitude": 12.06,
                    }
                ],
            }
        ).encode()
        declarations = [
            {
                "role": "project",
                "path": "project.json",
                "size": len(project_bytes),
                "sha256": hashlib.sha256(project_bytes).hexdigest(),
            },
            {
                "role": "source",
                "path": "data/source.geojson",
                "size": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            },
        ]
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps({"format": "mtmap", "version": 1, "files": declarations}),
            )
            archive.writestr("project.json", project_bytes)
            archive.writestr("data/source.geojson", source_bytes)
        package_bytes = package.getvalue()
        upload = UploadFile(
            filename="campus.mtmap",
            file=io.BytesIO(package_bytes),
        )
        imported = await project_import.import_project(upload, self.db)
        self.assertNotEqual(imported.id, self.project.id)
        self.assertNotEqual(imported.dataset_id, self.dataset.id)
        self.assertEqual(imported.name, self.project.name)
        self.assertEqual(imported.configuration, self.project.configuration)
        imported_dataset = self.db.get_dataset(imported.dataset_id)
        self.assertIsNotNone(imported_dataset)
        self.assertTrue((self.root / imported_dataset.storage_path).is_file())
        self.assertEqual(len(self.db.list_control_points(imported.dataset_id)), 1)
        self.assertEqual(len(self.db.list_icon_points(imported.dataset_id)), 1)
        duplicate = await project_import.import_project(
            UploadFile(filename="campus.mtmap", file=io.BytesIO(package_bytes)),
            self.db,
        )
        self.assertEqual(duplicate.id, imported.id)
        self.assertEqual(duplicate.dataset_id, imported.dataset_id)

    async def test_zip_slip_is_rejected_without_external_write(self) -> None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("../outside.txt", "blocked")
        upload = UploadFile(filename="unsafe.mtmap", file=io.BytesIO(package.getvalue()))
        with self.assertRaises(ApplicationError) as error:
            await project_import.import_project(upload, self.db)
        self.assertEqual(error.exception.code, "UNSAFE_PROJECT_ARCHIVE")
        self.assertFalse((self.root / "outside.txt").exists())

    async def test_manifest_hash_mismatch_is_rejected(self) -> None:
        project_bytes = json.dumps(
            {
                "schema_version": 1,
                "project": {"name": "Bad", "configuration": {}},
                "dataset": {"filename": "source.geojson"},
                "control_points": [],
                "icon_points": [],
            }
        ).encode()
        source_bytes = json.dumps(SAMPLE_GEOJSON).encode()
        files = [
            {
                "role": "project",
                "path": "project.json",
                "size": len(project_bytes),
                "sha256": hashlib.sha256(project_bytes).hexdigest(),
            },
            {
                "role": "source",
                "path": "data/source.geojson",
                "size": len(source_bytes),
                "sha256": "0" * 64,
            },
        ]
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps({"format": "mtmap", "version": 1, "files": files}),
            )
            archive.writestr("project.json", project_bytes)
            archive.writestr("data/source.geojson", source_bytes)
        upload = UploadFile(filename="corrupt.mtmap", file=io.BytesIO(package.getvalue()))
        with self.assertRaises(ApplicationError) as error:
            await project_import.import_project(upload, self.db)
        self.assertEqual(error.exception.code, "PROJECT_INTEGRITY_ERROR")
