import tempfile
import unittest
from pathlib import Path
from typing import Literal

import numpy
import rasterio

from storage.repository import RepositoryError, SessionRepository
from functions.control_points.function import (
    delete_control_point,
    update_control_point,
)
from functions.control_points.request import (
    ControlPointRequest,
    UpdateControlPointRequest,
)
from functions.georeference import function as georeference
from functions.georeference.request import GeoreferenceRequest
from functions.icon_points.function import (
    create_icon_point,
    delete_icon_point,
    list_icon_points,
    update_icon_point,
)
from functions.icon_points.request import (
    CreateIconPointRequest,
    DatasetIconPointsRequest,
    IconPointRequest,
    UpdateIconPointRequest,
)
from models.control_point import ControlPoint
from models.dataset import Dataset
from schemas.error import ApplicationError


class FailOnceSessionRepository(SessionRepository):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.failed = False

    def commit(self) -> None:
        if not self.failed:
            self.failed = True
            raise RepositoryError("simulated commit failure")
        super().commit()


class GeoreferencePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.uploads = self.root / "storage" / "uploads"
        self.processed = self.root / "storage" / "processed"
        self.uploads.mkdir(parents=True)
        self.db = SessionRepository(
            session_id="test_georeference_persistence",
            session_dir=self.root / "session",
        )

        self.source_path = self.uploads / "known.png"
        with rasterio.open(
            self.source_path,
            "w",
            driver="PNG",
            width=100,
            height=100,
            count=3,
            dtype="uint8",
        ) as image:
            image.write(numpy.full((3, 100, 100), 128, dtype="uint8"))

        self.dataset = Dataset(
            filename="known.png",
            file_size=self.source_path.stat().st_size,
            content_type="image/png",
            file_hash="known-source-hash",
            storage_path="storage/uploads/known.png",
            extracted_metadata={"width": 100, "height": 100},
        )
        self.db.insert_dataset(self.dataset)
        for image_x, image_y in ((10, 10), (90, 10), (10, 90), (90, 90)):
            source_y = -image_y
            self.db.insert_control_point(
                ControlPoint(
                    dataset_id=self.dataset.id,
                    image_x=image_x,
                    image_y=image_y,
                    longitude=0.01 * image_x + 0.002 * source_y + 10,
                    latitude=-0.001 * image_x + 0.008 * source_y + 20,
                )
            )
        self.db.commit()
        self.original_constants = (
            georeference.BACKEND_DIRECTORY,
            georeference.UPLOAD_DIRECTORY,
            georeference.PROCESSED_DIRECTORY,
        )
        georeference.BACKEND_DIRECTORY = self.root
        georeference.UPLOAD_DIRECTORY = self.uploads
        georeference.PROCESSED_DIRECTORY = self.processed

    def tearDown(self) -> None:
        self.db.close()
        (
            georeference.BACKEND_DIRECTORY,
            georeference.UPLOAD_DIRECTORY,
            georeference.PROCESSED_DIRECTORY,
        ) = self.original_constants
        self.temporary.cleanup()

    def request(self, action: Literal["calculate", "save"]) -> GeoreferenceRequest:
        return GeoreferenceRequest(
            dataset_id=self.dataset.id,
            action=action,
            transformation="auto",
            output_format="tif",
            target_crs="EPSG:4326",
        )

    def test_calculate_save_reload_edit_and_isolation(self) -> None:
        icon = create_icon_point(
            DatasetIconPointsRequest(dataset_id=self.dataset.id),
            CreateIconPointRequest(
                latitude=28.6,
                longitude=77.2,
                icon_key="camera",
                description="Independent landmark",
            ),
            self.db,
        ).data

        calculated = georeference.georeference_dataset(
            self.request("calculate"), self.db
        ).data
        self.assertEqual(calculated.status, "calculated")
        self.assertIsNone(self.db.get_active_georeference_config(self.dataset.id))
        self.assertAlmostEqual(calculated.transformation_parameters["a"], 0.01)
        self.assertAlmostEqual(calculated.transformation_parameters["b"], 0.002)
        self.assertAlmostEqual(calculated.transformation_parameters["d"], -0.001)
        self.assertAlmostEqual(calculated.transformation_parameters["e"], 0.008)

        saved = georeference.georeference_dataset(
            self.request("save"), self.db
        ).data
        config = self.db.get_active_georeference_config(self.dataset.id)
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(saved.status, "completed")
        self.assertEqual(config.id, saved.georeference_config_id)
        self.assertEqual(config.source_coordinate_system["y"], "-image_y")
        self.assertEqual(config.source_crs, None)
        self.assertEqual(config.target_crs, "EPSG:4326")
        self.assertEqual((config.source_width, config.source_height), (100, 100))
        self.assertEqual(config.output_format, "GeoTIFF")
        self.assertFalse(Path(config.output_path).is_absolute())
        self.assertEqual(len(self.db.list_control_points(self.dataset.id)), 4)
        self.assertEqual(self.db.list_icon_points(self.dataset.id)[0].id, icon.id)

        output_path = self.root / config.output_path
        with rasterio.open(output_path) as output:
            self.assertAlmostEqual(output.transform.a, 0.01)
            self.assertAlmostEqual(output.transform.b, -0.002)
            self.assertAlmostEqual(output.transform.d, -0.001)
            self.assertAlmostEqual(output.transform.e, -0.008)

        reloaded = SessionRepository(
            session_id=self.db.session_id,
            session_dir=self.db.session_dir,
        )
        reloaded.load_from_disk()
        try:
            loaded = georeference.get_georeference_config(
                self.dataset.id, reloaded
            ).data.configuration
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertTrue(loaded.reusable)
            self.assertEqual(
                loaded.transformation_parameters,
                saved.transformation_parameters,
            )
        finally:
            reloaded.close()

        mismatched_dataset = self.db.get_dataset(self.dataset.id)
        self.assertIsNotNone(mismatched_dataset)
        assert mismatched_dataset is not None
        mismatched_dataset.extracted_metadata = {"width": 121, "height": 100}
        self.db.save_dataset(mismatched_dataset)
        self.db.commit()
        unsafe = georeference.get_georeference_config(
            self.dataset.id, self.db
        ).data.configuration
        self.assertIsNotNone(unsafe)
        assert unsafe is not None
        self.assertFalse(unsafe.reusable)
        self.assertEqual(unsafe.reuse_warning, georeference.REUSE_WARNING)
        mismatched_dataset.extracted_metadata = {"width": 100, "height": 100}
        self.db.save_dataset(mismatched_dataset)
        self.db.commit()

        first = self.db.list_control_points(self.dataset.id)[0]
        update_control_point(
            ControlPointRequest(control_point_id=first.id),
            UpdateControlPointRequest(
                image_x=first.image_x,
                image_y=first.image_y,
                longitude=first.longitude + 0.1,
                latitude=first.latitude,
            ),
            self.db,
        )
        active_config = self.db.get_active_georeference_config(self.dataset.id)
        self.assertIsNotNone(active_config)
        assert active_config is not None
        self.assertEqual(
            active_config.status,
            "pending",
        )
        updated = georeference.georeference_dataset(
            self.request("save"), self.db
        ).data
        self.assertEqual(updated.georeference_config_id, saved.georeference_config_id)
        self.assertNotEqual(
            updated.transformation_parameters,
            saved.transformation_parameters,
        )

        last = self.db.list_control_points(self.dataset.id)[-1]
        delete_control_point(ControlPointRequest(control_point_id=last.id), self.db)
        self.assertIsNone(self.db.get_control_point(last.id))
        self.assertEqual(len(self.db.list_icon_points(self.dataset.id)), 1)

    def test_icon_point_crud_does_not_change_control_points(self) -> None:
        control_count = len(self.db.list_control_points(self.dataset.id))
        created = create_icon_point(
            DatasetIconPointsRequest(dataset_id=self.dataset.id),
            CreateIconPointRequest(
                latitude=1,
                longitude=2,
                icon_key="camera",
                description="one",
            ),
            self.db,
        ).data
        updated = update_icon_point(
            IconPointRequest(icon_point_id=created.id),
            UpdateIconPointRequest(
                latitude=3,
                longitude=4,
                icon_key="camera",
                description="two",
            ),
            self.db,
        ).data
        self.assertEqual(updated.description, "two")
        self.assertEqual(
            list_icon_points(
                DatasetIconPointsRequest(dataset_id=self.dataset.id), self.db
            ).data.count,
            1,
        )
        delete_icon_point(IconPointRequest(icon_point_id=created.id), self.db)
        self.assertEqual(self.db.list_icon_points(self.dataset.id), [])
        self.assertEqual(
            len(self.db.list_control_points(self.dataset.id)), control_count
        )

    def test_failed_commit_restores_previous_output(self) -> None:
        georeference.georeference_dataset(self.request("save"), self.db)
        output_path = georeference._output_path(self.dataset.id, self.db)
        with rasterio.open(output_path) as output:
            previous_transform = output.transform

        first = self.db.list_control_points(self.dataset.id)[0]
        first.longitude += 0.2
        self.db.save_control_point(first)
        self.db.mark_georeference_config_pending(self.dataset.id)
        self.db.commit()
        self.db.close()

        failing = FailOnceSessionRepository(
            session_id=self.db.session_id,
            session_dir=self.db.session_dir,
        )
        failing.load_from_disk()
        self.db = failing
        with self.assertRaises(ApplicationError) as raised:
            georeference.georeference_dataset(self.request("save"), failing)
        self.assertEqual(raised.exception.code, "GEOREFERENCE_SAVE_FAILED")
        with rasterio.open(output_path) as output:
            self.assertEqual(output.transform, previous_transform)


if __name__ == "__main__":
    unittest.main()
