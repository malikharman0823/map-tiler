import logging
from pathlib import Path
import shutil
from uuid import UUID

import mercantile
import numpy
import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp, Resampling
from rasterio.errors import RasterioError
from database import DatabaseError, DatabaseSession

from functions.tile_generation.request import TileGenerationRequest
from functions.tile_generation.response import (
    TileGenerationData,
    TileGenerationResponse,
)
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
TILE_SIZE = 256


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
        details="The tile generation operation could not be completed.",
        field=None,
    )


def _load_dataset(db: DatabaseSession, dataset_id: UUID) -> Dataset:
    try:
        dataset = db.get_dataset(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to load the dataset for tile generation.", exc_info=exc)
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


def _set_tile_state(
    db: DatabaseSession,
    dataset: Dataset,
    *,
    status: str,
    tile_path: str | None,
    min_zoom: int | None,
    max_zoom: int | None,
) -> None:
    dataset.tile_status = status
    dataset.tile_path = tile_path
    dataset.tile_min_zoom = min_zoom
    dataset.tile_max_zoom = max_zoom
    try:
        db.save_dataset(dataset)
        db.commit()
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to update tile generation status.", exc_info=exc)
        raise _database_error() from exc


def _validate_zoom_range(min_zoom: int, max_zoom: int) -> None:
    if min_zoom < 0 or max_zoom < min_zoom or max_zoom > 22:
        raise _application_error(
            status_code=400,
            code="INVALID_ZOOM_RANGE",
            message="The zoom range is invalid.",
            details=(
                "Minimum zoom must be at least 0, maximum zoom must be greater "
                "than or equal to minimum zoom, and maximum zoom cannot exceed "
                "22."
            ),
            field="max_zoom",
        )


def _processed_raster_path(dataset: Dataset) -> Path:
    if dataset.process_status != "completed" or not dataset.processed_path:
        raise _application_error(
            status_code=400,
            code="RASTER_NOT_PROCESSED",
            message="The raster has not been processed.",
            details="Run raster processing before generating map tiles.",
            field="dataset_id",
        )

    candidate = (BACKEND_DIRECTORY / dataset.processed_path).resolve()
    expected_directory = (PROCESSED_DIRECTORY / str(dataset.id)).resolve()
    try:
        candidate.relative_to(expected_directory)
    except ValueError as exc:
        raise _application_error(
            status_code=404,
            code="PROCESSED_RASTER_NOT_FOUND",
            message="The processed raster was not found.",
            details="The processed GeoTIFF is unavailable on the server.",
            field="dataset_id",
        ) from exc

    if not candidate.is_file():
        raise _application_error(
            status_code=404,
            code="PROCESSED_RASTER_NOT_FOUND",
            message="The processed raster was not found.",
            details="The processed GeoTIFF is unavailable on the server.",
            field="dataset_id",
        )
    return candidate


def _relative_tile_path(dataset_id: UUID) -> str:
    return (Path("storage") / "tiles" / str(dataset_id)).as_posix()


def _tile_directory(dataset_id: UUID) -> Path:
    return TILES_DIRECTORY / str(dataset_id)


def _temporary_tile_directory(dataset_id: UUID) -> Path:
    return TILES_DIRECTORY / f"{dataset_id}_temp"


def _open_processed_raster(source_path: Path):
    try:
        return rasterio.open(source_path)
    except (RasterioError, OSError, ValueError) as exc:
        raise _application_error(
            status_code=500,
            code="TILE_GENERATION_ERROR",
            message="Map tiles could not be generated.",
            details="The processed raster could not be opened.",
            field="dataset_id",
        ) from exc


def _require_web_mercator(source) -> None:
    if source.crs != WEB_MERCATOR_CRS:
        raise _application_error(
            status_code=400,
            code="INVALID_TILE_CRS",
            message="The processed raster is not in Web Mercator coordinates.",
            details="Run raster processing with target CRS EPSG:3857.",
            field="dataset_id",
        )


def _intersecting_tiles(bounds, min_zoom: int, max_zoom: int):
    world = mercantile.xy_bounds(0, 0, 0)
    left = max(bounds.left, world.left)
    bottom = max(bounds.bottom, world.bottom)
    right = min(bounds.right, world.right)
    top = min(bounds.top, world.top)
    if left >= right or bottom >= top:
        raise _application_error(
            status_code=500,
            code="TILE_GENERATION_ERROR",
            message="Map tiles could not be generated.",
            details="The raster bounds do not intersect the Web Mercator world.",
            field="dataset_id",
        )

    southwest = mercantile.lnglat(left, bottom, truncate=True)
    northeast = mercantile.lnglat(right, top, truncate=True)
    for tile in mercantile.tiles(
        southwest.lng,
        southwest.lat,
        northeast.lng,
        northeast.lat,
        range(min_zoom, max_zoom + 1),
        truncate=True,
    ):
        tile_bounds = mercantile.xy_bounds(tile)
        if (
            tile_bounds.right > left
            and tile_bounds.left < right
            and tile_bounds.top > bottom
            and tile_bounds.bottom < top
        ):
            yield tile, tile_bounds


def _to_uint8(values: numpy.ndarray) -> numpy.ndarray:
    if values.dtype == numpy.uint8:
        return values
    if numpy.issubdtype(values.dtype, numpy.bool_):
        return values.astype(numpy.uint8) * 255
    if numpy.issubdtype(values.dtype, numpy.integer):
        limits = numpy.iinfo(values.dtype)
        scaled = (
            (values.astype(numpy.float64) - limits.min)
            * 255.0
            / (limits.max - limits.min)
        )
        return numpy.clip(scaled, 0, 255).astype(numpy.uint8)

    finite_values = numpy.nan_to_num(
        values.astype(numpy.float64),
        nan=0.0,
        posinf=255.0,
        neginf=0.0,
    )
    if finite_values.size and finite_values.min() >= 0 and finite_values.max() <= 1:
        finite_values *= 255.0
    return numpy.clip(finite_values, 0, 255).astype(numpy.uint8)


def _read_tile(source, tile_bounds) -> numpy.ndarray:
    if source.count < 1:
        raise _application_error(
            status_code=500,
            code="TILE_GENERATION_ERROR",
            message="Map tiles could not be generated.",
            details="The processed raster contains no image bands.",
            field="dataset_id",
        )

    color_indexes = [1] if source.count < 3 else [1, 2, 3]
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT
    
    dst_transform = from_bounds(
        tile_bounds.left,
        tile_bounds.bottom,
        tile_bounds.right,
        tile_bounds.top,
        TILE_SIZE,
        TILE_SIZE
    )
    
    try:
        with WarpedVRT(
            source,
            crs=source.crs,
            transform=dst_transform,
            width=TILE_SIZE,
            height=TILE_SIZE,
            resampling=Resampling.bilinear,
        ) as vrt:
            colors = vrt.read(
                color_indexes,
                masked=True,
            )
            color_mask = numpy.ma.getmaskarray(colors)
            valid_pixels = ~numpy.any(color_mask, axis=0)
            color_values = _to_uint8(numpy.asarray(colors.filled(0)))
            if len(color_indexes) == 1:
                red = green = blue = color_values[0]
            else:
                red, green, blue = color_values
        
            alpha = numpy.where(valid_pixels, 255, 0).astype(numpy.uint8)
            has_alpha_band = (
                source.count in {2, 4}
                and source.colorinterp[source.count - 1] == ColorInterp.alpha
            )
            if has_alpha_band:
                source_alpha = vrt.read(
                    source.count,
                    masked=True,
                )
                alpha_values = _to_uint8(numpy.asarray(source_alpha.filled(0)))
                alpha_mask = numpy.ma.getmaskarray(source_alpha)
                alpha = numpy.where(valid_pixels & ~alpha_mask, alpha_values, 0).astype(
                    numpy.uint8
                )
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        raise _application_error(
            status_code=500,
            code="TILE_GENERATION_ERROR",
            message="Map tiles could not be generated.",
            details="A raster tile window could not be read.",
            field="dataset_id",
        ) from exc

    return numpy.stack((red, green, blue, alpha))


def _tile_write_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="TILE_WRITE_ERROR",
        message="A map tile could not be saved.",
        details="The server could not write the generated PNG tile.",
        field="dataset_id",
    )


