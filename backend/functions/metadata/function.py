import logging
import math
from pathlib import Path
from typing import Any, BinaryIO
import xml.etree.ElementTree as ElementTree
from zipfile import BadZipFile, ZipFile

import osmium
import pyogrio
import rasterio
from rasterio.errors import RasterioIOError
from starlette.concurrency import run_in_threadpool

from functions.metadata.request import MetadataRequest
from functions.metadata.response import MetadataData, MetadataResponse
from functions.pbf_preview.function import parse_pbf_with_preview
from functions.formats.function import (
    classify_json_document,
    geojson_metadata,
    inspect_geopackage,
    mbtiles_metadata,
    read_json_document,
)
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
RASTER_FORMATS = {"jpg", "jpeg", "png", "tiff"}
KML_FORMATS = {"kml", "kmz"}
OSM_FORMATS = {"osm", "osm_pbf"}
SHAPEFILE_COMPONENTS = {".shx", ".dbf", ".prj", ".cpg"}
KML_GEOMETRY_TYPES = {
    "Point",
    "LineString",
    "LinearRing",
    "Polygon",
    "MultiGeometry",
    "Model",
    "Track",
    "MultiTrack",
}


def _bounds(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> dict[str, float]:
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
    }


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _raster_colormap_legend(dataset: Any) -> dict[str, Any] | None:
    if dataset.count != 1:
        return None
    try:
        color_map = dataset.colormap(1)
    except (RasterioIOError, ValueError):
        return None
    if not color_map:
        return None

    items: list[dict[str, Any]] = []
    for value, rgba in sorted(color_map.items()):
        if not isinstance(rgba, tuple) or len(rgba) != 4:
            continue
        red, green, blue, alpha = rgba
        if not all(isinstance(channel, int) and 0 <= channel <= 255 for channel in rgba):
            continue
        items.append(
            {
                "type": "raster",
                "label": f"Value {value}",
                "value": int(value),
                "color": f"#{red:02X}{green:02X}{blue:02X}",
                "opacity": round(alpha / 255, 4),
            }
        )

    if not items:
        return None
    return {
        "title": "Source color table",
        "source": "raster_colormap",
        "items": items,
    }


def _extract_raster_metadata(file_path: Path) -> dict[str, Any]:
    try:
        with rasterio.open(file_path) as dataset:
            dtypes = list(dataset.dtypes)
            metadata: dict[str, Any] = {
                "driver": dataset.driver,
                "file_size": file_path.stat().st_size,
                "width": dataset.width,
                "height": dataset.height,
                "bands": dataset.count,
                "dtype": (
                    dtypes[0]
                    if dtypes and len(set(dtypes)) == 1
                    else dtypes
                ),
                "crs": dataset.crs.to_string() if dataset.crs else None,
                "bounds": None,
                "nodata": _finite_number(dataset.nodata),
                "color_interpretation": [
                    interpretation.name for interpretation in dataset.colorinterp
                ],
            }

            transform = dataset.transform
            has_spatial_transform = not transform.is_identity
            if dataset.crs is not None or has_spatial_transform:
                metadata["bounds"] = _bounds(*dataset.bounds)
                metadata["resolution"] = {
                    "x": float(abs(dataset.res[0])),
                    "y": float(abs(dataset.res[1])),
                }
                metadata["transform"] = [
                    float(transform.a),
                    float(transform.b),
                    float(transform.c),
                    float(transform.d),
                    float(transform.e),
                    float(transform.f),
                ]

            color_map_legend = _raster_colormap_legend(dataset)
            if color_map_legend is not None:
                metadata["legend"] = color_map_legend

            return metadata
    except (RasterioIOError, OSError, ValueError) as exc:
        raise ApplicationError(
            status_code=400,
            code="CORRUPTED_FILE",
            message="The raster file could not be read.",
            details="The stored file is not a readable raster dataset.",
            field="file",
        ) from exc


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _update_coordinate_bounds(
    coordinate_text: str,
    current_bounds: list[float] | None,
) -> list[float] | None:
    updated_bounds = current_bounds
    coordinate_tokens = coordinate_text.split()
    if any("," in token for token in coordinate_tokens):
        coordinate_values = [token.split(",") for token in coordinate_tokens]
    else:
        coordinate_values = [coordinate_tokens]

    for values in coordinate_values:
        if len(values) < 2:
            continue
        try:
            x = float(values[0])
            y = float(values[1])
        except ValueError:
            continue

        if updated_bounds is None:
            updated_bounds = [x, y, x, y]
        else:
            updated_bounds[0] = min(updated_bounds[0], x)
            updated_bounds[1] = min(updated_bounds[1], y)
            updated_bounds[2] = max(updated_bounds[2], x)
            updated_bounds[3] = max(updated_bounds[3], y)
    return updated_bounds


