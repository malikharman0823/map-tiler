from dataclasses import dataclass
import logging
import math
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy
import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioError
from rasterio.transform import Affine, array_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling

from database import DatabaseError, DatabaseSession
from functions.georeference.request import GeoreferenceRequest
from functions.georeference.response import (
    GeoreferenceData,
    GeoreferenceLookupData,
    GeoreferenceLookupResponse,
    GeoreferenceResponse,
)
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.tables import GeoreferenceConfig
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
SUPPORTED_RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
DEFAULT_TARGET_CRS = "EPSG:4326"
SOURCE_COORDINATE_SYSTEM = {
    "x": "image_x",
    "y": "-image_y",
    "target": {"x": "longitude", "y": "latitude"},
}
REUSE_WARNING = (
    "The saved georeferencing configuration belongs to a different source "
    "image configuration and may not be safely reused."
)


@dataclass(frozen=True)
class GeoreferenceCalculation:
    transformation: str
    parameters: dict[str, float]
    raster_transform: Affine
    source_crs: str | None
    target_crs: str
    source_width: int
    source_height: int


def _error(
    status_code: int,
    code: str,
    message: str,
    details: str,
    field: str | None = None,
) -> ApplicationError:
    return ApplicationError(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        field=field,
    )


def _load_dataset(db: DatabaseSession, dataset_id: UUID) -> Dataset:
    try:
        dataset = db.get_dataset(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        raise _error(
            500,
            "DATABASE_ERROR",
            "A database error occurred.",
            "The georeference operation could not be completed.",
        ) from exc
    if dataset is None:
        raise _error(
            404,
            "DATASET_NOT_FOUND",
            "The dataset was not found.",
            "No dataset exists for the supplied dataset ID.",
            "dataset_id",
        )
    return dataset


def _load_control_points(
    db: DatabaseSession, dataset_id: UUID
) -> list[ControlPoint]:
    try:
        return db.list_control_points(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        raise _error(
            500,
            "DATABASE_ERROR",
            "A database error occurred.",
            "The control points could not be loaded.",
        ) from exc


def _validate_request(request: GeoreferenceRequest) -> CRS:
    if request.output_format.strip().lower().lstrip(".") not in {"tif", "tiff"}:
        raise _error(
            400,
            "INVALID_OUTPUT_FORMAT",
            "The requested output format is not supported.",
            "The georeference function currently produces GeoTIFF files only.",
            "output_format",
        )
    try:
        target_crs = CRS.from_user_input(request.target_crs)
    except (RasterioError, TypeError, ValueError) as exc:
        raise _error(
            400,
            "INVALID_CONFIGURATION",
            "The target coordinate system is invalid.",
            "Provide a valid target CRS for longitude and latitude coordinates.",
            "target_crs",
        ) from exc
    if target_crs != CRS.from_user_input(DEFAULT_TARGET_CRS):
        raise _error(
            400,
            "INVALID_CONFIGURATION",
            "The target coordinate system is not supported by this workflow.",
            "The current reference map supplies longitude and latitude in EPSG:4326.",
            "target_crs",
        )
    return target_crs


def _validate_dataset_format(dataset: Dataset) -> None:
    if Path(dataset.filename).suffix.lower() not in SUPPORTED_RASTER_EXTENSIONS:
        raise _error(
            400,
            "INVALID_SOURCE_IMAGE",
            "This dataset cannot be georeferenced as a raster image.",
            "Visual georeferencing supports JPG, PNG, and TIFF raster images.",
            "dataset_id",
        )


def _validate_count(points: list[ControlPoint]) -> str:
    if not points:
        raise _error(
            400,
            "NO_CONTROL_POINTS",
            "No control points were found.",
            "Add control points before calculating georeferencing.",
            "control_points",
        )
    if len(points) < 2:
        raise _error(
            400,
            "INSUFFICIENT_CONTROL_POINTS",
            "There are not enough control points.",
            "Add at least 2 complete control-point pairs.",
            "control_points",
        )
    if len(points) > 10:
        raise _error(
            400,
            "TOO_MANY_CONTROL_POINTS",
            "Too many control points were added.",
            "The visual georeferencer supports a maximum of 10 control points.",
            "control_points",
        )
    return "similarity" if len(points) == 2 else "affine"


def _source_path(dataset: Dataset) -> Path:
    candidate = (BACKEND_DIRECTORY / dataset.storage_path).resolve()
    try:
        candidate.relative_to(UPLOAD_DIRECTORY.resolve())
    except ValueError as exc:
        raise _error(
            400,
            "INVALID_SOURCE_IMAGE",
            "The source raster is unavailable.",
            "The stored source path is not a managed upload.",
            "dataset_id",
        ) from exc
    if not candidate.is_file():
        raise _error(
            400,
            "INVALID_SOURCE_IMAGE",
            "The source raster is unavailable.",
            "The uploaded source image could not be found.",
            "dataset_id",
        )
    return candidate


def _relative_output_path(dataset_id: UUID, *, preview: bool = False) -> str:
    filename = "georeference-preview.tif" if preview else "georeferenced.tif"
    return (Path("storage") / "processed" / str(dataset_id) / filename).as_posix()


def _output_path(dataset_id: UUID, *, preview: bool = False) -> Path:
    filename = "georeference-preview.tif" if preview else "georeferenced.tif"
    return PROCESSED_DIRECTORY / str(dataset_id) / filename


def _validate_points(
    points: list[ControlPoint], *, width: int, height: int
) -> None:
    for point in points:
        values = (
            point.image_x,
            point.image_y,
            point.longitude,
            point.latitude,
        )
        if any(value is None for value in values):
            raise _error(
                400,
                "INCOMPLETE_CONTROL_POINT",
                "A control point is incomplete.",
                "Every point needs image and geographic coordinates.",
                "control_points",
            )
        if not all(math.isfinite(value) for value in values):
            raise _error(
                400,
                "INVALID_CONTROL_POINT",
                "A control point is invalid.",
                "Control-point coordinates must be finite numbers.",
                "control_points",
            )
        if not (0 <= point.image_x < width and 0 <= point.image_y < height):
            raise _error(
                400,
                "INVALID_CONTROL_POINT",
                "A control point is outside the source image.",
                "Image coordinates must fall within the raster dimensions.",
                "control_points",
            )
        if not (-180 <= point.longitude <= 180 and -90 <= point.latitude <= 90):
            raise _error(
                400,
                "INVALID_CONTROL_POINT",
                "A control point has invalid geographic coordinates.",
                "Longitude must be within -180 to 180 and latitude within -90 to 90.",
                "control_points",
            )


def _distribution_error(code: str, details: str) -> ApplicationError:
    return _error(
        400,
        code,
        (
            "The control points are nearly collinear."
            if code == "COLLINEAR_CONTROL_POINTS"
            else "The control points do not cover enough of the image."
        ),
        details,
        "control_points",
    )


def _validate_distribution(
    points: list[ControlPoint], *, width: int, height: int
) -> None:
    coordinates = [(point.image_x, point.image_y) for point in points]
    horizontal = max(x for x, _ in coordinates) - min(x for x, _ in coordinates)
    vertical = max(y for _, y in coordinates) - min(y for _, y in coordinates)
    image_diagonal = math.hypot(width, height)
    extent_diagonal = math.hypot(horizontal, vertical)
    if len(points) == 2:
        if extent_diagonal < image_diagonal * 0.12:
            raise _distribution_error(
                "POOR_CONTROL_POINT_DISTRIBUTION",
                "Move the two points farther apart across the source image.",
            )
        return
    if (
        horizontal < width * 0.1
        or vertical < height * 0.1
        or extent_diagonal < image_diagonal * 0.2
    ):
        raise _distribution_error(
            "POOR_CONTROL_POINT_DISTRIBUTION",
            "Move the points farther apart across the source image.",
        )
    largest_twice_area = 0.0
    for first in range(len(coordinates) - 2):
        x1, y1 = coordinates[first]
        for second in range(first + 1, len(coordinates) - 1):
            x2, y2 = coordinates[second]
            for third in range(second + 1, len(coordinates)):
                x3, y3 = coordinates[third]
                largest_twice_area = max(
                    largest_twice_area,
                    abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)),
                )
    if largest_twice_area < width * height * 0.002:
        raise _distribution_error(
            "COLLINEAR_CONTROL_POINTS",
            "Move at least one point away from the shared line.",
        )


