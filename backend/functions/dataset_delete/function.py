import logging
from pathlib import Path
import shutil
import stat

from database import DatabaseError, DatabaseSession

from functions.dataset_delete.request import DatasetDeleteRequest
from functions.dataset_delete.response import (
    DatasetDeleteData,
    DatasetDeleteResponse,
)
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOADS_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"


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
        message="The dataset could not be deleted.",
        details="The database operation failed.",
        field="dataset_id",
    )


def _file_delete_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="FILE_DELETE_ERROR",
        message="The dataset files could not be deleted.",
        details="One or more dataset storage directories could not be removed.",
        field="dataset_id",
    )


def _delete_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DELETE_ERROR",
        message="The dataset could not be deleted.",
        details=(
            "An error occurred while removing the dataset and its associated "
            "resources."
        ),
        field="dataset_id",
    )


def _load_dataset(
    db: DatabaseSession,
    request: DatasetDeleteRequest,
) -> Dataset:
    try:
        dataset = db.get_dataset(request.dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to load the dataset for deletion.", exc_info=exc)
        raise _database_error() from exc

    if dataset is None:
        raise _dataset_not_found()
    return dataset


def _safe_dataset_directory(root: Path, dataset_id) -> Path:
    resolved_root = root.resolve()
    resolved_directory = (resolved_root / str(dataset_id)).resolve()
    if (
        resolved_directory.parent != resolved_root
        or resolved_directory.name != str(dataset_id)
    ):
        raise _file_delete_error()
    return resolved_directory


def _dataset_directories(dataset: Dataset) -> tuple[Path, Path, Path]:
    return (
        _safe_dataset_directory(UPLOADS_DIRECTORY, dataset.id),
        _safe_dataset_directory(PROCESSED_DIRECTORY, dataset.id),
        _safe_dataset_directory(TILES_DIRECTORY, dataset.id),
    )


def _prepare_database_delete(
    db: DatabaseSession,
    dataset: Dataset,
) -> None:
    try:
        db.delete_dataset(dataset.id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to prepare the dataset deletion.", exc_info=exc)
        raise _database_error() from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected database deletion failure.", exc_info=exc)
        raise _delete_error() from exc


def _remove_dataset_directories(directories: tuple[Path, Path, Path]) -> None:
    try:
        for directory in directories:
            if directory.exists():
                if not directory.is_dir():
                    raise OSError("The dataset storage path is not a directory.")
                directory.chmod(directory.stat().st_mode | stat.S_IWRITE)
                shutil.rmtree(directory)
    except OSError as exc:
        logger.exception("Failed to remove dataset storage.", exc_info=exc)
        raise _file_delete_error() from exc


def delete_dataset(
    request: DatasetDeleteRequest,
    db: DatabaseSession,
) -> DatasetDeleteResponse:
    dataset = _load_dataset(db, request)
    response = DatasetDeleteResponse(
        data=DatasetDeleteData(
            id=dataset.id,
            filename=dataset.filename,
            message="Dataset deleted successfully.",
        )
    )
    directories = _dataset_directories(dataset)
    _prepare_database_delete(db, dataset)

    try:
        _remove_dataset_directories(directories)
    except ApplicationError:
        db.rollback()
        raise

    try:
        db.commit()
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to commit the dataset deletion.", exc_info=exc)
        raise _database_error() from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected dataset deletion failure.", exc_info=exc)
        raise _delete_error() from exc

    return response