def _parse_kml_stream(stream: BinaryIO) -> dict[str, Any]:
    feature_count = 0
    geometry_types: set[str] = set()
    coordinate_bounds: list[float] | None = None
    root_name: str | None = None

    try:
        for event, element in ElementTree.iterparse(stream, events=("start", "end")):
            element_name = _local_name(element.tag)
            if root_name is None and event == "start":
                root_name = element_name
            if event != "end":
                continue
            if element_name == "Placemark":
                feature_count += 1
            elif element_name in KML_GEOMETRY_TYPES:
                geometry_types.add(element_name)
            elif element_name in {"coordinates", "coord"} and element.text:
                coordinate_bounds = _update_coordinate_bounds(
                    element.text,
                    coordinate_bounds,
                )
            element.clear()
    except (ElementTree.ParseError, OSError, ValueError) as exc:
        raise ApplicationError(
            status_code=400,
            code="INVALID_KML",
            message="The KML file is invalid.",
            details="The stored file does not contain readable KML data.",
            field="file",
        ) from exc

    if root_name != "kml":
        raise ApplicationError(
            status_code=400,
            code="INVALID_KML",
            message="The KML file is invalid.",
            details="The stored file does not contain a KML document.",
            field="file",
        )

    return {
        "feature_count": feature_count,
        "geometry_types": sorted(geometry_types),
        "crs": "EPSG:4326",
        "bounds": (
            _bounds(*coordinate_bounds) if coordinate_bounds is not None else None
        ),
    }


def _extract_kml_metadata(file_path: Path, format_name: str) -> dict[str, Any]:
    try:
        if format_name == "kmz":
            with ZipFile(file_path) as archive:
                kml_names = [
                    name for name in archive.namelist() if name.lower().endswith(".kml")
                ]
                if not kml_names:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_KML",
                        message="The KMZ file is invalid.",
                        details="The archive does not contain a KML document.",
                        field="file",
                    )
                preferred_name = next(
                    (name for name in kml_names if Path(name).name.lower() == "doc.kml"),
                    kml_names[0],
                )
                with archive.open(preferred_name) as kml_stream:
                    metadata = _parse_kml_stream(kml_stream)
        else:
            with file_path.open("rb") as kml_stream:
                metadata = _parse_kml_stream(kml_stream)
    except ApplicationError:
        raise
    except (BadZipFile, KeyError, OSError) as exc:
        raise ApplicationError(
            status_code=400,
            code="INVALID_KML",
            message="The KML file is invalid.",
            details="The stored file does not contain readable KML data.",
            field="file",
        ) from exc

    metadata["file_size"] = file_path.stat().st_size
    return metadata


def _matching_shapefile_components(file_path: Path) -> dict[str, Path]:
    return {
        candidate.suffix.lower(): candidate
        for candidate in file_path.parent.iterdir()
        if candidate.is_file() and candidate.stem.lower() == file_path.stem.lower()
    }


def _extract_shapefile_metadata(file_path: Path) -> dict[str, Any]:
    extension = file_path.suffix.lower()
    if extension in SHAPEFILE_COMPONENTS:
        return {
            "file_size": file_path.stat().st_size,
            "component": extension,
            "requires_shp": True,
            "crs": None,
            "bounds": None,
        }

    components = _matching_shapefile_components(file_path)
    missing_components = [
        extension for extension in (".shx", ".dbf") if extension not in components
    ]
    if missing_components:
        raise ApplicationError(
            status_code=400,
            code="INCOMPLETE_SHAPEFILE",
            message="The Shapefile is incomplete.",
            details=(
                "A Shapefile normally requires the corresponding .shx and .dbf "
                "files, and may also require .prj and .cpg files."
            ),
            field="file",
        )

    try:
        info = pyogrio.read_info(
            file_path,
            force_feature_count=True,
            force_total_bounds=True,
        )
    except Exception as exc:
        raise ApplicationError(
            status_code=400,
            code="CORRUPTED_FILE",
            message="The Shapefile could not be read.",
            details="The stored Shapefile dataset is corrupt or unsupported.",
            field="file",
        ) from exc

    total_bounds = info.get("total_bounds")
    return {
        "file_size": file_path.stat().st_size,
        "feature_count": int(info["features"]),
        "geometry_type": info.get("geometry_type"),
        "crs": info.get("crs"),
        "bounds": _bounds(*total_bounds) if total_bounds is not None else None,
        "fields": [str(field) for field in info.get("fields", [])],
    }