def _parameter_dict(values: list[float]) -> dict[str, float]:
    if not all(math.isfinite(value) for value in values):
        raise _error(
            400,
            "INVALID_TRANSFORMATION",
            "The transformation is invalid.",
            "The control points did not produce finite coefficients.",
            "control_points",
        )
    return dict(zip(("a", "b", "c", "d", "e", "f"), values, strict=True))


def _similarity_parameters(points: list[ControlPoint]) -> dict[str, float]:
    first, second = points
    source_x = second.image_x - first.image_x
    source_y = -second.image_y - (-first.image_y)
    target_x = second.longitude - first.longitude
    target_y = second.latitude - first.latitude
    source_length = math.hypot(source_x, source_y)
    target_length = math.hypot(target_x, target_y)
    if source_length <= 0 or target_length <= 0:
        raise _distribution_error(
            "POOR_CONTROL_POINT_DISTRIBUTION",
            "Each point pair must identify two distinct locations.",
        )
    scale = target_length / source_length
    cosine = (source_x * target_x + source_y * target_y) / (
        source_length * target_length
    )
    sine = (source_x * target_y - source_y * target_x) / (
        source_length * target_length
    )
    a = scale * cosine
    b = -scale * sine
    d = scale * sine
    e = scale * cosine
    first_y = -first.image_y
    parameters = _parameter_dict(
        [
            a,
            b,
            first.longitude - a * first.image_x - b * first_y,
            d,
            e,
            first.latitude - d * first.image_x - e * first_y,
        ]
    )
    parameters["scale"] = scale
    parameters["rotation_degrees"] = math.degrees(math.atan2(sine, cosine))
    return parameters


