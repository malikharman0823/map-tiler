import tempfile
import unittest
from pathlib import Path

from storage.repository import SessionRepository
from functions.workspace.function import (
    attach_workspace_member,
    detach_workspace_member,
    get_workspace_manifest,
    get_workspace_records,
    update_workspace_member,
    update_workspace_state,
)
from functions.workspace.request import (
    WorkspaceCameraRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceStateUpdateRequest,
)
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError


class DatasetWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.db = SessionRepository(
            session_id="test_dataset_workspace",
            session_dir=Path(self.temporary.name) / "session",
        )
        self.primary = Dataset(
            filename="floor-a.png",
            file_size=100,
            content_type="image/png",
            file_hash="floor-a",
            storage_path="storage/uploads/floor-a.png",
            extracted_metadata={"format": "png", "width": 100, "height": 80},
        )
        self.secondary = Dataset(
            filename="floor-b.tif",
            file_size=200,
            content_type="image/tiff",
            file_hash="floor-b",
            storage_path="C:/private/storage/uploads/floor-b.tif",
            extracted_metadata={
                "format": "tiff",
                "width": 200,
                "height": 160,
                "crs": "EPSG:4326",
                "transform": [1, 0, 0, 0, -1, 0],
                "bounds": [10, 20, 11, 21],
            },
            georeference_status="completed",
        )
        self.db.insert_dataset(self.primary)
        self.db.insert_dataset(self.secondary)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.temporary.cleanup()

    def test_existing_project_is_backfilled_with_primary_settings(self) -> None:
        project = MapProject(
            name="Existing project",
            dataset_id=self.primary.id,
            configuration={
                "opacity": 0.4,
                "layerVisibility": {
                    "dataset": False,
                    "controlPoints": True,
                    "iconPoints": False,
                },
            },
        )
        self.db.insert_map_project(project)
        self.db.commit()

        manifest = get_workspace_manifest(self.primary.id, self.db).data

        self.assertEqual(manifest.id, project.id)
        self.assertEqual(len(manifest.members), 1)
        member = manifest.members[0]
        self.assertTrue(member.is_primary)
        self.assertFalse(member.raster_visible)
        self.assertTrue(member.control_points_visible)
        self.assertFalse(member.icon_points_visible)
        self.assertEqual(member.raster_opacity, 0.4)

    def test_attach_update_state_records_and_detach_preserve_dataset(self) -> None:
        manifest = get_workspace_manifest(self.primary.id, self.db).data
        self.assertEqual([member.dataset_id for member in manifest.members], [self.primary.id])

        manifest = attach_workspace_member(
            self.primary.id,
            WorkspaceMemberCreateRequest(dataset_id=self.secondary.id),
            self.db,
        ).data
        self.assertEqual(len(manifest.members), 2)

        self.db.insert_control_point(
            ControlPoint(
                dataset_id=self.secondary.id,
                image_x=10,
                image_y=20,
                longitude=77.2,
                latitude=28.6,
            )
        )
        self.db.insert_icon_point(
            IconPoint(
                dataset_id=self.secondary.id,
                icon_key="camera",
                longitude=77.21,
                latitude=28.61,
                description="North entrance",
            )
        )
        self.db.commit()

        manifest = update_workspace_member(
            self.primary.id,
            self.secondary.id,
            WorkspaceMemberUpdateRequest(
                alias="Annex",
                sort_order=0,
                raster_opacity=0.25,
                icon_points_visible=False,
            ),
            self.db,
        ).data
        secondary_member = next(
            member for member in manifest.members if member.dataset_id == self.secondary.id
        )
        self.assertEqual(secondary_member.name, "Annex")
        self.assertEqual(secondary_member.raster_opacity, 0.25)
        self.assertFalse(secondary_member.icon_points_visible)
        self.assertEqual(secondary_member.dataset.storage_path, "floor-b.tif")
        self.assertNotIn("C:/private", secondary_member.dataset.storage_path)

        manifest = update_workspace_state(
            self.primary.id,
            WorkspaceStateUpdateRequest(
                active_view="database",
                camera=WorkspaceCameraRequest(
                    longitude=77.2,
                    latitude=28.6,
                    zoom=14,
                ),
            ),
            self.db,
        ).data
        self.assertEqual(manifest.active_view, "database")
        self.assertEqual(manifest.camera.zoom, 14)

        records = get_workspace_records(
            self.primary.id,
            self.db,
            dataset_id=self.secondary.id,
            page_size=10,
        ).data
        self.assertEqual(records.total, 3)
        self.assertEqual(
            {record.kind for record in records.records},
            {"raster", "control_point", "icon_point"},
        )
        raster = next(record for record in records.records if record.kind == "raster")
        self.assertEqual(raster.managed_path, "floor-b.tif")
        self.assertNotIn("C:/private", raster.managed_path)

        manifest = detach_workspace_member(
            self.primary.id,
            self.secondary.id,
            self.db,
        ).data
        self.assertEqual(len(manifest.members), 1)
        self.assertIsNotNone(self.db.get_dataset(self.secondary.id))

    def test_duplicate_attach_and_primary_detach_are_rejected(self) -> None:
        get_workspace_manifest(self.primary.id, self.db)
        with self.assertRaises(ApplicationError) as duplicate:
            attach_workspace_member(
                self.primary.id,
                WorkspaceMemberCreateRequest(dataset_id=self.primary.id),
                self.db,
            )
        self.assertEqual(duplicate.exception.code, "WORKSPACE_MEMBER_EXISTS")

        with self.assertRaises(ApplicationError) as primary:
            detach_workspace_member(self.primary.id, self.primary.id, self.db)
        self.assertEqual(primary.exception.code, "PRIMARY_DATASET_REQUIRED")

    def test_workspace_still_loads_when_saved_tiles_are_missing(self) -> None:
        self.primary.georeference_status = "completed"
        self.primary.processed_path = "storage/processed/missing/output.tif"
        self.primary.tile_status = "completed"
        self.primary.tile_path = "storage/tiles/missing"
        self.primary.tile_min_zoom = 0
        self.primary.tile_max_zoom = 18
        self.db.save_dataset(self.primary)
        self.db.commit()

        manifest = get_workspace_manifest(self.primary.id, self.db).data

        self.assertEqual(len(manifest.members), 1)
        self.assertIsNone(manifest.members[0].dataset.map_layer)
        self.assertTrue(manifest.members[0].dataset.is_georeferenced)


if __name__ == "__main__":
    unittest.main()
