import asyncio
import io
from pathlib import Path
import tempfile
from typing import Any
import unittest
from uuid import UUID

from fastapi import BackgroundTasks, UploadFile

from functions.georeference.function import georeference_dataset
from functions.georeference.request import GeoreferenceRequest
from functions.raster_zip.function import import_raster_zip
from functions.workspace.function import (
    attach_workspace_member,
    get_workspace_manifest,
)
from functions.workspace.request import WorkspaceMemberCreateRequest
from models.control_point import ControlPoint
from models.dataset import Dataset
from storage.repository import SessionRepository


class MultiFloorRasterSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = SessionRepository(
            session_id="test_multifloor_session",
            session_dir=self.root / "session",
        )
        self.fixture_path = (
            Path(__file__).resolve().parent / "fixtures" / "maptiler_multifloor_test_data.zip"
        )
        self.assertTrue(
            self.fixture_path.is_file(),
            f"Fixture missing at {self.fixture_path}",
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temporary.cleanup()

    def _upload_fixture(self) -> tuple[UploadFile, Any]:
        f = UploadFile(
            file=io.BytesIO(self.fixture_path.read_bytes()),
            filename="maptiler_multifloor_test_data.zip",
        )
        response = asyncio.run(import_raster_zip(f, self.db, BackgroundTasks()))
        return f, response

    def test_multifloor_zip_discovery_and_metadata(self) -> None:
        _, response = self._upload_fixture()

        datasets = self.db.list_datasets()
        self.assertEqual(len(datasets), 5, "Expected all 5 PNG floor plans to be discovered.")

        expected_filenames = {
            "basement_1.png",
            "ground_floor.png",
            "floor_1.png",
            "floor_2.png",
            "floor_3.png",
        }
        discovered_filenames = {d.filename for d in datasets}
        self.assertEqual(discovered_filenames, expected_filenames)

        # Unique IDs
        dataset_ids = {d.id for d in datasets}
        self.assertEqual(len(dataset_ids), 5)

        # All 5 intentionally unreferenced
        for d in datasets:
            self.assertEqual(d.georeference_status, "not_started")
            self.assertIsNone(d.georeferenced_path)
            meta = d.extracted_metadata or {}
            self.assertEqual(meta.get("building_name"), "Test Building A")
            self.assertTrue(meta.get("is_building_floor"))
            self.assertIn(meta.get("floor_level"), {-1, 0, 1, 2, 3})

        # Manifest check
        manifest = get_workspace_manifest(response.data.id, self.db).data
        self.assertEqual(manifest.name, "Test Building A")
        self.assertEqual(len(manifest.members), 5)

        # Order check: -1, 0, 1, 2, 3
        levels = [m.floor_level for m in manifest.members]
        self.assertEqual(levels, [-1, 0, 1, 2, 3])

        # Primary is ground floor (level 0)
        primary_member = next(m for m in manifest.members if m.is_primary)
        self.assertEqual(primary_member.floor_level, 0)
        self.assertEqual(primary_member.name, "GROUND FLOOR")

    def test_multifloor_building_georeference_inheritance(self) -> None:
        _, response = self._upload_fixture()
        primary_id = response.data.id

        # Insert 4 control points for primary dataset (Zurich coordinates)
        points = [
            ControlPoint(dataset_id=primary_id, image_x=100, image_y=100, longitude=8.540, latitude=47.378),
            ControlPoint(dataset_id=primary_id, image_x=1100, image_y=100, longitude=8.545, latitude=47.378),
            ControlPoint(dataset_id=primary_id, image_x=1100, image_y=800, longitude=8.545, latitude=47.374),
            ControlPoint(dataset_id=primary_id, image_x=100, image_y=800, longitude=8.540, latitude=47.374),
        ]
        for p in points:
            self.db.insert_control_point(p)

        # Apply building-level georeferencing
        geo_response = georeference_dataset(
            GeoreferenceRequest(
                dataset_id=primary_id,
                action="save",
                transformation="affine",
                target_crs="EPSG:4326",
            ),
            self.db,
        )

        self.assertEqual(geo_response.data.status, "completed")
        self.assertEqual(len(geo_response.data.propagated_sibling_ids), 4)

        # Verify all 5 floors have completed georeferencing
        all_datasets = self.db.list_datasets()
        self.assertEqual(len(all_datasets), 5)
        for d in all_datasets:
            self.assertEqual(d.georeference_status, "completed")
            self.assertIsNotNone(d.georeferenced_path)
            # Sibling also has control points
            pts = self.db.list_control_points(d.id)
            self.assertEqual(len(pts), 4)

    def test_second_dataset_coexistence(self) -> None:
        _, response = self._upload_fixture()
        primary_id = response.data.id

        # Add a 2nd standalone dataset
        second_dataset = Dataset(
            filename="standalone_park.png",
            file_size=2048,
            content_type="image/png",
            file_hash="park_hash_123",
            storage_path="storage/uploads/standalone_park.png",
            extracted_metadata={"format": "png", "width": 500, "height": 500},
        )
        self.db.insert_dataset(second_dataset)
        self.db.commit()

        # Attach 2nd dataset to workspace
        attach_workspace_member(
            primary_id,
            WorkspaceMemberCreateRequest(dataset_id=second_dataset.id),
            self.db,
        )

        manifest = get_workspace_manifest(primary_id, self.db).data
        self.assertEqual(len(manifest.members), 6)

        # 5 floors under building + 1 standalone
        building_members = [m for m in manifest.members if m.building_name == "Test Building A"]
        self.assertEqual(len(building_members), 5)

        standalone_members = [m for m in manifest.members if m.dataset_id == second_dataset.id]
        self.assertEqual(len(standalone_members), 1)
        self.assertFalse(standalone_members[0].is_building_floor)


if __name__ == "__main__":
    unittest.main()
