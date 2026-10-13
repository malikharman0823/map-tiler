import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import numpy
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.warp import transform_bounds

from storage.session import RepositoryError, SessionRepository

from functions.dataset_detail.request import DatasetDetailRequest
from functions.dataset_detail.response import (
    DatasetDetailData,
    DatasetDetailResponse,
    GeographicBounds,
    GeoreferenceSummary,
    MapLayerSummary,
)
from config import settings
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"
DIRECT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
TIFF_EXTENSIONS = {".tif", ".tiff"}
MAX_PREVIEW_EDGE = 2048


@dataclass(frozen=True)
class DatasetSourceImage:
    path: Path
    media_type: str


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
        message="The dataset could not be retrieved.",
        details="The database operation failed.",
        field=None,
    )


def _managed_path(
    stored_path: str | None,
    expected_directory: Path,
    *,
    code: str,
    message: str,
    details: str,
) -> Path:
    if not stored_path:
        raise ApplicationError(
            status_code=404,
            code=code,
            message=message,
            details=details,
            field="dataset_id",
        )
    try:
        stored = Path(stored_path)
        candidate = stored.resolve() if stored.is_absolute() else (BACKEND_DIRECTORY / stored).resolve()
        sessions_root = Path(settings.session_storage_dir).resolve()
        is_safe = (
            candidate.is_relative_to(expected_directory.resolve())
            or candidate.is_relative_to(sessions_root)
            or candidate.is_relative_to(BACKEND_DIRECTORY.resolve())
            or (candidate.exists() and any(p in ("sessions", "datasets") for p in candidate.parts))
        )
        if not is_safe:
            raise ValueError("Path traversal detected")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ApplicationError(
            status_code=404,
            code=code,
            message=message,
            details=details,
            field="dataset_id",
        ) from exc
    return candidate


def _raster_bounds(dataset: Dataset, output_path: str) -> tuple[str, GeographicBounds]:
    expected_directory = PROCESSED_DIRECTORY / str(dataset.id)
    candidate = _managed_path(
        output_path,
        expected_directory,
        code="RASTER_OUTPUT_NOT_FOUND",
        message="The saved georeferenced raster was not found.",
        details="Save the georeference again to regenerate its geographic output.",
    )
    if not candidate.is_file():
        raise ApplicationError(
            status_code=404,
            code="RASTER_OUTPUT_NOT_FOUND",
            message="The saved georeferenced raster was not found.",
            details="Save the georeference again to regenerate its geographic output.",
            field="dataset_id",
        )
    try:
        with rasterio.open(candidate) as output:
            if output.crs is None:
                raise ValueError("Saved raster has no CRS.")
            left, bottom, right, top = transform_bounds(
                output.crs,
                CRS.from_epsg(4326),
                *output.bounds,
                densify_pts=21,
            )
            if left >= right or bottom >= top:
                raise ValueError("Saved raster bounds are invalid.")
            return output.crs.to_string(), GeographicBounds(
                min_longitude=left,
                min_latitude=bottom,
                max_longitude=right,
                max_latitude=top,
            )
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        logger.exception("Failed to read the saved georeferenced raster metadata.")
        raise ApplicationError(
            status_code=404,
            code="RASTER_OUTPUT_NOT_FOUND",
            message="The saved georeferenced raster was not found.",
            details="Save the georeference again to regenerate its geographic output.",
            field="dataset_id",
        ) from exc


def _tile_directory(dataset: Dataset) -> Path:
    expected_directory = TILES_DIRECTORY / str(dataset.id)
    candidate = _managed_path(
        dataset.tile_path,
        expected_directory,
        code="TILE_SOURCE_NOT_FOUND",
        message="The saved dataset tile source was not found.",
        details="Save the georeference again to regenerate its map tiles.",
    )
    try:
        has_tile = candidate.is_dir() and next(candidate.rglob("*.png"), None) is not None
    except OSError as exc:
        logger.exception("Failed to inspect the saved dataset tile source.")
        raise ApplicationError(
            status_code=404,
            code="TILE_SOURCE_NOT_FOUND",
            message="The saved dataset tile source was not found.",
            details="Save the georeference again to regenerate its map tiles.",
            field="dataset_id",
        ) from exc
    if not has_tile:
        raise ApplicationError(
            status_code=404,
            code="TILE_SOURCE_NOT_FOUND",
            message="The saved dataset tile source was not found.",
            details="Save the georeference again to regenerate its map tiles.",
            field="dataset_id",
        )
    return candidate


def _is_folder_tile_dataset(dataset: Dataset) -> bool:
    metadata = dataset.extracted_metadata or {}
    if str(metadata.get("format") or "").lower() == "mapstudio_folder":
        return True
    return bool(
        metadata.get("import_package_hash")
        and isinstance(metadata.get("bounds"), list)
        and dataset.tile_status == "completed"
        and dataset.tile_path
    )