def _write_png_tile(tile_path: Path, data: numpy.ndarray) -> None:
    try:
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            tile_path,
            "w",
            driver="PNG",
            width=TILE_SIZE,
            height=TILE_SIZE,
            count=4,
            dtype="uint8",
        ) as output:
            output.write(data)
            output.colorinterp = (
                ColorInterp.red,
                ColorInterp.green,
                ColorInterp.blue,
                ColorInterp.alpha,
            )
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        raise _tile_write_error() from exc


def _remove_tile_directory(directory: Path) -> None:
    resolved_root = TILES_DIRECTORY.resolve()
    resolved_directory = directory.resolve()
    if resolved_directory.parent != resolved_root:
        raise RuntimeError("Refusing to remove a directory outside tile storage.")
    if resolved_directory.exists():
        shutil.rmtree(resolved_directory, ignore_errors=True)


def _generate_tile_set(
    source,
    final_directory: Path,
    *,
    min_zoom: int,
    max_zoom: int,
) -> None:
    generated_count = 0
    try:
        for tile, tile_bounds in _intersecting_tiles(
            source.bounds,
            min_zoom,
            max_zoom,
        ):
            tile_data = _read_tile(source, tile_bounds)
            tile_path = (
                final_directory
                / str(tile.z)
                / str(tile.x)
                / f"{tile.y}.png"
            )
            _write_png_tile(tile_path, tile_data)
            generated_count += 1

        if generated_count == 0:
            raise _application_error(
                status_code=500,
                code="TILE_GENERATION_ERROR",
                message="Map tiles could not be generated.",
                details="No XYZ tiles intersect the processed raster bounds.",
                field="dataset_id",
            )
    except ApplicationError:
        raise
    except (OSError, RuntimeError) as exc:
        raise _tile_write_error() from exc


