from dataclasses import dataclass
import logging
from pathlib import Path
from uuid import UUID

import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.warp import calculate_default_transform, reproject
from database import DatabaseError, DatabaseSession

from functions.raster_process.request import RasterProcessRequest
from functions.raster_process.response import (
    RasterBounds,
    RasterProcessData,
    RasterProcessResponse,
)
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
SUPPORTED_RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
RESAMPLING_METHODS = {
    "nearest": Resampling.nearest,
    "bilinear": Resampling.bilinear,
    "cubic": Resampling.cubic,
}


@dataclass(frozen=True)
class RasterInfo:
    crs: str
    width: int
    height: int
    bands: int
    bounds: tuple[float, float, float, float]


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
        details="The raster processing operation could not be completed.",
        field=None,
    )


def _load_dataset(db: DatabaseSession, dataset_id: UUID) -> Dataset:
    try:
        dataset = db.get_dataset(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to load the dataset for raster processing.", exc_info=exc)
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


def _set_dataset_state(
    db: DatabaseSession,
    dataset: Dataset,
    *,
    status: str,
    output_path: str | None,
) -> None:
    dataset.process_status = status
    dataset.processed_path = output_path
    dataset.tile_status = "not_started"
    dataset.tile_path = None
    dataset.tile_min_zoom = None
    dataset.tile_max_zoom = None
    try:
        db.save_dataset(dataset)
        db.commit()
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to update raster processing status.", exc_info=exc)
        raise _database_error() from exc


def _validate_dataset_format(dataset: Dataset) -> None:
    if Path(dataset.filename).suffix.lower() not in SUPPORTED_RASTER_EXTENSIONS:
        raise _application_error(
            status_code=400,
            code="INVALID_RASTER_DATASET",
            message="This dataset cannot be processed as a raster image.",
            details="Raster processing supports raster image datasets only.",
            field="dataset_id",
        )


def _target_crs(value: str) -> CRS:
    try:
        target_crs = CRS.from_user_input(value.strip())
    except (RasterioError, TypeError, ValueError) as exc:
        raise _application_error(
            status_code=400,
            code="INVALID_TARGET_CRS",
            message="The requested target CRS is invalid.",
            details="Provide a coordinate reference system understood by Rasterio.",
            field="target_crs",
        ) from exc
    return target_crs


def _resampling_method(value: str) -> tuple[str, Resampling]:
    normalized_value = value.strip().lower()
    try:
        return normalized_value, RESAMPLING_METHODS[normalized_value]
    except KeyError as exc:
        raise _application_error(
            status_code=400,
            code="INVALID_RESAMPLING",
            message="The requested resampling method is not supported.",
            details="Supported methods are nearest, bilinear, and cubic.",
            field="resampling",
        ) from exc


def _source_path(dataset: Dataset) -> Path:
    if not dataset.georeferenced_path:
        raise _application_error(
            status_code=404,
            code="GEOTIFF_NOT_FOUND",
            message="The georeferenced raster was not found.",
            details="Run the georeference function before raster processing.",
            field="dataset_id",
        )

    candidate = (BACKEND_DIRECTORY / dataset.georeferenced_path).resolve()
    expected_directory = (PROCESSED_DIRECTORY / str(dataset.id)).resolve()
    try:
        candidate.relative_to(expected_directory)
    except ValueError as exc:
        raise _application_error(
            status_code=404,
            code="GEOTIFF_NOT_FOUND",
            message="The georeferenced raster was not found.",
            details="Run the georeference function before raster processing.",
            field="dataset_id",
        ) from exc

    if not candidate.is_file():
        raise _application_error(
            status_code=404,
            code="GEOTIFF_NOT_FOUND",
            message="The georeferenced raster was not found.",
            details="Run the georeference function before raster processing.",
            field="dataset_id",
        )
    return candidate


def _relative_output_path(dataset_id: UUID) -> str:
    return (
        Path("storage") / "processed" / str(dataset_id) / "processed.tif"
    ).as_posix()


def _output_path(dataset_id: UUID) -> Path:
    return PROCESSED_DIRECTORY / str(dataset_id) / "processed.tif"


def _open_source(source_path: Path):
    try:
        return rasterio.open(source_path)
    except (RasterioError, OSError, ValueError) as exc:
        raise _application_error(
            status_code=500,
            code="RASTER_OPEN_ERROR",
            message="The georeferenced raster could not be opened.",
            details="The source raster is unreadable or invalid.",
            field="dataset_id",
        ) from exc


def _require_source_crs(source) -> CRS:
    if source.crs is None:
        raise _application_error(
            status_code=400,
            code="SOURCE_CRS_MISSING",
            message=(
                "The source raster does not contain a coordinate reference "
                "system."
            ),
            details=(
                "The raster must be georeferenced with a known CRS before "
                "reprojection."
            ),
            field="dataset_id",
        )
    return source.crs


def _raster_info(dataset) -> RasterInfo:
    if dataset.crs is None:
        raise _application_error(
            status_code=400,
            code="SOURCE_CRS_MISSING",
            message=(
                "The source raster does not contain a coordinate reference "
                "system."
            ),
            details=(
                "The raster must be georeferenced with a known CRS before "
                "reprojection."
            ),
            field="dataset_id",
        )
    bounds = dataset.bounds
    return RasterInfo(
        crs=dataset.crs.to_string(),
        width=dataset.width,
        height=dataset.height,
        bands=dataset.count,
        bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
    )


def _existing_output_info(output_path: Path) -> RasterInfo | None:
    if not output_path.is_file():
        return None
    try:
        with rasterio.open(output_path) as output:
            return _raster_info(output)
    except (ApplicationError, RasterioError, OSError, ValueError) as exc:
        logger.warning("Ignoring an invalid existing processed raster.", exc_info=exc)
        return None


def _destination_geometry(source, target_crs: CRS):
    if source.crs == target_crs:
        return source.transform, source.width, source.height
    try:
        return calculate_default_transform(
            source.crs,
            target_crs,
            source.width,
            source.height,
            *source.bounds,
        )
    except (RasterioError, TypeError, ValueError) as exc:
        raise _application_error(
            status_code=500,
            code="REPROJECTION_ERROR",
            message="The raster could not be reprojected.",
            details="The coordinate transformation could not be calculated.",
            field="target_crs",
        ) from exc


def _write_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="RASTER_WRITE_ERROR",
        message="The processed raster could not be saved.",
        details="The server could not write the processed GeoTIFF.",
        field="dataset_id",
    )