def _affine_parameters(points: list[ControlPoint]) -> dict[str, float]:
    source = numpy.asarray(
        [[point.image_x, -point.image_y, 1.0] for point in points],
        dtype="float64",
    )
    longitude = numpy.asarray([point.longitude for point in points])
    latitude = numpy.asarray([point.latitude for point in points])
    try:
        horizontal, _, horizontal_rank, _ = numpy.linalg.lstsq(
            source, longitude, rcond=None
        )
        vertical, _, vertical_rank, _ = numpy.linalg.lstsq(
            source, latitude, rcond=None
        )
    except numpy.linalg.LinAlgError as exc:
        raise _error(
            400,
            "INVALID_TRANSFORMATION",
            "The affine transformation could not be calculated.",
            "The control-point equations could not be solved.",
            "control_points",
        ) from exc
    if horizontal_rank < 3 or vertical_rank < 3:
        raise _distribution_error(
            "COLLINEAR_CONTROL_POINTS",
            "Move at least one point away from the shared line.",
        )
    return _parameter_dict([*horizontal.tolist(), *vertical.tolist()])


def _raster_transform(parameters: dict[str, float]) -> Affine:
    return Affine(
        parameters["a"],
        -parameters["b"],
        parameters["c"],
        parameters["d"],
        -parameters["e"],
        parameters["f"],
    )


def _calculate(
    source_path: Path,
    points: list[ControlPoint],
    requested_transformation: str,
    target_crs: CRS,
) -> GeoreferenceCalculation:
    try:
        with rasterio.open(source_path) as source:
            width = source.width
            height = source.height
            source_crs = source.crs.to_string() if source.crs else None
    except (RasterioError, OSError, ValueError) as exc:
        raise _error(
            400,
            "INVALID_SOURCE_IMAGE",
            "The source raster could not be opened.",
            "The uploaded file is not a readable raster image.",
            "dataset_id",
        ) from exc
    transformation = _validate_count(points)
    if requested_transformation not in {"auto", transformation}:
        raise _error(
            400,
            "INVALID_TRANSFORMATION",
            "The requested transformation does not match the control points.",
            f"{len(points)} points require the {transformation} transformation.",
            "transformation",
        )
    _validate_points(points, width=width, height=height)
    _validate_distribution(points, width=width, height=height)
    parameters = (
        _similarity_parameters(points)
        if transformation == "similarity"
        else _affine_parameters(points)
    )
    return GeoreferenceCalculation(
        transformation=transformation,
        parameters=parameters,
        raster_transform=_raster_transform(parameters),
        source_crs=source_crs,
        target_crs=target_crs.to_string(),
        source_width=width,
        source_height=height,
    )


def _write_raster(
    source_path: Path,
    destination_path: Path,
    calculation: GeoreferenceCalculation,
) -> None:
    temporary_path = destination_path.with_name(
        f"{destination_path.stem}.tmp{destination_path.suffix}"
    )
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.unlink(missing_ok=True)
        with rasterio.open(source_path) as source:
            bounds = array_bounds(source.height, source.width, calculation.raster_transform)
            transform, width, height = calculate_default_transform(
                calculation.target_crs,
                calculation.target_crs,
                source.width,
                source.height,
                *bounds
            )
            profile = source.profile.copy()
            profile.update(
                driver="GTiff",
                width=width,
                height=height,
                count=source.count,
                crs=calculation.target_crs,
                transform=transform,
            )
            with rasterio.open(temporary_path, "w", **profile) as destination:
                for i in range(1, source.count + 1):
                    reproject(
                        source=source.read(i),
                        destination=rasterio.band(destination, i),
                        src_transform=calculation.raster_transform,
                        src_crs=calculation.target_crs,
                        dst_transform=transform,
                        dst_crs=calculation.target_crs,
                        resampling=Resampling.nearest
                    )
        temporary_path.replace(destination_path)
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        temporary_path.unlink(missing_ok=True)
        raise _error(
            500,
            "GEOREFERENCE_FAILED",
            "The georeferenced raster could not be generated.",
            "The geospatial processing operation failed.",
            "dataset_id",
        ) from exc


