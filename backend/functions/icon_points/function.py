import logging
from uuid import UUID

from storage.session import RepositoryError, SessionRepository
from functions.icon_points.request import (
    CreateIconPointRequest,
    DatasetIconPointsRequest,
    UpdateIconPointRequest,
    IconPointRequest,
)
from functions.icon_points.response import (
    IconPointData,
    IconPointListData,
    IconPointListResponse,
    IconPointResponse,
)
from models.icon_point import IconPoint
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)


def _not_found(resource: str, field: str) -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code=f"{resource.upper()}_NOT_FOUND",
        message=f"The {resource.replace('_', ' ')} was not found.",
        details=f"No {resource.replace('_', ' ')} exists for the supplied ID.",
        field=field,
    )


def _database_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DATABASE_ERROR",
        message="A database error occurred.",
        details="The icon point operation could not be completed.",
    )


def _require_dataset(db: SessionRepository, dataset_id: UUID) -> None:
    if db.get_dataset(dataset_id) is None:
        raise _not_found("dataset", "dataset_id")





def _require_point(db: SessionRepository, point_id: UUID) -> IconPoint:
    point = db.get_icon_point(point_id)
    if point is None:
        raise _not_found("icon_point", "icon_point_id")
    return point


def _response(point: IconPoint) -> IconPointResponse:
    return IconPointResponse(data=IconPointData.model_validate(point))


def create_icon_point(
    dataset: DatasetIconPointsRequest,
    request: CreateIconPointRequest,
    db: SessionRepository,
) -> IconPointResponse:
    try:
        _require_dataset(db, dataset.dataset_id)
        point = IconPoint(
            dataset_id=dataset.dataset_id,
            icon_key=request.icon_key,
            latitude=request.latitude,
            longitude=request.longitude,
            description=request.description,
        )
        db.insert_icon_point(point)
        db.commit()
        return _response(point)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to create an icon point.", exc_info=exc)
        raise _database_error() from exc


def list_icon_points(
    request: DatasetIconPointsRequest, db: SessionRepository
) -> IconPointListResponse:
    try:
        _require_dataset(db, request.dataset_id)
        points = db.list_icon_points(request.dataset_id)
        data = [IconPointData.model_validate(point) for point in points]
        return IconPointListResponse(
            data=IconPointListData(points=data, count=len(data))
        )
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to list icon points.", exc_info=exc)
        raise _database_error() from exc


def update_icon_point(
    point_request: IconPointRequest,
    request: UpdateIconPointRequest,
    db: SessionRepository,
) -> IconPointResponse:
    try:
        point = _require_point(db, point_request.icon_point_id)
        point.icon_key = request.icon_key
        point.latitude = request.latitude
        point.longitude = request.longitude
        point.description = request.description
        db.save_icon_point(point)
        db.commit()
        return _response(point)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to update an icon point.", exc_info=exc)
        raise _database_error() from exc


def delete_icon_point(
    request: IconPointRequest, db: SessionRepository
) -> IconPointResponse:
    try:
        point = _require_point(db, request.icon_point_id)
        response = _response(point)
        db.delete_icon_point(point.id)
        db.commit()
        return response
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to delete an icon point.", exc_info=exc)
        raise _database_error() from exc