def _map_layer(dataset: Dataset, georeference) -> MapLayerSummary | None:
    metadata = dataset.extracted_metadata or {}
    if _is_folder_tile_dataset(dataset):
        bounds_value = metadata.get("bounds")
        if not isinstance(bounds_value, list) or len(bounds_value) != 4:
            raise ApplicationError(
                status_code=404,
                code="RASTER_OUTPUT_NOT_FOUND",
                message="The restored project map bounds were not found.",
                details="Open the original exported folder again.",
                field="dataset_id",
            )
        west, south, east, north = (float(value) for value in bounds_value)
        if (
            dataset.tile_status != "completed"
            or dataset.tile_min_zoom is None
            or dataset.tile_max_zoom is None
            or not (-180 <= west < east <= 180 and -90 <= south < north <= 90)
        ):
            raise ApplicationError(
                status_code=404,
                code="TILE_SOURCE_NOT_FOUND",
                message="The restored project tile source was not found.",
                details="Open the original exported folder again.",
                field="dataset_id",
            )
        _tile_directory(dataset)
        return MapLayerSummary(
            name=Path(dataset.filename).stem,
            source_crs="EPSG:3857",
            bounds=GeographicBounds(
                min_longitude=west,
                min_latitude=south,
                max_longitude=east,
                max_latitude=north,
            ),
            tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
            tile_min_zoom=dataset.tile_min_zoom,
            tile_max_zoom=dataset.tile_max_zoom,
        )

    if dataset.georeference_status != "completed":
        return None

    if georeference is None and not dataset.processed_path:
        return None

    if georeference and georeference.status != "completed":
        return None

    if (
        dataset.tile_status != "completed"
        or dataset.tile_min_zoom is None
        or dataset.tile_max_zoom is None
    ):
        raise ApplicationError(
            status_code=404,
            code="TILE_SOURCE_NOT_FOUND",
            message="The saved dataset tile source was not found.",
            details="Save the georeference again to regenerate its map tiles.",
            field="dataset_id",
        )

    output_path = georeference.output_path if georeference else dataset.processed_path
    if not output_path:
        return None

    source_crs, bounds = _raster_bounds(dataset, output_path)
    _tile_directory(dataset)
    return MapLayerSummary(
        name=Path(dataset.filename).stem,
        source_crs=source_crs,
        bounds=bounds,
        tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
        tile_min_zoom=dataset.tile_min_zoom,
        tile_max_zoom=dataset.tile_max_zoom,
    )


def _response(dataset: Dataset, georeference) -> DatasetDetailResponse:
    metadata = dataset.extracted_metadata or {}
    format_type = str(metadata.get("format", "")).lower()

    is_georeferenced = False
    display_type = "unknown"
    is_spatial = False

    if _is_folder_tile_dataset(dataset):
        display_type = "raster"
        is_spatial = True
        is_georeferenced = True
    elif format_type in {"jpg", "jpeg", "png"}:
        display_type = "raster"
        if dataset.georeference_status == "completed" or (metadata.get("crs") and metadata.get("transform")):
            is_georeferenced = True
            is_spatial = True
    elif format_type in {"pdf", "cad", "dxf", "dwg", "svf"}:
        display_type = "raster"
        if dataset.georeference_status == "completed":
            is_georeferenced = True
            is_spatial = True
    elif format_type == "mtmap":
        display_type = "project"

    return DatasetDetailResponse(
        data=DatasetDetailData(
            id=dataset.id,
            filename=dataset.filename,
            file_size=dataset.file_size,
            content_type=dataset.content_type,
            file_hash=dataset.file_hash,
            storage_path=dataset.storage_path,
            metadata=dataset.extracted_metadata,
            georeferenced_path=dataset.georeferenced_path,
            georeference_status=dataset.georeference_status,
            processed_path=dataset.processed_path,
            process_status=dataset.process_status,
            tile_path=dataset.tile_path,
            tile_min_zoom=dataset.tile_min_zoom,
            tile_max_zoom=dataset.tile_max_zoom,
            tile_status=dataset.tile_status,
            display_type=display_type,
            is_spatial=is_spatial,
            is_georeferenced=is_georeferenced,
            georeference=(
                None
                if georeference is None
                else GeoreferenceSummary(
                    id=georeference.id,
                    status=georeference.status,
                    transformation=georeference.transformation,
                    control_point_count=georeference.control_point_count,
                    target_crs=georeference.target_crs,
                    source_width=georeference.source_width,
                    source_height=georeference.source_height,
                    output_format=georeference.output_format,
                    output_path=georeference.output_path,
                )
            ),
            map_layer=_map_layer(dataset, georeference),
            created_at=dataset.created_at,
        )
    )


def get_dataset_detail(
    request: DatasetDetailRequest,
    db: SessionRepository,
) -> DatasetDetailResponse:
    try:
        dataset = db.get_dataset(request.dataset_id)
        georeference = db.get_active_georeference_config(request.dataset_id)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to retrieve a dataset.", exc_info=exc)
        raise _database_error() from exc

    if dataset is None:
        raise _dataset_not_found()
    return _response(dataset, georeference)


