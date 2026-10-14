from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import numpy
import rasterio

from config import settings
from main import app
from models.control_point import ControlPoint
from models.dataset import Dataset
from storage.repository import SessionRepository
from storage.session import SessionStorage, cleanup_expired_sessions, session_storage
from schemas.error import ApplicationError


def write_test_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    pixels = numpy.empty((3, height, width), dtype="uint8")
    for band, value in enumerate(rgb):
        pixels[band].fill(value)
    with rasterio.open(
        path,
        "w",
        driver="PNG",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
    ) as image:
        image.write(pixels)


class SessionRepositoryComprehensiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.session_dir = self.root / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Point session_storage and settings to isolated temp folder
        self.original_session_storage_dir = settings.session_storage_dir
        settings.session_storage_dir = self.session_dir
        self.storage = SessionStorage(root_dir=self.session_dir)
        # Patch global session_storage used by main.py
        self.original_global_storage = session_storage
        import storage.session as session_module
        import main as main_module
        session_module.session_storage = self.storage
        main_module.session_storage = self.storage

        self.client = TestClient(app)

        self.sample_png_path = self.root / "sample.png"
        write_test_png(self.sample_png_path, 50, 50, (255, 0, 0))
        self.sample_tiff_path = self.sample_png_path

    def tearDown(self) -> None:
        settings.session_storage_dir = self.original_session_storage_dir
        import storage.session as session_module
        import main as main_module
        session_module.session_storage = self.original_global_storage
        main_module.session_storage = self.original_global_storage
        self.temp_dir.cleanup()

    def _create_session(self) -> str:
        resp = self.client.post("/sessions")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        return data["session_id"]

    def _upload_dataset(self, session_id: str, filename: str = "sample.png") -> str:
        with open(self.sample_png_path, "rb") as f:
            resp = self.client.post(
                "/upload",
                files={"file": (filename, f.read(), "image/png")},
                headers={"X-Session-ID": session_id},
            )
        self.assertEqual(resp.status_code, 201)
        return resp.json()["data"]["id"]

    # -------------------------------------------------------------------------
    # Test 1: Session survives navigation between pages
    # -------------------------------------------------------------------------
    def test_session_survives_navigation_between_pages(self) -> None:
        session_id = self._create_session()
        dataset_id = self._upload_dataset(session_id)

        headers = {"X-Session-ID": session_id}

        # 1. Navigate to georeference page endpoint
        georef_resp = self.client.get(f"/datasets/{dataset_id}/georeference", headers=headers)
        self.assertEqual(georef_resp.status_code, 200)

        # 2. Navigate to workspace manifest endpoint
        workspace_resp = self.client.get(f"/datasets/{dataset_id}/workspace", headers=headers)
        self.assertEqual(workspace_resp.status_code, 200)

        # 3. Navigate to workspace records (attribute table)
        records_resp = self.client.get(f"/datasets/{dataset_id}/workspace/records", headers=headers)
        self.assertEqual(records_resp.status_code, 200)

        # 4. Navigate to datasets list
        list_resp = self.client.get("/datasets", headers=headers)
        self.assertEqual(list_resp.status_code, 200)
        datasets = list_resp.json()["data"]["datasets"]
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]["id"], dataset_id)

    # -------------------------------------------------------------------------
    # Test 2: Session survives frontend refreshes
    # -------------------------------------------------------------------------
    def test_session_survives_frontend_refreshes(self) -> None:
        session_id = self._create_session()
        dataset_id = self._upload_dataset(session_id)

        # Simulate user updating project name and map view
        headers = {"X-Session-ID": session_id}
        update_resp = self.client.put(
            f"/datasets/{dataset_id}/project",
            json={"name": "Refreshed Map", "configuration": {"activeView": "split", "zoom": 5.5}},
            headers=headers,
        )
        self.assertEqual(update_resp.status_code, 200)

        # Simulate browser refresh by querying session verification endpoint
        verify_resp = self.client.get(f"/sessions/{session_id}", headers=headers)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertEqual(verify_resp.json()["data"]["session_id"], session_id)
        self.assertEqual(verify_resp.json()["data"]["dataset_count"], 1)

        # Verify state is intact after refresh
        datasets_resp = self.client.get("/datasets", headers=headers)
        self.assertEqual(len(datasets_resp.json()["data"]["datasets"]), 1)
        project_resp = self.client.get(f"/datasets/{dataset_id}/project", headers=headers)
        self.assertEqual(project_resp.json()["name"], "Refreshed Map")
        self.assertEqual(project_resp.json()["configuration"]["zoom"], 5.5)

    # -------------------------------------------------------------------------
    # Test 3: Multiple uploads remain in the same session
    # -------------------------------------------------------------------------
    def test_multiple_uploads_remain_in_the_same_session(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}

        # Upload first dataset
        with open(self.sample_png_path, "rb") as f:
            resp1 = self.client.post(
                "/upload",
                files={"file": ("dataset_1.png", f.read(), "image/png")},
                headers=headers,
            )
        self.assertEqual(resp1.status_code, 201)
        id1 = resp1.json()["data"]["id"]

        # Create another unique small PNG
        second_path = self.root / "second.png"
        write_test_png(second_path, 20, 20, (0, 0, 255))

        with open(second_path, "rb") as f:
            resp2 = self.client.post(
                "/upload",
                files={"file": ("dataset_2.png", f.read(), "image/png")},
                headers=headers,
            )
        self.assertEqual(resp2.status_code, 201)
        id2 = resp2.json()["data"]["id"]

        # Check list of datasets in the session
        list_resp = self.client.get("/datasets", headers=headers)
        dataset_ids = [d["id"] for d in list_resp.json()["data"]["datasets"]]
        self.assertIn(id1, dataset_ids)
        self.assertIn(id2, dataset_ids)
        self.assertEqual(len(dataset_ids), 2)

    # -------------------------------------------------------------------------
    # Test 4: Multiple datasets remain independently selectable
    # -------------------------------------------------------------------------
    def test_multiple_datasets_remain_independently_selectable(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}

        # Upload dataset A & B
        with open(self.sample_png_path, "rb") as f:
            id_a = self.client.post("/upload", files={"file": ("a.png", f.read(), "image/png")}, headers=headers).json()["data"]["id"]

        second_path = self.root / "b.png"
        write_test_png(second_path, 30, 30, (0, 255, 0))
        with open(second_path, "rb") as f:
            id_b = self.client.post("/upload", files={"file": ("b.png", f.read(), "image/png")}, headers=headers).json()["data"]["id"]

        # Attach dataset B to workspace
        attach_resp = self.client.post(
            f"/datasets/{id_a}/workspace/members",
            json={"dataset_id": id_b},
            headers=headers,
        )
        self.assertEqual(attach_resp.status_code, 201)

        # Modify dataset B's visibility and opacity independently
        patch_resp = self.client.patch(
            f"/datasets/{id_a}/workspace/members/{id_b}",
            json={"raster_visible": False, "raster_opacity": 0.35},
            headers=headers,
        )
        self.assertEqual(patch_resp.status_code, 200)

        # Verify dataset B changed while dataset A remains visible with default opacity
        manifest = self.client.get(f"/datasets/{id_a}/workspace", headers=headers).json()["data"]
        members = {m["dataset_id"]: m for m in manifest["members"]}
        self.assertTrue(members[id_a]["raster_visible"])
        self.assertFalse(members[id_b]["raster_visible"])
        self.assertEqual(members[id_b]["raster_opacity"], 0.35)

    # -------------------------------------------------------------------------
    # Test 5: Georeferencing metadata survives page changes
    # -------------------------------------------------------------------------
    def test_georeferencing_metadata_survives_page_changes(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}

        # Upload unreferenced image
        unref_path = self.root / "unref.png"
        with rasterio.open(unref_path, "w", driver="PNG", width=50, height=50, count=3, dtype="uint8") as d:
            d.write(numpy.ones((3, 50, 50), dtype="uint8"))
        with open(unref_path, "rb") as f:
            did = self.client.post("/upload", files={"file": ("unref.png", f.read(), "image/png")}, headers=headers).json()["data"]["id"]

        # Add 4 control points inside 50x50 image bounds (0 <= x < 50, 0 <= y < 50)
        for i, (ix, iy, lng, lat) in enumerate([(0, 0, 10.0, 50.0), (49, 0, 11.0, 50.0), (49, 49, 11.0, 49.0), (0, 49, 10.0, 49.0)]):
            self.client.post(
                f"/datasets/{did}/control-points",
                json={"dataset_id": str(did), "image_x": ix, "image_y": iy, "longitude": lng, "latitude": lat},
                headers=headers,
            )

        # Save georeference
        geo_resp = self.client.post(
            f"/datasets/{did}/georeference",
            json={"action": "save", "transformation": "affine", "output_format": "tif", "target_crs": "EPSG:4326"},
            headers=headers,
        )
        self.assertEqual(geo_resp.status_code, 200)

        # Navigate away to workspace and records
        self.client.get(f"/datasets/{did}/workspace", headers=headers)
        self.client.get("/datasets", headers=headers)

        # Navigate back to georeference page
        loaded_geo = self.client.get(f"/datasets/{did}/georeference", headers=headers).json()["data"]["configuration"]
        self.assertIsNotNone(loaded_geo)
        self.assertEqual(loaded_geo["target_crs"], "EPSG:4326")
        self.assertEqual(loaded_geo["control_point_count"], 4)
        self.assertTrue(loaded_geo["reusable"])

    # -------------------------------------------------------------------------
    # Test 6: Control-point changes persist
    # -------------------------------------------------------------------------
    def test_control_point_changes_persist(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        # Create control point
        cp_resp = self.client.post(
            f"/datasets/{did}/control-points",
            json={"dataset_id": did, "image_x": 10.0, "image_y": 20.0, "longitude": 12.34, "latitude": 56.78},
            headers=headers,
        )
        self.assertEqual(cp_resp.status_code, 201)
        cp_id = cp_resp.json()["data"]["id"]

        # Update control point
        update_resp = self.client.put(
            f"/control-points/{cp_id}",
            json={"image_x": 15.0, "image_y": 25.0, "longitude": 13.0, "latitude": 57.0},
            headers=headers,
        )
        self.assertEqual(update_resp.status_code, 200)

        # Navigate away and reload
        self.client.get("/datasets", headers=headers)
        points_resp = self.client.get(f"/datasets/{did}/control-points", headers=headers)
        points = points_resp.json()["data"]["points"]
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["image_x"], 15.0)
        self.assertEqual(points[0]["longitude"], 13.0)

    # -------------------------------------------------------------------------
    # Test 7: Layer visibility and ordering persist
    # -------------------------------------------------------------------------
    def test_layer_visibility_and_ordering_persist(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        # Update workspace state
        state_resp = self.client.patch(
            f"/datasets/{did}/workspace/state",
            json={
                "active_view": "map",
                "camera": {"longitude": 45.0, "latitude": 15.0, "zoom": 12.0, "bearing": 30.0, "pitch": 45.0},
            },
            headers=headers,
        )
        self.assertEqual(state_resp.status_code, 200)

        # Verify state persists after navigation
        self.client.get(f"/datasets/{did}/georeference", headers=headers)
        manifest = self.client.get(f"/datasets/{did}/workspace", headers=headers).json()["data"]
        self.assertEqual(manifest["active_view"], "map")
        self.assertEqual(manifest["camera"]["longitude"], 45.0)
        self.assertEqual(manifest["camera"]["latitude"], 15.0)
        self.assertEqual(manifest["camera"]["zoom"], 12.0)

    # -------------------------------------------------------------------------
    # Test 8: Edits are reflected in exports
    # -------------------------------------------------------------------------
    def test_edits_are_reflected_in_exports(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        # Update project name and add an icon point
        self.client.put(
            f"/datasets/{did}/project",
            json={"name": "Exported Custom Session", "configuration": {"activeView": "map"}},
            headers=headers,
        )
        self.client.post(
            f"/datasets/{did}/icon-points",
            json={"icon_key": "star", "latitude": 20.5, "longitude": 10.5, "description": "Export Point"},
            headers=headers,
        )

        # Set dataset tile status and processed raster so export can generate package
        from uuid import UUID
        session = self.storage.get_session(session_id)
        self.assertIsNotNone(session)
        assert session is not None
        dataset = session.datasets[UUID(did)]
        proc_tif = session.get_processed_dir(UUID(did)) / "processed.tif"
        with rasterio.open(
            proc_tif,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=rasterio.transform.from_bounds(10.0, 20.0, 11.0, 21.0, 2, 2),
        ) as dest:
            dest.write(numpy.ones((1, 2, 2), dtype="uint8"))
        dataset.processed_path = str(proc_tif)
        dataset.process_status = "completed"

        tile_dir = session.get_tiles_dir(UUID(did))
        (tile_dir / "0" / "0").mkdir(parents=True, exist_ok=True)
        (tile_dir / "0" / "0" / "0.png").write_bytes(b"tile-data")
        dataset.tile_path = str(tile_dir)
        dataset.tile_status = "completed"
        dataset.tile_min_zoom = 0
        dataset.tile_max_zoom = 0

        # Export project
        export_resp = self.client.get(f"/datasets/{did}/export", headers=headers)
        self.assertEqual(export_resp.status_code, 200)
        self.assertTrue(export_resp.content.startswith(b"PK"))

        # Inspect ZIP content
        with zipfile.ZipFile(io.BytesIO(export_resp.content)) as archive:
            self.assertIn("mapstudio.json", archive.namelist())
            import json
            doc = json.loads(archive.read("mapstudio.json"))
            self.assertEqual(doc["project"]["name"], "Exported Custom Session")
            self.assertEqual(len(doc["icon_points"]), 1)
            self.assertEqual(doc["icon_points"][0]["description"], "Export Point")

    # -------------------------------------------------------------------------
    # Test 9: Failed operation does not erase the session
    # -------------------------------------------------------------------------
    def test_failed_operation_does_not_erase_session(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        # Send invalid control point (latitude > 90) -> expect 422 validation error
        fail_resp = self.client.post(
            f"/datasets/{did}/control-points",
            json={"image_x": 0.0, "image_y": 0.0, "longitude": 0.0, "latitude": 999.0},
            headers=headers,
        )
        self.assertEqual(fail_resp.status_code, 422)

        # Verify session and previous dataset are completely untouched
        list_resp = self.client.get("/datasets", headers=headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["data"]["datasets"]), 1)

    # -------------------------------------------------------------------------
    # Test 10: Expired session is cleaned up
    # -------------------------------------------------------------------------
    def test_expired_session_is_cleaned_up(self) -> None:
        session_id = self._create_session()
        repo = self.storage.get_session(session_id)
        self.assertIsNotNone(repo)

        # Artificially set last_accessed_at in the past
        repo.last_accessed_at = datetime.now(timezone.utc) - timedelta(hours=5)
        repo._save_manifest_atomic()

        # Run cleanup
        cleaned = cleanup_expired_sessions(self.storage)
        self.assertIn(session_id, cleaned)

        # Verify directory deleted and cannot be accessed
        self.assertFalse((self.session_dir / session_id).exists())
        resp = self.client.get("/datasets", headers={"X-Session-ID": session_id})
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------------------
    # Test 11: One session cannot access another session's data
    # -------------------------------------------------------------------------
    def test_cross_session_isolation(self) -> None:
        session_a = self._create_session()
        session_b = self._create_session()

        did_a = self._upload_dataset(session_a, filename="dataset_a.png")

        # Session B attempts to read dataset A
        leak_resp = self.client.get(f"/datasets/{did_a}", headers={"X-Session-ID": session_b})
        self.assertEqual(leak_resp.status_code, 404)

        # Session B listing datasets returns empty
        list_b = self.client.get("/datasets", headers={"X-Session-ID": session_b})
        self.assertEqual(len(list_b.json()["data"]["datasets"]), 0)

    # -------------------------------------------------------------------------
    # Test 12: Backend restart restores sessions
    # -------------------------------------------------------------------------
    def test_backend_restart_restores_sessions(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        # Update map configuration
        self.client.put(
            f"/sessions/{session_id}/map-config",
            json={"basemap": "satellite", "zoom": 7.0},
            headers=headers,
        )

        original_restore = settings.restore_sessions_on_startup
        try:
            settings.restore_sessions_on_startup = True
            # Simulate backend restart with a new SessionStorage instance
            new_storage = SessionStorage(root_dir=self.session_dir)
            restored_count = new_storage.restore_all_on_startup()
            self.assertGreaterEqual(restored_count, 1)

            restored_repo = new_storage.get_session(session_id)
            self.assertIsNotNone(restored_repo)
            self.assertIn(did, [str(d) for d in restored_repo.datasets.keys()])
            self.assertEqual(restored_repo.get_map_configuration()["basemap"], "satellite")
        finally:
            settings.restore_sessions_on_startup = original_restore

    # -------------------------------------------------------------------------
    # Test 12b: Ending a session immediately removes all dataset files from disk
    # -------------------------------------------------------------------------
    def test_end_session_cleans_up_all_files(self) -> None:
        session_id = self._create_session()
        headers = {"X-Session-ID": session_id}
        did = self._upload_dataset(session_id)

        session = self.storage.get_session(session_id)
        self.assertIsNotNone(session)
        assert session is not None
        from uuid import UUID
        dataset = session.datasets[UUID(did)]
        storage_path = Path(dataset.storage_path) if dataset.storage_path else None
        self.assertTrue(storage_path is not None and storage_path.exists())

        # End the session
        end_resp = self.client.post("/sessions/current/end", headers=headers)
        self.assertEqual(end_resp.status_code, 200)

        # Verify session directory is deleted
        self.assertFalse((self.session_dir / session_id).exists())
        # Verify source file is deleted
        self.assertFalse(storage_path.exists())

    # -------------------------------------------------------------------------
    # Test 13: Cleanup cannot delete a session during an active export
    # -------------------------------------------------------------------------
    def test_cleanup_cannot_delete_session_during_active_export(self) -> None:
        session_id = self._create_session()
        repo = self.storage.get_session(session_id)
        self.assertIsNotNone(repo)

        # Make session appear expired
        repo.last_accessed_at = datetime.now(timezone.utc) - timedelta(hours=3)

        # Protect session with active export
        with repo.protect_operation("export"):
            cleaned = cleanup_expired_sessions(self.storage)
            # Must NOT be cleaned while active export is running
            self.assertNotIn(session_id, cleaned)
            self.assertTrue((self.session_dir / session_id).exists())

        # Now that export completed, set expired and cleanup should succeed
        repo.last_accessed_at = datetime.now(timezone.utc) - timedelta(hours=3)
        repo._save_manifest_atomic()
        cleaned_after = cleanup_expired_sessions(self.storage)
        self.assertIn(session_id, cleaned_after)
        self.assertFalse((self.session_dir / session_id).exists())

    # -------------------------------------------------------------------------
    # Test 14: Disk quotas are enforced
    # -------------------------------------------------------------------------
    def test_disk_quota_enforced(self) -> None:
        session_id = self._create_session()
        repo = self.storage.get_session(session_id)
        self.assertIsNotNone(repo)

        # Temporarily set max storage per session to 500 bytes
        original_quota = settings.max_storage_per_session_bytes
        try:
            settings.max_storage_per_session_bytes = 500
            # Attempt to check quota with 1000 bytes
            with self.assertRaises(ApplicationError) as ctx:
                repo.check_quota(additional_bytes=1000)
            self.assertEqual(ctx.exception.code, "QUOTA_EXCEEDED")
            self.assertEqual(ctx.exception.status_code, 413)
        finally:
            settings.max_storage_per_session_bytes = original_quota

    # -------------------------------------------------------------------------
    # Test 15: Cleanup handles malformed/orphaned session directories without crashing
    # -------------------------------------------------------------------------
    def test_cleanup_handles_malformed_directories(self) -> None:
        malformed_dir = self.session_dir / "short_invalid"
        malformed_dir.mkdir(parents=True, exist_ok=True)
        (malformed_dir / "garbage.txt").write_text("orphan data", encoding="utf-8")
        self.assertTrue(malformed_dir.is_dir())

        cleaned = cleanup_expired_sessions(self.storage)
        self.assertIn("short_invalid", cleaned)
        self.assertFalse(malformed_dir.exists())


if __name__ == "__main__":
    unittest.main()

