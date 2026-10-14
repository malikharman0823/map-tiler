import logging
from pathlib import Path

from fastapi.responses import FileResponse, Response
from storage.session import RepositoryError, SessionRepository

from config import settings
from functions.tile_read.request import TileReadRequest
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"
CACHE_CONTROL = "no-cache, must-revalidate"


def _application_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: str,
    field: str | None,
) -> ApplicationError:
    return ApplicationError(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        field=field,
    )


def _database_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="DATABASE_ERROR",
        message="A database error occurred.",
        details="The tile read operation could not be completed.",
        field=None,
    )


def _tile_read_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="TILE_READ_ERROR",
        message="The requested tile could not be read.",
        details="The generated tile could not be served.",
        field=None,
    )


def _validate_coordinates(request: TileReadRequest) -> None:
    coordinates_are_invalid = (
        request.z < 0
        or request.x < 0
        or request.y < 0
        or request.x.bit_length() > request.z
        or request.y.bit_length() > request.z
    )
    if coordinates_are_invalid:
        raise _application_error(
            status_code=400,
            code="INVALID_TILE_COORDINATES",
            message="The tile coordinates are invalid.",
            details=(
                "The supplied x and y coordinates do not exist at the "
                "requested zoom level."
            ),
            field="x",
        )


def _load_dataset(db: SessionRepository, request: TileReadRequest) -> Dataset:
    try:
        dataset = db.get_dataset(request.dataset_id)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to load the dataset for tile reading.", exc_info=exc)
        raise _database_error() from exc

    if dataset is None:
        raise _application_error(
            status_code=404,
            code="DATASET_NOT_FOUND",
            message="The dataset was not found.",
            details="No dataset exists for the supplied dataset ID.",
            field="dataset_id",
        )
    return dataset


def _require_generated_tiles(dataset: Dataset) -> bool:
    return dataset.tile_status == "completed" and bool(dataset.tile_path)


def _zoom_is_valid(dataset: Dataset, z: int) -> bool:
    below_minimum = dataset.tile_min_zoom is not None and z < dataset.tile_min_zoom
    above_maximum = dataset.tile_max_zoom is not None and z > dataset.tile_max_zoom
    return not (below_minimum or above_maximum)


def _tile_path(dataset: Dataset, request: TileReadRequest) -> Path | None:
    expected_root = (TILES_DIRECTORY / str(dataset.id)).resolve()
    if not dataset.tile_path:
        return None
    try:
        stored = Path(dataset.tile_path)
        stored_root = stored.resolve() if stored.is_absolute() else (BACKEND_DIRECTORY / stored).resolve()
    except (OSError, RuntimeError, TypeError):
        logger.exception("The stored tile directory could not be resolved.")
        return None

    sessions_root = Path(settings.session_storage_dir).resolve()
    is_valid_root = (
        stored_root == expected_root
        or (stored_root.is_relative_to(sessions_root) and str(dataset.id) in stored_root.parts)
        or (stored_root.exists() and str(dataset.id) in stored_root.parts)
    )
    if not is_valid_root:
        logger.error("The stored tile directory is outside its dataset directory.")
        return None

    try:
        tile_path = (
            stored_root
            / str(request.z)
            / str(request.x)
            / f"{request.y}.png"
        ).resolve()
        tile_path.relative_to(stored_root)
    except (OSError, RuntimeError, ValueError):
        logger.exception("The requested tile path could not be safely resolved.")
        return None

    try:
        tile_exists = tile_path.is_file()
    except OSError as exc:
        logger.exception("The requested tile could not be inspected.", exc_info=exc)
        return None

    if not tile_exists:
        return None
    return tile_path


def read_tile(
    request: TileReadRequest,
    db: SessionRepository,
) -> FileResponse | Response:
    _validate_coordinates(request)
    dataset = _load_dataset(db, request)
    if not _require_generated_tiles(dataset):
        return Response(status_code=204, headers={"Cache-Control": CACHE_CONTROL})
    if not _zoom_is_valid(dataset, request.z):
        return Response(status_code=204, headers={"Cache-Control": CACHE_CONTROL})
    tile_path = _tile_path(dataset, request)
    if tile_path is None:
        return Response(status_code=204, headers={"Cache-Control": CACHE_CONTROL})
    return FileResponse(
        path=tile_path,
        media_type="image/png",
        headers={"Cache-Control": CACHE_CONTROL},
    )