class _OsmCountHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.node_count = 0
        self.way_count = 0
        self.relation_count = 0

    def node(self, node: Any) -> None:
        self.node_count += 1

    def way(self, way: Any) -> None:
        self.way_count += 1

    def relation(self, relation: Any) -> None:
        self.relation_count += 1


def _extract_osm_metadata(
    file_path: Path,
    format_name: str,
) -> dict[str, Any]:
    if format_name == "osm_pbf":
        metadata, _ = parse_pbf_with_preview(file_path)
        return metadata

    handler = _OsmCountHandler()
    try:
        handler.apply_file(str(file_path), locations=False)
    except Exception as exc:
        raise ApplicationError(
            status_code=400,
            code="INVALID_OSM_FILE",
            message="The OSM file is invalid.",
            details="The stored file does not contain readable OSM data.",
            field="file",
        ) from exc

    return {
        "file_size": file_path.stat().st_size,
        "node_count": handler.node_count,
        "way_count": handler.way_count,
        "relation_count": handler.relation_count,
        "crs": "EPSG:4326",
        "bounds": None,
    }


def _extract_metadata(request: MetadataRequest) -> MetadataResponse:
    file_path = Path(request.file_path)
    if not file_path.is_file():
        raise ApplicationError(
            status_code=500,
            code="METADATA_EXTRACTION_ERROR",
            message="Metadata could not be extracted from the file.",
            details="The stored file is unavailable.",
            field="file",
        )

    normalized_format = request.format.lower()
    detected_format = normalized_format
    detected_category = request.category
    if normalized_format in RASTER_FORMATS:
        metadata = _extract_raster_metadata(file_path)
    elif normalized_format in {"geojson", "json"}:
        document = read_json_document(file_path)
        detected_format = classify_json_document(
            document,
            require_geojson=normalized_format == "geojson",
        )
        if detected_format == "geojson":
            detected_category = "vector"
            metadata = geojson_metadata(document, file_path.stat().st_size)
        else:
            detected_category = "style"
            metadata = {
                "file_size": file_path.stat().st_size,
                "style_version": 8,
                "source_count": len(document["sources"]),
                "layer_count": len(document["layers"]),
                "style": document,
                "crs": "EPSG:3857",
                "bounds": None,
            }
    elif normalized_format == "geopackage":
        metadata = inspect_geopackage(file_path)
    elif normalized_format == "mbtiles":
        metadata = mbtiles_metadata(file_path)
    elif normalized_format in KML_FORMATS:
        metadata = _extract_kml_metadata(file_path, normalized_format)
    elif normalized_format == "shapefile":
        metadata = _extract_shapefile_metadata(file_path)
    elif normalized_format in OSM_FORMATS:
        metadata = _extract_osm_metadata(file_path, normalized_format)
    else:
        raise ApplicationError(
            status_code=400,
            code="UNSUPPORTED_METADATA_FORMAT",
            message="Metadata extraction is not supported for this file format.",
            details="The detected format has no metadata extractor.",
            field="file",
        )

    return MetadataResponse(
        data=MetadataData(
            format=detected_format,
            category=detected_category,
            metadata=metadata,
        )
    )


async def extract_metadata(request: MetadataRequest) -> MetadataResponse:
    try:
        return await run_in_threadpool(_extract_metadata, request)
    except ApplicationError as exc:
        if exc.__cause__ is not None:
            logger.exception("Metadata extraction failed for a stored upload.")
        raise
    except Exception as exc:
        logger.exception("Unexpected metadata extraction failure.", exc_info=exc)
        raise ApplicationError(
            status_code=500,
            code="METADATA_EXTRACTION_ERROR",
            message="Metadata could not be extracted from the file.",
            details="The file could not be opened using the detected format.",
            field="file",
        ) from exc
