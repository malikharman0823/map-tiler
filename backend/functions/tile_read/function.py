import logging
from pathlib import Path

from fastapi.responses import FileResponse
from database import DatabaseError, DatabaseSession

from functions.tile_read.request import TileReadRequest
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"
CACHE_CONTROL = "public, max-age=3600"


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


def _load_dataset(db: DatabaseSession, request: TileReadRequest) -> Dataset:
    try:
        dataset = db.get_dataset(request.dataset_id)
    except DatabaseError as exc:
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


def _require_generated_tiles(dataset: Dataset) -> None:
    if dataset.tile_status != "completed" or not dataset.tile_path:
        raise _application_error(
            status_code=404,
            code="TILES_NOT_GENERATED",
            message="Tiles have not been generated for this dataset.",
            details="Generate tiles before requesting map tiles.",
            field="dataset_id",
        )


def _validate_zoom(dataset: Dataset, z: int) -> None:
    below_minimum = dataset.tile_min_zoom is not None and z < dataset.tile_min_zoom
    above_maximum = dataset.tile_max_zoom is not None and z > dataset.tile_max_zoom
    if below_minimum or above_maximum:
        raise _application_error(
            status_code=404,
            code="ZOOM_NOT_AVAILABLE",
            message="The requested zoom level is not available.",
            details=(
                "The requested tile is outside the generated zoom range for "
                "this dataset."
            ),
            field="z",
        )


def _tile_path(dataset: Dataset, request: TileReadRequest) -> Path:
    expected_root = (TILES_DIRECTORY / str(dataset.id)).resolve()
    try:
        stored_root = (BACKEND_DIRECTORY / dataset.tile_path).resolve()
    except (OSError, RuntimeError, TypeError):
        logger.exception("The stored tile directory could not be resolved.")
        raise _tile_read_error()

    if stored_root != expected_root:
        logger.error("The stored tile directory is outside its dataset directory.")
        raise _tile_read_error()

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
        raise _tile_read_error()

    try:
        tile_exists = tile_path.is_file()
    except OSError as exc:
        logger.exception("The requested tile could not be inspected.", exc_info=exc)
        raise _tile_read_error() from exc

    if not tile_exists:
        raise _application_error(
            status_code=404,
            code="TILE_NOT_FOUND",
            message="The requested tile was not found.",
            details=(
                "No generated tile exists for the supplied dataset and tile "
                "coordinates."
            ),
            field="y",
        )
    return tile_path


def read_tile(
    request: TileReadRequest,
    db: DatabaseSession,
) -> FileResponse:
    _validate_coordinates(request)
    dataset = _load_dataset(db, request)
    _require_generated_tiles(dataset)
    _validate_zoom(dataset, request.z)
    tile_path = _tile_path(dataset, request)
    return FileResponse(
        path=tile_path,
        media_type="image/png",
        headers={"Cache-Control": CACHE_CONTROL},
    )
