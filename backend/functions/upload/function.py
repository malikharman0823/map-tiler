import logging
from pathlib import Path
import shutil
from typing import BinaryIO, cast
import uuid

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from database import DatabaseError, DatabaseSession, DuplicateDatabaseValue
from functions.file_hash.function import calculate_file_hash
from functions.metadata.function import extract_metadata
from functions.metadata.request import MetadataRequest
from functions.upload.response import UploadData, UploadResponse
from functions.validate_file.function import validate_file
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
COPY_CHUNK_SIZE = 1024 * 1024


def _write_upload(source: BinaryIO, destination: Path) -> int:
    file_size = 0
    with destination.open("xb") as stored_file:
        while chunk := source.read(COPY_CHUNK_SIZE):
            stored_file.write(chunk)
            file_size += len(chunk)
    return file_size


def _remove_saved_upload(file_path: Path, dataset_directory: Path) -> None:
    try:
        if dataset_directory.is_dir():
            shutil.rmtree(dataset_directory)
        else:
            file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Failed to clean up upload storage.")


def _find_dataset_by_hash(
    db: DatabaseSession,
    file_hash: str,
) -> Dataset | None:
    return db.find_dataset_by_hash(file_hash)


def _build_upload_response(dataset: Dataset, *, existing: bool) -> UploadResponse:
    return UploadResponse(
        data=UploadData(
            id=dataset.id,
            filename=dataset.filename,
            file_size=dataset.file_size,
            content_type=dataset.content_type,
            file_hash=dataset.file_hash,
            storage_path=dataset.storage_path,
            metadata=dataset.extracted_metadata,
            existing=existing,
            message=(
                "This file already exists."
                if existing
                else "File uploaded successfully."
            ),
        )
    )


def _database_error() -> ApplicationError:
    return ApplicationError(
        status_code=500,
        code="DATABASE_ERROR",
        message="The file information could not be saved.",
        details="The database operation failed.",
    )


async def upload_file(
    file: UploadFile | None,
    db: DatabaseSession,
) -> UploadResponse:
    validation = await validate_file(file)
    validated_file = cast(UploadFile, file)
    hash_response = await calculate_file_hash(validated_file)
    file_hash = hash_response.data.file_hash

    try:
        existing_dataset = _find_dataset_by_hash(db, file_hash)
    except DatabaseError as exc:
        logger.exception("Failed to look up the uploaded file hash.", exc_info=exc)
        raise _database_error() from exc

    if existing_dataset is not None:
        return _build_upload_response(existing_dataset, existing=True)

    filename = validation.data.filename
    dataset_id = uuid.uuid4()
    dataset_directory = UPLOAD_DIRECTORY / str(dataset_id)
    file_path = dataset_directory / filename
    relative_storage_path = (
        Path("storage") / "uploads" / str(dataset_id) / filename
    ).as_posix()

    try:
        dataset_directory.mkdir(parents=True, exist_ok=False)
        await validated_file.seek(0)
        file_size = await run_in_threadpool(
            _write_upload,
            validated_file.file,
            file_path,
        )
    except Exception as exc:
        _remove_saved_upload(file_path, dataset_directory)
        logger.exception("Failed to save uploaded file.", exc_info=exc)
        raise ApplicationError(
            status_code=500,
            code="FILE_SAVE_ERROR",
            message="The uploaded file could not be saved.",
            details="The server was unable to write the file to local storage.",
            field="file",
        ) from exc

    try:
        metadata_response = await extract_metadata(
            MetadataRequest(
                file_path=str(file_path),
                format=validation.data.format,
                category=validation.data.category,
            )
        )
    except ApplicationError:
        _remove_saved_upload(file_path, dataset_directory)
        raise

    dataset = Dataset(
        id=dataset_id,
        filename=filename,
        file_size=file_size,
        content_type=validation.data.content_type,
        file_hash=file_hash,
        storage_path=relative_storage_path,
        extracted_metadata=metadata_response.data.metadata,
    )

    try:
        db.insert_dataset(dataset)
        db.commit()
    except DuplicateDatabaseValue as exc:
        _remove_saved_upload(file_path, dataset_directory)
        db.rollback()
        try:
            existing_dataset = _find_dataset_by_hash(db, file_hash)
        except DatabaseError as lookup_exc:
            logger.exception(
                "Failed to recover from a duplicate file hash.",
                exc_info=lookup_exc,
            )
            raise _database_error() from lookup_exc

        if existing_dataset is not None:
            return _build_upload_response(existing_dataset, existing=True)

        logger.exception("Failed to save uploaded file information.", exc_info=exc)
        raise _database_error() from exc
    except DatabaseError as exc:
        _remove_saved_upload(file_path, dataset_directory)
        db.rollback()
        logger.exception("Failed to save uploaded file information.", exc_info=exc)
        raise _database_error() from exc

    return _build_upload_response(dataset, existing=False)
