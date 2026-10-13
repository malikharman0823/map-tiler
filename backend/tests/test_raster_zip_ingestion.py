import asyncio
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy
import rasterio
from fastapi import BackgroundTasks, UploadFile
from rasterio.crs import CRS

from storage.repository import SessionRepository
from functions.raster_zip import function as raster_zip
from schemas.error import ApplicationError


class RasterZipIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.uploads = self.root / "storage" / "uploads"
        self.db = SessionRepository(
            session_id="test_raster_zip_ingestion",
            session_dir=self.root / "session",
        )
        self.original_upload_directory = raster_zip.UPLOAD_DIRECTORY
        raster_zip.UPLOAD_DIRECTORY = self.uploads

        self.source = self.root / "floor.png"
        with rasterio.open(
            self.source,
            "w",
            driver="PNG",
            width=4,
            height=3,
            count=3,
            dtype="uint8",
        ) as image:
            image.write(numpy.full((3, 3, 4), 255, dtype="uint8"))

    def tearDown(self) -> None:
        raster_zip.UPLOAD_DIRECTORY = self.original_upload_directory
        self.db.close()
        self.temporary.cleanup()

    def _zip_bytes(self, entries: dict[str, bytes]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in entries.items():
                archive.writestr(name, value)
        return output.getvalue()

    def _upload(self, content: bytes, filename: str = "dataset.zip"):
        upload = UploadFile(file=io.BytesIO(content), filename=filename)
        return asyncio.run(
            raster_zip.import_raster_zip(
                upload,
                self.db,
                BackgroundTasks(),
            )
        )

    def test_unreferenced_raster_bundle_imports_as_raw(self) -> None:
        response = self._upload(
            self._zip_bytes({"floor.png": self.source.read_bytes()})
        )

        self.assertFalse(response.data.is_georeferenced)
        self.assertEqual(response.data.georeference_status, "not_started")
        dataset = self.db.get_dataset(response.data.id)
        self.assertIsNotNone(dataset)
        self.assertIsNone(dataset.georeferenced_path)
        self.assertTrue((self.root / dataset.storage_path).is_file())

    def test_matching_world_and_crs_sidecars_mark_dataset_georeferenced(self) -> None:
        world = "2\n0\n0\n-2\n101\n199\n".encode()
        projection = CRS.from_epsg(4326).to_wkt().encode()
        response = self._upload(
            self._zip_bytes(
                {
                    "nested/floor.png": self.source.read_bytes(),
                    "nested/floor.pgw": world,
                    "nested/floor.prj": projection,
                }
            )
        )

        self.assertTrue(response.data.is_georeferenced)
        dataset = self.db.get_dataset(response.data.id)
        self.assertIsNotNone(dataset)
        assert dataset is not None
        self.assertEqual(dataset.georeference_status, "completed")
        self.assertEqual(dataset.extracted_metadata["crs"], "EPSG:4326")
        self.assertEqual(dataset.extracted_metadata["georeference_source"], "sidecar")
        self.assertEqual(len(dataset.extracted_metadata["transform"]), 6)

    def test_unsafe_and_ambiguous_archives_leave_no_dataset_or_files(self) -> None:
        with self.assertRaises(ApplicationError) as unsafe:
            self._upload(
                self._zip_bytes({"../floor.png": self.source.read_bytes()})
            )
        self.assertEqual(unsafe.exception.code, "UNSAFE_RASTER_ARCHIVE")

        with self.assertRaises(ApplicationError) as ambiguous:
            self._upload(
                self._zip_bytes(
                    {
                        "floor-a.png": self.source.read_bytes(),
                        "floor-b.png": self.source.read_bytes(),
                    }
                )
            )
        self.assertEqual(ambiguous.exception.code, "AMBIGUOUS_RASTER_BUNDLE")
        self.assertEqual(self.db.list_datasets(), [])
        self.assertFalse(self.uploads.exists())

    def test_non_zip_and_extra_files_are_rejected(self) -> None:
        with self.assertRaises(ApplicationError) as extension:
            self._upload(b"not a zip", "floor.png")
        self.assertEqual(extension.exception.code, "ZIP_REQUIRED")

        with self.assertRaises(ApplicationError) as extra:
            self._upload(
                self._zip_bytes(
                    {
                        "floor.png": self.source.read_bytes(),
                        "readme.txt": b"unexpected",
                    }
                )
            )
        self.assertEqual(extra.exception.code, "UNSUPPORTED_RASTER_BUNDLE_CONTENT")


if __name__ == "__main__":
    unittest.main()
