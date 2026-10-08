import logging
from uuid import UUID

from database import DatabaseError, DatabaseSession

from functions.control_points.request import (
    ControlPointRequest,
    CreateControlPointRequest,
    DatasetControlPointsRequest,
    UpdateControlPointRequest,
)
from functions.control_points.response import (
    ControlPointData,
    ControlPointListData,
    ControlPointListItem,
    ControlPointListResponse,
    ControlPointResponse,
)
from models.control_point import ControlPoint
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)


def _dataset_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="DATASET_NOT_FOUND",
        message="The dataset was not found.",
        details="No dataset exists for the supplied dataset ID.",
        field="dataset_id",
    )


def _control_point_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="CONTROL_POINT_NOT_FOUND",
        message="The control point was not found.",
        details="No control point exists for the supplied ID.",
        field="control_point_id",
    )


def _database_error(details="The control point operation could not be completed.") -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DATABASE_ERROR",
        message="A database error occurred.",
        details=details,
    )


def _require_dataset(db: DatabaseSession, dataset_id: UUID) -> Dataset:
    dataset = db.get_dataset(dataset_id)
    if dataset is None:
        raise _dataset_not_found()
    return dataset


def _require_control_point(
    db: DatabaseSession,
    control_point_id: UUID,
) -> ControlPoint:
    control_point = db.get_control_point(control_point_id)
    if control_point is None:
        raise _control_point_not_found()
    return control_point


def _single_response(control_point: ControlPoint) -> ControlPointResponse:
    return ControlPointResponse(
        data=ControlPointData.model_validate(control_point)
    )


def create_control_point(
    dataset: DatasetControlPointsRequest,
    request: CreateControlPointRequest,
    db: DatabaseSession,
) -> ControlPointResponse:
    if request.dataset_id != dataset.dataset_id:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="The request contains invalid data.",
            details="The dataset ID in the request body must match the URL.",
            field="dataset_id",
        )

    try:
        stored_dataset = _require_dataset(db, dataset.dataset_id)
        stored_dataset.georeference_status = "not_started"
        stored_dataset.georeferenced_path = None
        stored_dataset.process_status = "not_started"
        stored_dataset.processed_path = None
        stored_dataset.tile_status = "not_started"
        stored_dataset.tile_path = None
        stored_dataset.tile_min_zoom = None
        stored_dataset.tile_max_zoom = None
        control_point = ControlPoint(
            dataset_id=dataset.dataset_id,
            image_x=request.image_x,
            image_y=request.image_y,
            longitude=request.longitude,
            latitude=request.latitude,
        )
        db.save_dataset(stored_dataset)
        db.insert_control_point(control_point)
        db.mark_georeference_config_pending(stored_dataset.id)
        db.commit()
        return _single_response(control_point)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to create a control point.", exc_info=exc)
        raise _database_error() from exc


def list_control_points(
    request: DatasetControlPointsRequest,
    db: DatabaseSession,
) -> ControlPointListResponse:
    try:
        _require_dataset(db, request.dataset_id)
        points = db.list_control_points(request.dataset_id)
        items = [ControlPointListItem.model_validate(point) for point in points]
        return ControlPointListResponse(
            data=ControlPointListData(points=items, count=len(items))
        )
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to list control points.", exc_info=exc)
        raise _database_error() from exc


def update_control_point(
    control_point: ControlPointRequest,
    request: UpdateControlPointRequest,
    db: DatabaseSession,
) -> ControlPointResponse:
    try:
        stored_point = _require_control_point(db, control_point.control_point_id)
        stored_dataset = _require_dataset(db, stored_point.dataset_id)
        stored_point.image_x = request.image_x
        stored_point.image_y = request.image_y
        stored_point.longitude = request.longitude
        stored_point.latitude = request.latitude
        stored_dataset.georeference_status = "not_started"
        stored_dataset.georeferenced_path = None
        stored_dataset.process_status = "not_started"
        stored_dataset.processed_path = None
        stored_dataset.tile_status = "not_started"
        stored_dataset.tile_path = None
        stored_dataset.tile_min_zoom = None
        stored_dataset.tile_max_zoom = None
        db.save_control_point(stored_point)
        db.save_dataset(stored_dataset)
        db.mark_georeference_config_pending(stored_dataset.id)
        db.commit()
        return _single_response(stored_point)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to update a control point.", exc_info=exc)
        raise _database_error(str(exc)) from exc


def delete_control_point(
    request: ControlPointRequest,
    db: DatabaseSession,
) -> ControlPointResponse:
    try:
        control_point = _require_control_point(db, request.control_point_id)
        stored_dataset = _require_dataset(db, control_point.dataset_id)
        response = _single_response(control_point)
        stored_dataset.georeference_status = "not_started"
        stored_dataset.georeferenced_path = None
        stored_dataset.process_status = "not_started"
        stored_dataset.processed_path = None
        stored_dataset.tile_status = "not_started"
        stored_dataset.tile_path = None
        stored_dataset.tile_min_zoom = None
        stored_dataset.tile_max_zoom = None
        db.save_dataset(stored_dataset)
        db.delete_control_point(control_point.id)
        db.mark_georeference_config_pending(stored_dataset.id)
        db.commit()
        return response
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to delete a control point.", exc_info=exc)
        raise _database_error() from exc