def _response_data(
    dataset_id: UUID,
    calculation: GeoreferenceCalculation,
    *,
    config: GeoreferenceConfig | None,
    status: str,
    output_path: str,
    point_count: int,
    reusable: bool = False,
    reuse_warning: str | None = None,
    message: str,
) -> GeoreferenceData:
    return GeoreferenceData(
        dataset_id=dataset_id,
        georeference_config_id=None if config is None else config.id,
        status=status,
        transformation=calculation.transformation,
        transformation_parameters=calculation.parameters,
        source_coordinate_system=SOURCE_COORDINATE_SYSTEM,
        control_point_count=point_count,
        source_crs=calculation.source_crs,
        target_crs=calculation.target_crs,
        source_width=calculation.source_width,
        source_height=calculation.source_height,
        output_format="GeoTIFF",
        output_path=output_path,
        reusable=reusable,
        reuse_warning=reuse_warning,
        created_at=None if config is None else config.created_at,
        updated_at=None if config is None else config.updated_at,
        message=message,
    )


def _upsert_config(
    db: DatabaseSession,
    dataset: Dataset,
    calculation: GeoreferenceCalculation,
    point_count: int,
    output_path: str,
) -> GeoreferenceConfig:
    config = db.get_active_georeference_config(dataset.id)
    values: dict[str, Any] = {
        "transformation": calculation.transformation,
        "source_file_hash": dataset.file_hash,
        "source_crs": calculation.source_crs,
        "target_crs": calculation.target_crs,
        "source_width": calculation.source_width,
        "source_height": calculation.source_height,
        "control_point_count": point_count,
        "source_coordinate_system": SOURCE_COORDINATE_SYSTEM,
        "transformation_parameters": calculation.parameters,
        "output_path": output_path,
        "output_format": "GeoTIFF",
        "status": "completed",
        "is_active": True,
    }
    if config is None:
        config = GeoreferenceConfig(dataset_id=dataset.id, **values)
    else:
        for name, value in values.items():
            setattr(config, name, value)
    db.save_georeference_config(config)
    return config


def _restore_output(output: Path, backup: Path | None) -> None:
    output.unlink(missing_ok=True)
    if backup is not None and backup.is_file():
        backup.replace(output)


def _record_failure(
    db: DatabaseSession, dataset: Dataset, config: GeoreferenceConfig | None = None
) -> None:
    try:
        db.rollback()
        dataset.georeference_status = "failed"
        db.save_dataset(dataset)
        current = config or db.get_active_georeference_config(dataset.id)
        if current is not None:
            current.status = "failed"
            db.save_georeference_config(current)
        db.commit()
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to persist georeference failure status.")


def mark_georeference_publication_failed(
    dataset_id: UUID, db: DatabaseSession
) -> None:
    """Prevent a partially processed save from appearing on the main map."""
    try:
        db.rollback()
        dataset = db.get_dataset(dataset_id)
        if dataset is not None:
            dataset.georeference_status = "failed"
            dataset.tile_status = "failed"
            dataset.tile_path = None
            dataset.tile_min_zoom = None
            dataset.tile_max_zoom = None
            db.save_dataset(dataset)
        config = db.get_active_georeference_config(dataset_id)
        if config is not None:
            config.status = "failed"
            db.save_georeference_config(config)
        db.commit()
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to mark an incomplete map publication as failed.")


