import logging
import math
from pathlib import Path
from uuid import UUID

import rasterio
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS
from rasterio.errors import RasterioError
from rasterio.transform import from_gcps
from database import DatabaseError, DatabaseSession

from functions.georeference.request import GeoreferenceRequest
from functions.georeference.response import (
    GeoreferenceData,
    GeoreferenceResponse,
)
from models.control_point import ControlPoint
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
SUPPORTED_RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
TARGET_CRS = CRS.from_epsg(4326)


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
        details="The georeference operation could not be completed.",
        field=None,
    )


def _load_dataset(db: DatabaseSession, dataset_id: UUID) -> Dataset:
    try:
        dataset = db.get_dataset(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to load the dataset for georeferencing.", exc_info=exc)
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


def _load_control_points(
    db: DatabaseSession,
    dataset_id: UUID,
) -> list[ControlPoint]:
    try:
        return db.list_control_points(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to load control points for georeferencing.", exc_info=exc)
        raise _database_error() from exc


def _set_dataset_state(
    db: DatabaseSession,
    dataset: Dataset,
    *,
    status: str,
    output_path: str | None,
) -> None:
    dataset.georeference_status = status
    dataset.georeferenced_path = output_path
    dataset.process_status = "not_started"
    dataset.processed_path = None
    dataset.tile_status = "not_started"
    dataset.tile_path = None
    dataset.tile_min_zoom = None
    dataset.tile_max_zoom = None
    try:
        db.save_dataset(dataset)
        db.commit()
    except DatabaseError as exc:
        db.rollback()
        logger.exception("Failed to update georeference status.", exc_info=exc)
        raise _database_error() from exc


def _validate_request(request: GeoreferenceRequest) -> tuple[str, str]:
    transformation = request.transformation.strip().lower()
    if transformation != "affine":
        raise _application_error(
            status_code=400,
            code="INVALID_TRANSFORMATION",
            message="The requested transformation is not supported.",
            details="The MVP currently supports the affine transformation only.",
            field="transformation",
        )

    output_format = request.output_format.strip().lower().lstrip(".")
    if output_format not in {"tif", "tiff"}:
        raise _application_error(
            status_code=400,
            code="INVALID_OUTPUT_FORMAT",
            message="The requested output format is not supported.",
            details="The georeference function currently produces GeoTIFF files only.",
            field="output_format",
        )
    return transformation, "tif"


def _validate_dataset_format(dataset: Dataset) -> None:
    if Path(dataset.filename).suffix.lower() not in SUPPORTED_RASTER_EXTENSIONS:
        raise _application_error(
            status_code=400,
            code="INVALID_GEOREFERENCE_FORMAT",
            message="This dataset cannot be georeferenced as a raster image.",
            details=(
                "The georeference function currently supports raster image "
                "datasets only."
            ),
            field="dataset_id",
        )


def _validate_control_point_count(points: list[ControlPoint]) -> None:
    if not points:
        raise _application_error(
            status_code=400,
            code="NO_CONTROL_POINTS",
            message="No control points were found.",
            details="Add control points to the dataset before running georeferencing.",
            field="dataset_id",
        )
    if len(points) < 3:
        raise _application_error(
            status_code=400,
            code="INSUFFICIENT_CONTROL_POINTS",
            message="There are not enough control points.",
            details="At least 3 control points are required for affine georeferencing.",
            field="dataset_id",
        )


def _source_path(dataset: Dataset) -> Path:
    candidate = (BACKEND_DIRECTORY / dataset.storage_path).resolve()
    try:
        candidate.relative_to(UPLOAD_DIRECTORY.resolve())
    except ValueError as exc:
        raise _application_error(
            status_code=404,
            code="SOURCE_FILE_NOT_FOUND",
            message="The source raster was not found.",
            details="The uploaded raster file is unavailable.",
            field="dataset_id",
        ) from exc

    if not candidate.is_file():
        raise _application_error(
            status_code=404,
            code="SOURCE_FILE_NOT_FOUND",
            message="The source raster was not found.",
            details="The uploaded raster file is unavailable.",
            field="dataset_id",
        )
    return candidate


def _relative_output_path(dataset_id: UUID) -> str:
    return (
        Path("storage")
        / "processed"
        / str(dataset_id)
        / "georeferenced.tif"
    ).as_posix()


def _output_path(dataset_id: UUID) -> Path:
    return PROCESSED_DIRECTORY / str(dataset_id) / "georeferenced.tif"


def _validate_and_convert_gcps(
    points: list[ControlPoint],
    *,
    width: int,
    height: int,
) -> list[GroundControlPoint]:
    gcps: list[GroundControlPoint] = []
    for point in points:
        image_values = (point.image_x, point.image_y)
        if (
            not all(math.isfinite(value) for value in image_values)
            or point.image_x < 0
            or point.image_y < 0
            or point.image_x >= width
            or point.image_y >= height
        ):
            raise _application_error(
                status_code=400,
                code="CONTROL_POINT_OUT_OF_BOUNDS",
                message="A control point is outside the image.",
                details=(
                    "The image coordinate does not fall within the raster "
                    "dimensions."
                ),
                field="control_points",
            )

        geographic_values = (point.longitude, point.latitude)
        if (
            not all(math.isfinite(value) for value in geographic_values)
            or not -180 <= point.longitude <= 180
            or not -90 <= point.latitude <= 90
        ):
            raise _application_error(
                status_code=400,
                code="INVALID_COORDINATES",
                message="The map coordinates are invalid.",
                details=(
                    "A stored control point has invalid longitude or latitude "
                    "coordinates."
                ),
                field="control_points",
            )

        gcps.append(
            GroundControlPoint(
                row=point.image_y,
                col=point.image_x,
                x=point.longitude,
                y=point.latitude,
                z=0,
                id=str(point.id),
            )
        )
    return gcps


def _affine_transform(gcps: list[GroundControlPoint]):
    try:
        transform = from_gcps(gcps)
    except (RasterioError, TypeError, ValueError) as exc:
        raise _application_error(
            status_code=400,
            code="INSUFFICIENT_CONTROL_POINTS",
            message="There are not enough usable control points.",
            details=(
                "At least 3 non-collinear control points are required for "
                "affine georeferencing."
            ),
            field="control_points",
        ) from exc

    coefficients = (
        transform.a,
        transform.b,
        transform.c,
        transform.d,
        transform.e,
        transform.f,
    )
    if transform.is_degenerate or not all(
        math.isfinite(value) for value in coefficients
    ):
        raise _application_error(
            status_code=400,
            code="INSUFFICIENT_CONTROL_POINTS",
            message="There are not enough usable control points.",
            details=(
                "At least 3 non-collinear control points are required for "
                "affine georeferencing."
            ),
            field="control_points",
        )
    return transform


def _output_file_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="OUTPUT_FILE_ERROR",
        message="The georeferenced raster could not be saved.",
        details="The server could not write the processed raster file.",
        field="dataset_id",
    )


def _geoprocessing_error() -> ApplicationError:
    return _application_error(
        status_code=500,
        code="GEOPROCESSING_ERROR",
        message="The raster could not be georeferenced.",
        details="The geospatial processing operation failed.",
        field="dataset_id",
    )


def _write_georeferenced_raster(
    source_path: Path,
    output_path: Path,
    points: list[ControlPoint],
) -> None:
    try:
        source = rasterio.open(source_path)
    except (RasterioError, OSError, ValueError) as exc:
        raise _geoprocessing_error() from exc

    with source:
        gcps = _validate_and_convert_gcps(
            points,
            width=source.width,
            height=source.height,
        )
        transform = _affine_transform(gcps)
        profile = {
            "driver": "GTiff",
            "width": source.width,
            "height": source.height,
            "count": source.count,
            "dtype": source.dtypes[0],
            "crs": TARGET_CRS,
            "transform": transform,
        }
        if source.nodata is not None:
            profile["nodata"] = source.nodata

        temporary_path = output_path.with_name("georeferenced.tmp.tif")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.unlink(missing_ok=True)
            with rasterio.open(temporary_path, "w", **profile) as destination:
                for _, window in source.block_windows(1):
                    destination.write(source.read(window=window), window=window)
            temporary_path.replace(output_path)
        except (RasterioError, OSError, TypeError, ValueError) as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to remove a partial georeference output.")
            raise _output_file_error() from exc


def _response(
    dataset_id: UUID,
    *,
    transformation: str,
    point_count: int,
    output_path: str,
) -> GeoreferenceResponse:
    return GeoreferenceResponse(
        data=GeoreferenceData(
            dataset_id=dataset_id,
            transformation=transformation,
            control_point_count=point_count,
            crs="EPSG:4326",
            output_path=output_path,
            status="completed",
            message="Dataset georeferenced successfully.",
        )
    )


def georeference_dataset(
    request: GeoreferenceRequest,
    db: DatabaseSession,
) -> GeoreferenceResponse:
    dataset = _load_dataset(db, request.dataset_id)
    transformation, _ = _validate_request(request)
    _validate_dataset_format(dataset)
    points = _load_control_points(db, request.dataset_id)
    _validate_control_point_count(points)

    relative_output_path = _relative_output_path(request.dataset_id)
    output_path = _output_path(request.dataset_id)
    if (
        dataset.georeference_status == "completed"
        and dataset.georeferenced_path == relative_output_path
        and output_path.is_file()
    ):
        return _response(
            request.dataset_id,
            transformation=transformation,
            point_count=len(points),
            output_path=relative_output_path,
        )

    source_path = _source_path(dataset)
    _set_dataset_state(db, dataset, status="processing", output_path=None)

    try:
        _write_georeferenced_raster(source_path, output_path, points)
    except ApplicationError as exc:
        logger.exception("Georeferencing failed.", exc_info=exc)
        _set_dataset_state(db, dataset, status="failed", output_path=None)
        raise
    except Exception as exc:
        logger.exception("Unexpected georeferencing failure.", exc_info=exc)
        _set_dataset_state(db, dataset, status="failed", output_path=None)
        raise _geoprocessing_error() from exc

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
        transformation=transformation,
        point_count=len(points),
        output_path=relative_output_path,
    )