def _response(
    dataset_id: UUID,
    *,
    min_zoom: int,
    max_zoom: int,
    tile_path: str,
) -> TileGenerationResponse:
    return TileGenerationResponse(
        data=TileGenerationData(
            dataset_id=dataset_id,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            tile_size=TILE_SIZE,
            format="png",
            scheme="xyz",
            tile_path=tile_path,
            tile_url_template=(
                f"/datasets/{dataset_id}/tiles/{{z}}/{{x}}/{{y}}.png"
            ),
            status="completed",
            message="Tiles generated successfully.",
        )
    )


def generate_tiles(
    request: TileGenerationRequest,
    db: DatabaseSession,
) -> TileGenerationResponse:
    dataset = _load_dataset(db, request.dataset_id)
    _validate_zoom_range(request.min_zoom, request.max_zoom)
    source_path = _processed_raster_path(dataset)
    relative_tile_path = _relative_tile_path(request.dataset_id)
    final_directory = _tile_directory(request.dataset_id)

    with _open_processed_raster(source_path) as source:
        _require_web_mercator(source)
        if (
            dataset.tile_status == "completed"
            and dataset.tile_path == relative_tile_path
            and dataset.tile_min_zoom == request.min_zoom
            and dataset.tile_max_zoom == request.max_zoom
            and final_directory.is_dir()
        ):
            return _response(
                request.dataset_id,
                min_zoom=request.min_zoom,
                max_zoom=request.max_zoom,
                tile_path=relative_tile_path,
            )

        _set_tile_state(
            db,
            dataset,
            status="processing",
            tile_path=None,
            min_zoom=None,
            max_zoom=None,
        )
        try:
            _generate_tile_set(
                source,
                final_directory,
                min_zoom=request.min_zoom,
                max_zoom=request.max_zoom,
            )
        except ApplicationError as exc:
            logger.exception("Tile generation failed.", exc_info=exc)
            _set_tile_state(
                db,
                dataset,
                status="failed",
                tile_path=None,
                min_zoom=None,
                max_zoom=None,
            )
            raise
        except Exception as exc:
            logger.exception("Unexpected tile generation failure.", exc_info=exc)
            # Skip temp directory cleanup
            pass
            _set_tile_state(
                db,
                dataset,
                status="failed",
                tile_path=None,
                min_zoom=None,
                max_zoom=None,
            )
            raise _application_error(
                status_code=500,
                code="TILE_GENERATION_ERROR",
                message="Map tiles could not be generated.",
                details="The raster tiling operation failed.",
                field="dataset_id",
            ) from exc

    try:
        _set_tile_state(
            db,
            dataset,
            status="completed",
            tile_path=relative_tile_path,
            min_zoom=request.min_zoom,
            max_zoom=request.max_zoom,
        )
    except ApplicationError:
        try:
            _remove_tile_directory(final_directory)
            _set_tile_state(
                db,
                dataset,
                status="failed",
                tile_path=None,
                min_zoom=None,
                max_zoom=None,
            )
        except (ApplicationError, OSError, RuntimeError):
            logger.exception("Failed to clean up after a tile database error.")
        raise

    return _response(
        request.dataset_id,
        min_zoom=request.min_zoom,
        max_zoom=request.max_zoom,
        tile_path=relative_tile_path,
    )
