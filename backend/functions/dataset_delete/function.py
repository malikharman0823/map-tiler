import logging
from pathlib import Path
import shutil
import stat

from storage.session import RepositoryError, SessionRepository

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
    db: SessionRepository,
    request: DatasetDeleteRequest,
) -> Dataset:
    try:
        dataset = db.get_dataset(request.dataset_id)
    except RepositoryError as exc:
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


def _dataset_directories(dataset: Dataset, db: SessionRepository | None = None) -> list[Path]:
    dirs = [
        _safe_dataset_directory(UPLOADS_DIRECTORY, dataset.id),
        _safe_dataset_directory(PROCESSED_DIRECTORY, dataset.id),
        _safe_dataset_directory(TILES_DIRECTORY, dataset.id),
    ]
    if db is not None and hasattr(db, "get_dataset_dir"):
        ds_dir = db.get_dataset_dir(dataset.id)
        if ds_dir not in dirs:
            dirs.append(ds_dir)
    return dirs


def _remove_dataset_files(dataset: Dataset) -> None:
    for path_attr in (
        dataset.storage_path,
        dataset.processed_path,
        dataset.georeferenced_path,
        dataset.tile_path,
    ):
        if path_attr:
            p = Path(path_attr)
            target = p.resolve() if p.is_absolute() else (BACKEND_DIRECTORY / p).resolve()
            if target.exists():
                try:
                    if target.is_dir():
                        _robust_rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Failed to remove file %s: %s", target, exc)


def _prepare_database_delete(
    db: SessionRepository,
    dataset: Dataset,
) -> None:
    try:
        db.delete_dataset(dataset.id)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to prepare the dataset deletion.", exc_info=exc)
        raise _database_error() from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected database deletion failure.", exc_info=exc)
        raise _delete_error() from exc


def _robust_rmtree(directory: Path) -> None:
    import gc
    import os
    import time
    import sys

    def _handle_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception:
            pass

    gc.collect()
    for attempt in range(4):
        try:
            if not directory.exists():
                return
            if sys.version_info >= (3, 12):
                shutil.rmtree(directory, onexc=_handle_error)
            else:
                shutil.rmtree(directory, onerror=_handle_error)
            return
        except OSError:
            if attempt < 3:
                time.sleep(0.15 * (attempt + 1))
                gc.collect()
            else:
                logger.warning("Could not cleanly delete directory %s after retries", directory)


def _remove_dataset_directories(directories: list[Path] | tuple[Path, ...]) -> None:
    for directory in directories:
        if directory.exists():
            if not directory.is_dir():
                try:
                    directory.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Failed to remove dataset file %s: %s", directory, exc)
                continue
            _robust_rmtree(directory)


def delete_dataset(
    request: DatasetDeleteRequest,
    db: SessionRepository,
) -> DatasetDeleteResponse:
    dataset = _load_dataset(db, request)
    response = DatasetDeleteResponse(
        data=DatasetDeleteData(
            id=dataset.id,
            filename=dataset.filename,
            message="Dataset deleted successfully.",
        )
    )
    directories = _dataset_directories(dataset, db)
    _prepare_database_delete(db, dataset)

    try:
        _remove_dataset_directories(directories)
        _remove_dataset_files(dataset)
    except Exception as exc:
        logger.warning("Storage directory cleanup encountered an error: %s", exc)

    try:
        db.commit()
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to commit the dataset deletion.", exc_info=exc)
        raise _database_error() from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected dataset deletion failure.", exc_info=exc)
        raise _delete_error() from exc

    return response