def georeference_dataset(
    request: GeoreferenceRequest, db: DatabaseSession
) -> GeoreferenceResponse:
    dataset = _load_dataset(db, request.dataset_id)
    _validate_dataset_format(dataset)
    target_crs = _validate_request(request)
    points = _load_control_points(db, dataset.id)
    source_path = _source_path(dataset)
    calculation = _calculate(
        source_path, points, request.transformation, target_crs
    )

    if request.action == "calculate":
        preview_path = _output_path(dataset.id, preview=True)
        _write_raster(source_path, preview_path, calculation)
        return GeoreferenceResponse(
            data=_response_data(
                dataset.id,
                calculation,
                config=None,
                status="calculated",
                output_path=_relative_output_path(dataset.id, preview=True),
                point_count=len(points),
                message="Georeference calculated. Review the preview before saving.",
            )
        )

    candidate = _output_path(dataset.id).with_name("georeferenced.pending.tif")
    output = _output_path(dataset.id)
    relative_output = _relative_output_path(dataset.id)
    backup: Path | None = None
    promoted = False
    config: GeoreferenceConfig | None = None
    try:
        candidate.unlink(missing_ok=True)
        _write_raster(source_path, candidate, calculation)
        dataset.georeference_status = "completed"
        dataset.georeferenced_path = relative_output
        dataset.process_status = "not_started"
        dataset.processed_path = None
        dataset.tile_status = "not_started"
        dataset.tile_path = None
        dataset.tile_min_zoom = None
        dataset.tile_max_zoom = None
        db.save_dataset(dataset)
        config = _upsert_config(
            db, dataset, calculation, len(points), relative_output
        )
        backup_path = output.with_name("georeferenced.previous.tif")
        backup_path.unlink(missing_ok=True)
        if output.is_file():
            output.replace(backup_path)
            backup = backup_path
        candidate.replace(output)
        promoted = True
        db.commit()
    except ApplicationError:
        candidate.unlink(missing_ok=True)
        _record_failure(db, dataset, config)
        raise
    except (DatabaseError, OSError) as exc:
        candidate.unlink(missing_ok=True)
        if promoted or backup is not None:
            _restore_output(output, backup)
        _record_failure(db, dataset, config)
        raise _error(
            500,
            "GEOREFERENCE_SAVE_FAILED",
            "The georeference could not be saved.",
            "The generated output and database configuration were not committed.",
            "dataset_id",
        ) from exc
    if backup is not None:
        backup.unlink(missing_ok=True)
    _output_path(dataset.id, preview=True).unlink(missing_ok=True)
    return GeoreferenceResponse(
        data=_response_data(
            dataset.id,
            calculation,
            config=config,
            status="completed",
            output_path=relative_output,
            point_count=len(points),
            reusable=True,
            message="Georeference saved successfully.",
        )
    )


def _calculation_from_config(config: GeoreferenceConfig) -> GeoreferenceCalculation:
    required = {"a", "b", "c", "d", "e", "f"}
    parameters = dict(config.transformation_parameters or {})
    if not required.issubset(parameters):
        raise _error(
            409,
            "INVALID_CONFIGURATION",
            "The saved georeference configuration is incomplete.",
            "The saved transformation parameters cannot reproduce the output.",
            "dataset_id",
        )
    try:
        numeric_parameters = {
            key: float(value) for key, value in parameters.items()
        }
        transform = _raster_transform(numeric_parameters)
    except (TypeError, ValueError, KeyError) as exc:
        raise _error(
            409,
            "INVALID_CONFIGURATION",
            "The saved georeference configuration is invalid.",
            "The saved transformation parameters are not numeric.",
            "dataset_id",
        ) from exc
    return GeoreferenceCalculation(
        transformation=config.transformation,
        parameters=numeric_parameters,
        raster_transform=transform,
        source_crs=config.source_crs,
        target_crs=config.target_crs,
        source_width=config.source_width,
        source_height=config.source_height,
    )


def get_georeference_config(
    dataset_id: UUID, db: DatabaseSession
) -> GeoreferenceLookupResponse:
    dataset = _load_dataset(db, dataset_id)
    try:
        config = db.get_active_georeference_config(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        raise _error(
            500,
            "DATABASE_ERROR",
            "The saved georeference could not be loaded.",
            "The database operation failed.",
        ) from exc
    if config is None:
        return GeoreferenceLookupResponse(
            data=GeoreferenceLookupData(configuration=None)
        )
    calculation = _calculation_from_config(config)
    reusable = (
        config.status == "completed"
        and config.dataset_id == dataset.id
        and config.source_file_hash == dataset.file_hash
        and config.source_width == int(dataset.extracted_metadata.get("width", 0))
        and config.source_height == int(dataset.extracted_metadata.get("height", 0))
    )
    warning = None if reusable else REUSE_WARNING
    return GeoreferenceLookupResponse(
        data=GeoreferenceLookupData(
            configuration=_response_data(
                dataset.id,
                calculation,
                config=config,
                status=config.status,
                output_path=config.output_path,
                point_count=config.control_point_count,
                reusable=reusable,
                reuse_warning=warning,
                message=(
                    "Saved georeference configuration is ready to reuse."
                    if reusable
                    else warning
                ),
            )
        )
    )
