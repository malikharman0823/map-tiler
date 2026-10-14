import logging
from pathlib import Path
import shutil
from typing import BinaryIO, cast
import uuid

from fastapi import BackgroundTasks, UploadFile
from starlette.concurrency import run_in_threadpool

from storage.session import RepositoryError, SessionRepository, DuplicateValueError
from functions.file_hash.function import calculate_file_hash
from functions.metadata.function import extract_metadata
from functions.metadata.request import MetadataRequest
from functions.upload.response import UploadData, UploadResponse
from functions.validate_file.function import validate_file
from models.dataset import Dataset
from schemas.error import ApplicationError
from functions.raster_process.function import process_raster
from functions.raster_process.request import RasterProcessRequest
from functions.tile_generation.function import generate_tiles
from functions.tile_generation.request import TileGenerationRequest


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
    db: SessionRepository,
    file_hash: str,
) -> Dataset | None:
    return db.find_dataset_by_hash(file_hash)


def _build_upload_response(
    dataset: Dataset,
    *,
    existing: bool,
    message: str | None = None,
    imported_datasets: list[Dataset] | None = None,
) -> UploadResponse:
    default_msg = (
        "This file already exists."
        if existing
        else "File uploaded successfully."
    )
    imported_list = None
    if imported_datasets:
        imported_list = [
            {
                "id": str(d.id),
                "filename": d.filename,
                "is_georeferenced": bool(
                    d.georeference_status == "completed"
                    or (
                        d.extracted_metadata.get("crs")
                        and d.extracted_metadata.get("transform")
                    )
                ),
            }
            for d in imported_datasets
        ]
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
            is_georeferenced=bool(
                dataset.georeference_status == "completed"
                or (
                    dataset.extracted_metadata.get("crs")
                    and dataset.extracted_metadata.get("transform")
                )
            ),
            georeference_status=dataset.georeference_status,
            message=message or default_msg,
            imported_datasets=imported_list,
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
    db: SessionRepository,
    background_tasks: BackgroundTasks,
) -> UploadResponse:
    validation = await validate_file(file)
    validated_file = cast(UploadFile, file)
    hash_response = await calculate_file_hash(validated_file)
    file_hash = hash_response.data.file_hash

    try:
        existing_dataset = _find_dataset_by_hash(db, file_hash)
    except RepositoryError as exc:
        logger.exception("Failed to look up the uploaded file hash.", exc_info=exc)
        raise _database_error() from exc

    if existing_dataset is not None:
        return _build_upload_response(existing_dataset, existing=True)

    if hasattr(db, "check_quota"):
        db.check_quota()

    filename = validation.data.filename
    dataset_id = uuid.uuid4()
    is_default_upload_dir = UPLOAD_DIRECTORY == BACKEND_DIRECTORY / "storage" / "uploads"
    if is_default_upload_dir and hasattr(db, "get_source_dir") and hasattr(db, "session_dir"):
        dataset_directory = db.get_source_dir(dataset_id)
        file_path = dataset_directory / filename
        try:
            relative_storage_path = file_path.relative_to(BACKEND_DIRECTORY).as_posix()
        except ValueError:
            relative_storage_path = file_path.as_posix()
    else:
        dataset_directory = UPLOAD_DIRECTORY / str(dataset_id)
        file_path = dataset_directory / filename
        relative_storage_path = (
            Path("storage") / "uploads" / str(dataset_id) / filename
        ).as_posix()

    try:
        dataset_directory.mkdir(parents=True, exist_ok=True)
        await validated_file.seek(0)
        file_size = await run_in_threadpool(
            _write_upload,
            validated_file.file,
            file_path,
        )
        if hasattr(db, "check_quota"):
            db.check_quota()
    except Exception as exc:
        _remove_saved_upload(file_path, dataset_directory)
        logger.exception("Failed to save uploaded file.", exc_info=exc)
        if isinstance(exc, ApplicationError):
            raise
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

    extracted_metadata = dict(metadata_response.data.metadata)
    extracted_metadata["format"] = metadata_response.data.format
    extracted_metadata["category"] = metadata_response.data.category

    georeferenced_path = None
    georeference_status = "not_started"
    processed_path = None
    process_status = "not_started"
    tile_status = "not_started"
    tile_min_zoom = None
    tile_max_zoom = None
    tile_path = None

    is_auto_georeferenced = False
    if metadata_response.data.format == "tiff" and extracted_metadata.get("crs") and extracted_metadata.get("transform"):
        georeferenced_path = relative_storage_path
        georeference_status = "completed"
        is_auto_georeferenced = True

    if metadata_response.data.format == "mbtiles":
        tile_status = "completed"
        tile_path = relative_storage_path
        tile_min_zoom = extracted_metadata.get("min_zoom")
        tile_max_zoom = extracted_metadata.get("max_zoom")

    dataset = Dataset(
        id=dataset_id,
        filename=filename,
        file_size=file_size,
        content_type=validation.data.content_type,
        file_hash=file_hash,
        storage_path=relative_storage_path,
        extracted_metadata=extracted_metadata,
        georeferenced_path=georeferenced_path,
        georeference_status=georeference_status,
        processed_path=processed_path,
        process_status=process_status,
        tile_status=tile_status,
        tile_min_zoom=tile_min_zoom,
        tile_max_zoom=tile_max_zoom,
        tile_path=tile_path,
    )

    try:
        db.insert_dataset(dataset)
        db.commit()
    except DuplicateValueError as exc:
        _remove_saved_upload(file_path, dataset_directory)
        db.rollback()
        try:
            existing_dataset = _find_dataset_by_hash(db, file_hash)
        except RepositoryError as lookup_exc:
            logger.exception(
                "Failed to recover from a duplicate file hash.",
                exc_info=lookup_exc,
            )
            raise _database_error() from lookup_exc

        if existing_dataset is not None:
            return _build_upload_response(existing_dataset, existing=True)

        logger.exception("Failed to save uploaded file information.", exc_info=exc)
        raise _database_error() from exc
    except RepositoryError as exc:
        _remove_saved_upload(file_path, dataset_directory)
        db.rollback()
        logger.exception("Failed to save uploaded file information.", exc_info=exc)
        raise _database_error() from exc

    def run_processing(session_id: str | None, dataset_id: uuid.UUID):
        from storage.session import session_storage
        bg_db = session_storage.get_session(session_id) if session_id else None
        if bg_db is None:
            from storage.session import get_session_repository
            bg_db = get_session_repository()
        with bg_db.protect_operation("processing"):
            try:
                process_raster(
                    RasterProcessRequest(
                        dataset_id=dataset_id,
                        target_crs="EPSG:3857",
                        resampling="bilinear",
                    ),
                    bg_db,
                )
                generate_tiles(
                    TileGenerationRequest(
                        dataset_id=dataset_id,
                        min_zoom=0,
                        max_zoom=18,
                    ),
                    bg_db,
                )
            except Exception as exc:
                logger.exception("Failed to auto-process GeoTIFF.", exc_info=exc)

    if is_auto_georeferenced:
        session_id = getattr(db, "session_id", None)
        background_tasks.add_task(run_processing, session_id, dataset_id)

    return _build_upload_response(dataset, existing=False)
