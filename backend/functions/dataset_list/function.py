import logging

from database import DatabaseError, DatabaseSession

from functions.dataset_list.response import (
    DatasetListData,
    DatasetListItem,
    DatasetListResponse,
)
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)


def _database_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DATABASE_ERROR",
        message="The datasets could not be retrieved.",
        details="The database operation failed.",
        field=None,
    )


def _list_item(dataset: Dataset) -> DatasetListItem:
    return DatasetListItem(
        id=dataset.id,
        filename=dataset.filename,
        file_size=dataset.file_size,
        content_type=dataset.content_type,
        file_hash=dataset.file_hash,
        metadata=dataset.extracted_metadata,
        georeference_status=dataset.georeference_status,
        process_status=dataset.process_status,
        tile_status=dataset.tile_status,
        created_at=dataset.created_at,
    )


def list_datasets(db: DatabaseSession) -> DatasetListResponse:
    try:
        datasets = db.list_datasets()
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to list datasets.", exc_info=exc)
        raise _database_error() from exc

    items = [_list_item(dataset) for dataset in datasets]
    return DatasetListResponse(
        data=DatasetListData(datasets=items, count=len(items))
    )