def _source_file_path(dataset: Dataset) -> Path:
    try:
        stored = Path(dataset.storage_path)
        source_path = stored.resolve() if stored.is_absolute() else (BACKEND_DIRECTORY / dataset.storage_path).resolve()
        sessions_root = Path(settings.session_storage_dir).resolve()
        uploads_root = UPLOAD_DIRECTORY.resolve()
        is_safe = (
            source_path.is_relative_to(uploads_root)
            or source_path.is_relative_to(sessions_root)
            or (source_path.exists() and any(p in ("sessions", "datasets", "uploads") for p in source_path.parts))
        )
        if not is_safe:
            raise ValueError("Path traversal detected")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ApplicationError(
            status_code=404,
            code="SOURCE_FILE_NOT_FOUND",
            message="The source raster was not found.",
            details="The uploaded raster file is unavailable.",
            field="dataset_id",
        ) from exc
    if not source_path.is_file():
        raise ApplicationError(
            status_code=404,
            code="SOURCE_FILE_NOT_FOUND",
            message="The source raster was not found.",
            details="The uploaded raster file is unavailable.",
            field="dataset_id",
        )
    return source_path


def _uint8_preview(data: numpy.ndarray) -> numpy.ndarray:
    if data.dtype == numpy.uint8:
        return data
    preview = numpy.empty(data.shape, dtype=numpy.uint8)
    for index, band in enumerate(data):
        finite_values = band[numpy.isfinite(band)]
        if finite_values.size == 0:
            preview[index].fill(0)
            continue
        low, high = numpy.percentile(finite_values, (2, 98))
        if high <= low:
            preview[index].fill(0)
            continue
        preview[index] = numpy.clip((band - low) * 255 / (high - low), 0, 255)
    return preview


def _tiff_preview(source_path: Path, dataset_id: UUID) -> Path:
    output_path = PROCESSED_DIRECTORY / str(dataset_id) / "source-preview.png"
    if output_path.is_file():
        return output_path

    temporary_path = output_path.with_name("source-preview.tmp.png")
    try:
        with rasterio.open(source_path) as source:
            if source.count < 1 or source.width < 1 or source.height < 1:
                raise ValueError("Raster has no displayable pixels.")
            scale = min(1, MAX_PREVIEW_EDGE / max(source.width, source.height))
            preview_width = max(1, round(source.width * scale))
            preview_height = max(1, round(source.height * scale))
            indexes = tuple(range(1, min(source.count, 3) + 1))
            data = source.read(
                indexes=indexes,
                out_shape=(len(indexes), preview_height, preview_width),
                resampling=Resampling.bilinear,
            )
            data = _uint8_preview(data)
            if data.shape[0] == 1:
                data = numpy.repeat(data, 3, axis=0)
            elif data.shape[0] == 2:
                data = numpy.concatenate((data, data[:1]), axis=0)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.unlink(missing_ok=True)
        with rasterio.open(
            temporary_path,
            "w",
            driver="PNG",
            width=preview_width,
            height=preview_height,
            count=3,
            dtype="uint8",
        ) as destination:
            destination.write(data)
        temporary_path.replace(output_path)
        return output_path
    except (RasterioError, OSError, TypeError, ValueError) as exc:
        temporary_path.unlink(missing_ok=True)
        raise ApplicationError(
            status_code=400,
            code="INVALID_RASTER",
            message="The source raster could not be displayed.",
            details="The uploaded raster is not a displayable image.",
            field="dataset_id",
        ) from exc


def get_dataset_source_image(
    dataset_id: UUID,
    db: SessionRepository,
) -> DatasetSourceImage:
    try:
        dataset = db.get_dataset(dataset_id)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to retrieve a dataset source image.", exc_info=exc)
        raise _database_error() from exc
    if dataset is None:
        raise _dataset_not_found()
    source_path = _source_file_path(dataset)
    extension = source_path.suffix.lower()
    if extension in DIRECT_IMAGE_EXTENSIONS:
        return DatasetSourceImage(
            path=source_path,
            media_type="image/jpeg" if extension in {".jpg", ".jpeg"} else "image/png",
        )
    if extension in {".pdf", ".dxf", ".dwg", ".svf"}:
        preview_path = source_path.parent / "source-preview.png"
        if not preview_path.is_file():
            preview_path = PROCESSED_DIRECTORY / str(dataset_id) / "source-preview.png"
        if not preview_path.is_file():
            from functions.formats.converters import convert_source_to_image
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            convert_source_to_image(source_path, preview_path)
        return DatasetSourceImage(
            path=preview_path,
            media_type="image/png",
        )
    if extension in TIFF_EXTENSIONS:
        return DatasetSourceImage(
            path=_tiff_preview(source_path, dataset_id),
            media_type="image/png",
        )
    raise ApplicationError(
        status_code=400,
        code="INVALID_RASTER",
        message="The source raster could not be displayed.",
        details="Visual georeferencing supports PNG, JPG, PDF, CAD (.dxf, .dwg), and SVF files.",
        field="dataset_id",
    )