def _reprojection_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="REPROJECTION_ERROR",
        message="The raster could not be reprojected.",
        details="The raster reprojection operation failed.",
        field="target_crs",
    )


def _process_to_output(
    source,
    output_path: Path,
    *,
    target_crs: CRS,
    resampling: Resampling,
) -> RasterInfo:
    transform, width, height = _destination_geometry(source, target_crs)
    profile = source.profile.copy()
    for key in ("blockxsize", "blockysize", "compress", "photometric"):
        profile.pop(key, None)
    profile.update(
        driver="GTiff",
        crs=target_crs,
        transform=transform,
        width=width,
        height=height,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
        BIGTIFF="IF_SAFER",
    )

    temporary_path = output_path.with_name("processed.tmp.tif")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.unlink(missing_ok=True)
        with rasterio.open(temporary_path, "w", **profile) as destination:
            if source.crs == target_crs:
                for _, window in source.block_windows(1):
                    destination.write(source.read(window=window), window=window)
            else:
                try:
                    for band_index in range(1, source.count + 1):
                        reproject(
                            source=source.read(band_index),
                            destination=rasterio.band(destination, band_index),
                            src_transform=source.transform,
                            src_crs=source.crs,
                            dst_transform=transform,
                            dst_crs=target_crs,
                            resampling=resampling,
                            warp_mem_limit=64,
                        )
                except (RasterioError, TypeError, ValueError) as exc:
                    raise _reprojection_error() from exc
        temporary_path.replace(output_path)
    except ApplicationError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove a partial processed raster.")
        raise
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove a partial processed raster.")
        raise _write_error() from exc

    try:
        with rasterio.open(output_path) as output:
            return _raster_info(output)
    except (ApplicationError, RasterioError, OSError, ValueError) as exc:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove an unreadable processed raster.")
        raise _write_error() from exc


def _response(
    dataset_id: UUID,
    *,
    source_crs: str,
    output: RasterInfo,
    output_path: str,
    resampling: str,
) -> RasterProcessResponse:
    min_x, min_y, max_x, max_y = output.bounds
    return RasterProcessResponse(
        data=RasterProcessData(
            dataset_id=dataset_id,
            source_crs=source_crs,
            target_crs=output.crs,
            width=output.width,
            height=output.height,
            bands=output.bands,
            bounds=RasterBounds(
                min_x=min_x,
                min_y=min_y,
                max_x=max_x,
                max_y=max_y,
            ),
            output_path=output_path,
            resampling=resampling,
            status="completed",
            message="Raster processed successfully.",
        )
    )


def process_raster(
    request: RasterProcessRequest,
    db: DatabaseSession,
) -> RasterProcessResponse:
    dataset = _load_dataset(db, request.dataset_id)
    _validate_dataset_format(dataset)
    target_crs = _target_crs(request.target_crs)
    resampling_name, resampling = _resampling_method(request.resampling)
    source_path = _source_path(dataset)
    relative_output_path = _relative_output_path(request.dataset_id)
    output_path = _output_path(request.dataset_id)

    with _open_source(source_path) as source:
        source_crs = _require_source_crs(source).to_string()
        if (
            dataset.process_status == "completed"
            and dataset.processed_path == relative_output_path
        ):
            existing_output = _existing_output_info(output_path)
            if existing_output is not None and CRS.from_user_input(
                existing_output.crs
            ) == target_crs:
                return _response(
                    request.dataset_id,
                    source_crs=source_crs,
                    output=existing_output,
                    output_path=relative_output_path,
                    resampling=resampling_name,
                )

        _set_dataset_state(db, dataset, status="processing", output_path=None)
        try:
            output = _process_to_output(
                source,
                output_path,
                target_crs=target_crs,
                resampling=resampling,
            )
        except ApplicationError as exc:
            logger.exception("Raster processing failed.", exc_info=exc)
            _set_dataset_state(db, dataset, status="failed", output_path=None)
            raise
        except Exception as exc:
            logger.exception("Unexpected raster processing failure.", exc_info=exc)
            _set_dataset_state(db, dataset, status="failed", output_path=None)
            raise _reprojection_error() from exc

    try:
        _set_dataset_state(
            db,
            dataset,
            status="completed",
            output_path=relative_output_path,
        )
    except ApplicationError:
        try:
            output_path.unlink(missing_ok=True)
            _set_dataset_state(db, dataset, status="failed", output_path=None)
        except (ApplicationError, OSError):
            logger.exception("Failed to clean up after a database error.")
        raise

    return _response(
        request.dataset_id,
        source_crs=source_crs,
        output=output,
        output_path=relative_output_path,
        resampling=resampling_name,
    )
