import logging

from database import DatabaseError, DatabaseSession

from functions.dataset_detail.request import DatasetDetailRequest
from functions.dataset_detail.response import (
    DatasetDetailData,
    DatasetDetailResponse,
)
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


def _database_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DATABASE_ERROR",
        message="The dataset could not be retrieved.",
        details="The database operation failed.",
        field=None,
    )


def _response(dataset: Dataset) -> DatasetDetailResponse:
    return DatasetDetailResponse(
        data=DatasetDetailData(
            id=dataset.id,
            filename=dataset.filename,
            file_size=dataset.file_size,
            content_type=dataset.content_type,
            file_hash=dataset.file_hash,
            storage_path=dataset.storage_path,
            metadata=dataset.extracted_metadata,
            georeferenced_path=dataset.georeferenced_path,
            georeference_status=dataset.georeference_status,
            processed_path=dataset.processed_path,
            process_status=dataset.process_status,
            tile_path=dataset.tile_path,
            tile_min_zoom=dataset.tile_min_zoom,
            tile_max_zoom=dataset.tile_max_zoom,
            tile_status=dataset.tile_status,
            created_at=dataset.created_at,
        )
    )


def get_dataset_detail(
    request: DatasetDetailRequest,
    db: DatabaseSession,
) -> DatasetDetailResponse:
    try:
        dataset = db.get_dataset(request.dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to retrieve a dataset.", exc_info=exc)
        raise _database_error() from exc

    if dataset is None:
        raise _dataset_not_found()
    return _response(dataset)
