from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import sqlite3
import struct
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pyogrio
from pyogrio.raw import read as ogr_read
from pyogrio.raw import write as ogr_write

from schemas.error import ApplicationError


GEOJSON_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
}
GEOJSON_ROOT_TYPES = GEOJSON_GEOMETRY_TYPES | {"Feature", "FeatureCollection"}
MBTILES_FORMAT_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pbf": "application/vnd.mapbox-vector-tile",
    "mvt": "application/vnd.mapbox-vector-tile",
}
MAX_VECTOR_PREVIEW_FEATURES = 10_000
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]


def resolve_managed_path(relative_path: str) -> Path:
    candidate = (BACKEND_DIRECTORY / relative_path).resolve()
    try:
        candidate.relative_to(BACKEND_DIRECTORY.resolve())
    except ValueError as exc:
        raise ApplicationError(
            status_code=500,
            code="INVALID_MANAGED_PATH",
            message="A managed project file path is invalid.",
            details="The stored path resolves outside backend-managed storage.",
        ) from exc
    return candidate


def sha256_path(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _format_error(
    code: str,
    message: str,
    details: str,
) -> ApplicationError:
    return ApplicationError(
        status_code=400,
        code=code,
        message=message,
        details=details,
        field="file",
    )


def read_json_document(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            document = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _format_error(
            "INVALID_JSON",
            "The JSON file is invalid.",
            "The file must contain one UTF-8 JSON object.",
        ) from exc
    if not isinstance(document, dict):
        raise _format_error(
            "INVALID_JSON",
            "The JSON file is invalid.",
            "The root JSON value must be an object.",
        )
    return document


def is_maplibre_style(document: dict[str, Any]) -> bool:
    return (
        document.get("version") == 8
        and isinstance(document.get("sources"), dict)
        and isinstance(document.get("layers"), list)
        and all(isinstance(layer, dict) for layer in document["layers"])
    )


def _validate_position(position: Any) -> None:
    if not isinstance(position, list) or len(position) < 2:
        raise ValueError("A coordinate position must have at least two numbers.")
    for value in position:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Coordinates must contain only numbers.")
        if not math.isfinite(float(value)):
            raise ValueError("Coordinates must be finite.")


def _validate_coordinates(value: Any, depth: int) -> None:
    if depth == 0:
        _validate_position(value)
        return
    if not isinstance(value, list):
        raise ValueError("Geometry coordinates have an invalid structure.")
    for child in value:
        _validate_coordinates(child, depth - 1)


def validate_geojson_geometry(geometry: Any) -> None:
    if geometry is None:
        return
    if not isinstance(geometry, dict):
        raise ValueError("A GeoJSON geometry must be an object or null.")
    geometry_type = geometry.get("type")
    if geometry_type not in GEOJSON_GEOMETRY_TYPES:
        raise ValueError("The GeoJSON geometry type is unsupported.")
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not isinstance(geometries, list):
            raise ValueError("A GeometryCollection requires a geometries array.")
        for child in geometries:
            validate_geojson_geometry(child)
        return
    coordinate_depth = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }[geometry_type]
    _validate_coordinates(geometry.get("coordinates"), coordinate_depth)


def validate_geojson(document: dict[str, Any]) -> None:
    root_type = document.get("type")
    if root_type not in GEOJSON_ROOT_TYPES:
        raise _format_error(
            "INVALID_GEOJSON",
            "The GeoJSON file is invalid.",
            "The root type is not a supported GeoJSON type.",
        )
    try:
        if root_type == "FeatureCollection":
            features = document.get("features")
            if not isinstance(features, list):
                raise ValueError("A FeatureCollection requires a features array.")
            for feature in features:
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ValueError("Every collection item must be a Feature.")
                properties = feature.get("properties")
                if properties is not None and not isinstance(properties, dict):
                    raise ValueError("Feature properties must be an object or null.")
                validate_geojson_geometry(feature.get("geometry"))
        elif root_type == "Feature":
            properties = document.get("properties")
            if properties is not None and not isinstance(properties, dict):
                raise ValueError("Feature properties must be an object or null.")
            validate_geojson_geometry(document.get("geometry"))
        else:
            validate_geojson_geometry(document)
    except ValueError as exc:
        raise _format_error(
            "INVALID_GEOJSON",
            "The GeoJSON file is invalid.",
            str(exc),
        ) from exc


def classify_json_document(
    document: dict[str, Any],
    *,
    require_geojson: bool = False,
) -> str:
    if document.get("type") in GEOJSON_ROOT_TYPES:
        validate_geojson(document)
        return "geojson"
    if not require_geojson and is_maplibre_style(document):
        return "maplibre_style"
    code = "INVALID_GEOJSON" if require_geojson else "UNSUPPORTED_JSON_STRUCTURE"
    message = (
        "The GeoJSON file is invalid."
        if require_geojson
        else "The JSON structure is not supported."
    )
    raise _format_error(
        code,
        message,
        "Use GeoJSON or a MapLibre Style Specification version 8 document.",
    )


def as_feature_collection(document: dict[str, Any]) -> dict[str, Any]:
    root_type = document.get("type")
    if root_type == "FeatureCollection":
        return document
    if root_type == "Feature":
        return {"type": "FeatureCollection", "features": [document]}
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": document}
        ],
    }


def _iter_positions(geometry: dict[str, Any] | None) -> Iterable[list[float]]:
    if not geometry:
        return
    geometry_type = geometry.get("type")
    if geometry_type == "GeometryCollection":
        for child in geometry.get("geometries", []):
            yield from _iter_positions(child)
        return

    def walk(value: Any) -> Iterable[list[float]]:
        if isinstance(value, list) and value and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        ):
            yield value
            return
        if isinstance(value, list):
            for child in value:
                yield from walk(child)

    yield from walk(geometry.get("coordinates"))


def geojson_metadata(document: dict[str, Any], file_size: int) -> dict[str, Any]:
    collection = as_feature_collection(document)
    geometry_types: set[str] = set()
    fields: set[str] = set()
    bounds: list[float] | None = None
    for feature in collection["features"]:
        geometry = feature.get("geometry")
        if geometry:
            geometry_types.add(str(geometry.get("type")))
            for position in _iter_positions(geometry):
                x, y = float(position[0]), float(position[1])
                if bounds is None:
                    bounds = [x, y, x, y]
                else:
                    bounds = [
                        min(bounds[0], x),
                        min(bounds[1], y),
                        max(bounds[2], x),
                        max(bounds[3], y),
                    ]
        fields.update((feature.get("properties") or {}).keys())
    return {
        "file_size": file_size,
        "feature_count": len(collection["features"]),
        "geometry_types": sorted(geometry_types),
        "fields": sorted(str(field) for field in fields),
        "crs": "EPSG:4326",
        "bounds": None
        if bounds is None
        else {
            "min_x": bounds[0],
            "min_y": bounds[1],
            "max_x": bounds[2],
            "max_y": bounds[3],
        },
    }


def inspect_geopackage(path: Path) -> dict[str, Any]:
    try:
        layer_rows = pyogrio.list_layers(path)
        layers: list[dict[str, Any]] = []
        total_features = 0
        for layer_name, geometry_type in layer_rows:
            info = pyogrio.read_info(
                path,
                layer=str(layer_name),
                force_feature_count=True,
                force_total_bounds=True,
            )
            feature_count = max(0, int(info.get("features", 0)))
            total_features += feature_count
            total_bounds = info.get("total_bounds")
            layers.append(
                {
                    "name": str(layer_name),
                    "geometry_type": (
                        str(geometry_type) if geometry_type is not None else None
                    ),
                    "feature_count": feature_count,
                    "crs": info.get("crs"),
                    "fields": [str(field) for field in info.get("fields", [])],
                    "bounds": None
                    if total_bounds is None
                    else {
                        "min_x": float(total_bounds[0]),
                        "min_y": float(total_bounds[1]),
                        "max_x": float(total_bounds[2]),
                        "max_y": float(total_bounds[3]),
                    },
                }
            )
    except Exception as exc:
        raise _format_error(
            "INVALID_GEOPACKAGE",
            "The GeoPackage could not be read.",
            "The file is not a readable GDAL/OGR GeoPackage.",
        ) from exc
    vector_layers = [layer for layer in layers if layer["geometry_type"]]
    if not vector_layers:
        raise _format_error(
            "GEOPACKAGE_VECTOR_LAYERS_REQUIRED",
            "The GeoPackage has no supported vector layers.",
            "Raster-only or empty GeoPackages are not supported.",
        )
    return {
        "file_size": path.stat().st_size,
        "driver": "GPKG",
        "layer_count": len(vector_layers),
        "feature_count": total_features,
        "layers": vector_layers,
    }


class _WkbReader:
    def __init__(self, data: bytes) -> None:
        self.data = memoryview(data)
        self.offset = 0

    def unpack(self, endian: str, value_format: str) -> tuple[Any, ...]:
        size = struct.calcsize(endian + value_format)
        if self.offset + size > len(self.data):
            raise ValueError("Truncated WKB geometry.")
        values = struct.unpack_from(endian + value_format, self.data, self.offset)
        self.offset += size
        return values

    def geometry(self) -> dict[str, Any]:
        byte_order = self.unpack("<", "B")[0]
        if byte_order not in {0, 1}:
            raise ValueError("Invalid WKB byte order.")
        endian = "<" if byte_order == 1 else ">"
        raw_type = int(self.unpack(endian, "I")[0])
        has_z = bool(raw_type & 0x80000000)
        has_m = bool(raw_type & 0x40000000)
        has_srid = bool(raw_type & 0x20000000)
        geometry_type = raw_type & 0x0FFFFFFF
        if geometry_type >= 3000:
            geometry_type -= 3000
            has_z = True
            has_m = True
        elif geometry_type >= 2000:
            geometry_type -= 2000
            has_m = True
        elif geometry_type >= 1000:
            geometry_type -= 1000
            has_z = True
        if has_srid:
            self.unpack(endian, "I")
        dimension = 2 + int(has_z) + int(has_m)

        def point() -> list[float]:
            values = list(self.unpack(endian, "d" * dimension))
            return values[: 3 if has_z else 2]

        def count() -> int:
            value = int(self.unpack(endian, "I")[0])
            if value > MAX_VECTOR_PREVIEW_FEATURES * 100:
                raise ValueError("WKB coordinate count is unreasonable.")
            return value

        names = {
            1: "Point",
            2: "LineString",
            3: "Polygon",
            4: "MultiPoint",
            5: "MultiLineString",
            6: "MultiPolygon",
            7: "GeometryCollection",
        }
        if geometry_type not in names:
            raise ValueError("Unsupported WKB geometry type.")
        name = names[geometry_type]
        if geometry_type == 1:
            return {"type": name, "coordinates": point()}
        if geometry_type == 2:
            return {"type": name, "coordinates": [point() for _ in range(count())]}
        if geometry_type == 3:
            rings = []
            for _ in range(count()):
                rings.append([point() for _ in range(count())])
            return {"type": name, "coordinates": rings}
        children = [self.geometry() for _ in range(count())]
        if geometry_type == 7:
            return {"type": name, "geometries": children}
        expected_child = {4: "Point", 5: "LineString", 6: "Polygon"}[geometry_type]
        if any(child.get("type") != expected_child for child in children):
            raise ValueError("Invalid nested WKB geometry type.")
        return {"type": name, "coordinates": [child["coordinates"] for child in children]}


def wkb_to_geojson(data: bytes) -> dict[str, Any]:
    reader = _WkbReader(data)
    geometry = reader.geometry()
    if reader.offset != len(reader.data):
        raise ValueError("Unexpected bytes after WKB geometry.")
    return geometry


def _transform_geometry(
    geometry: dict[str, Any],
    transform: Callable[[float, float], tuple[float, float]],
) -> dict[str, Any]:
    if geometry["type"] == "GeometryCollection":
        return {
            **geometry,
            "geometries": [
                _transform_geometry(child, transform)
                for child in geometry.get("geometries", [])
            ],
        }

    def walk(value: Any) -> Any:
        if isinstance(value, list) and len(value) >= 2 and all(
            isinstance(item, (int, float)) for item in value[:2]
        ):
            x, y = transform(float(value[0]), float(value[1]))
            return [x, y, *value[2:]]
        return [walk(child) for child in value]

    return {**geometry, "coordinates": walk(geometry["coordinates"])}


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def geopackage_preview(
    path: Path,
    max_features: int = MAX_VECTOR_PREVIEW_FEATURES,
) -> dict[str, Any]:
    package = inspect_geopackage(path)
    features: list[dict[str, Any]] = []
    truncated = False
    for layer in package["layers"]:
        remaining = max_features - len(features)
        if remaining <= 0:
            truncated = True
            break
        try:
            meta, fids, geometries, field_data = ogr_read(
                path,
                layer=layer["name"],
                max_features=remaining + 1,
                force_2d=True,
                return_fids=True,
            )
            transformer = None
            crs = meta.get("crs")
            if crs and "4326" not in str(crs).upper():
                try:
                    from pyproj import Transformer

                    transformer = Transformer.from_crs(
                        crs, "EPSG:4326", always_xy=True
                    ).transform
                except Exception as exc:
                    raise _format_error(
                        "UNSUPPORTED_VECTOR_CRS",
                        "The vector layer CRS could not be transformed.",
                        f"Layer {layer['name']} does not have a usable WGS84 transformation.",
                    ) from exc
            row_count = 0 if geometries is None else len(geometries)
            if row_count > remaining:
                row_count = remaining
                truncated = True
            fields = [str(field) for field in meta.get("fields", [])]
            for index in range(row_count):
                raw_geometry = geometries[index]
                geometry = None if raw_geometry is None else wkb_to_geojson(bytes(raw_geometry))
                if geometry is not None and transformer is not None:
                    geometry = _transform_geometry(geometry, transformer)
                properties = {
                    field: _json_scalar(field_data[field_index][index])
                    for field_index, field in enumerate(fields)
                }
                properties["_layer"] = layer["name"]
                if fids is not None:
                    properties["_fid"] = int(fids[index])
                features.append(
                    {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": properties,
                    }
                )
        except ApplicationError:
            raise
        except Exception as exc:
            raise _format_error(
                "GEOPACKAGE_READ_ERROR",
                "A GeoPackage layer could not be read.",
                f"Layer {layer['name']} contains unsupported or corrupt vector data.",
            ) from exc
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "truncated": truncated,
        "feature_limit": max_features,
        "layers": package["layers"],
    }


def _wkb_header(geometry_type: int) -> bytes:
    return struct.pack("<BI", 1, geometry_type)


def geojson_to_wkb(geometry: dict[str, Any]) -> bytes:
    geometry_type = geometry.get("type")

    def point_bytes(position: list[Any]) -> bytes:
        _validate_position(position)
        return struct.pack("<dd", float(position[0]), float(position[1]))

    if geometry_type == "Point":
        return _wkb_header(1) + point_bytes(geometry["coordinates"])
    if geometry_type == "LineString":
        coordinates = geometry["coordinates"]
        return _wkb_header(2) + struct.pack("<I", len(coordinates)) + b"".join(
            point_bytes(position) for position in coordinates
        )
    if geometry_type == "Polygon":
        rings = geometry["coordinates"]
        payload = [_wkb_header(3), struct.pack("<I", len(rings))]
        for ring in rings:
            payload.extend(
                [
                    struct.pack("<I", len(ring)),
                    b"".join(point_bytes(position) for position in ring),
                ]
            )
        return b"".join(payload)
    multi_types = {
        "MultiPoint": (4, "Point"),
        "MultiLineString": (5, "LineString"),
        "MultiPolygon": (6, "Polygon"),
    }
    if geometry_type in multi_types:
        type_id, child_type = multi_types[geometry_type]
        children = [
            geojson_to_wkb({"type": child_type, "coordinates": coordinates})
            for coordinates in geometry["coordinates"]
        ]
        return _wkb_header(type_id) + struct.pack("<I", len(children)) + b"".join(children)
    if geometry_type == "GeometryCollection":
        children = [geojson_to_wkb(child) for child in geometry.get("geometries", [])]
        return _wkb_header(7) + struct.pack("<I", len(children)) + b"".join(children)
    raise ValueError("Unsupported GeoJSON geometry type.")


def _layer_name(value: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")[:48] or "features"
    candidate = base
    suffix = 2
    while candidate.lower() in used:
        candidate = f"{base[:44]}_{suffix}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def write_geojson_to_geopackage(document: dict[str, Any], destination: Path) -> None:
    validate_geojson(document)
    collection = as_feature_collection(document)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for feature in collection["features"]:
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        grouped.setdefault(str(geometry["type"]), []).append(feature)
    if not grouped:
        raise _format_error(
            "VECTOR_DATA_REQUIRED",
            "No vector data is available for GeoPackage export.",
            "At least one feature with geometry is required.",
        )
    used_names: set[str] = set()
    for layer_index, (geometry_type, features) in enumerate(sorted(grouped.items())):
        field_names = sorted(
            {
                str(key)
                for feature in features
                for key in (feature.get("properties") or {}).keys()
            }
        )
        field_data: list[np.ndarray] = []
        field_mask: list[np.ndarray] = []
        for field in field_names:
            values = [(feature.get("properties") or {}).get(field) for feature in features]
            non_null = [value for value in values if value is not None]
            if non_null and all(isinstance(value, bool) for value in non_null):
                data = np.array([bool(value) if value is not None else False for value in values])
            elif non_null and all(isinstance(value, int) and not isinstance(value, bool) for value in non_null):
                data = np.array([int(value) if value is not None else 0 for value in values], dtype="int64")
            elif non_null and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null):
                data = np.array([float(value) if value is not None else np.nan for value in values], dtype="float64")
            else:
                data = np.array(
                    [
                        value
                        if isinstance(value, str) or value is None
                        else json.dumps(value, ensure_ascii=False, sort_keys=True)
                        for value in values
                    ],
                    dtype=object,
                )
            field_data.append(data)
            field_mask.append(np.array([value is None for value in values], dtype=bool))
        geometry_data = np.array(
            [geojson_to_wkb(feature["geometry"]) for feature in features],
            dtype=object,
        )
        ogr_write(
            destination,
            geometry_data,
            field_data,
            field_names,
            field_mask=field_mask,
            layer=_layer_name(geometry_type.lower(), used_names),
            driver="GPKG",
            geometry_type=geometry_type,
            crs="EPSG:4326",
            append=layer_index > 0,
        )
    inspect_geopackage(destination)


@dataclass(frozen=True)
class MBTilesInfo:
    name: str
    format: str
    min_zoom: int
    max_zoom: int
    tile_count: int
    bounds: list[float] | None
    vector_layers: list[str]
    metadata: dict[str, str]


def _sqlite_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def inspect_mbtiles(path: Path) -> MBTilesInfo:
    try:
        with path.open("rb") as source:
            if source.read(16) != b"SQLite format 3\x00":
                raise ValueError("Missing SQLite header.")
        with closing(sqlite3.connect(_sqlite_uri(path), uri=True)) as connection:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            if not {"metadata", "tiles"}.issubset(table_names):
                raise ValueError("Required MBTiles tables are missing.")
            metadata = {
                str(name): str(value)
                for name, value in connection.execute("SELECT name, value FROM metadata")
            }
            tile_count, actual_min, actual_max = connection.execute(
                "SELECT COUNT(*), MIN(zoom_level), MAX(zoom_level) FROM tiles"
            ).fetchone()
            if not tile_count:
                raise ValueError("The MBTiles archive contains no tiles.")
            tile_format = metadata.get("format", "").lower()
            if tile_format not in MBTILES_FORMAT_MEDIA_TYPES:
                raise ValueError("The MBTiles format metadata is missing or unsupported.")
            min_zoom = int(metadata.get("minzoom", actual_min))
            max_zoom = int(metadata.get("maxzoom", actual_max))
            bounds = None
            if metadata.get("bounds"):
                values = [float(value) for value in metadata["bounds"].split(",")]
                if len(values) != 4 or not all(math.isfinite(value) for value in values):
                    raise ValueError("The MBTiles bounds metadata is invalid.")
                bounds = values
            vector_layers: list[str] = []
            if metadata.get("json"):
                tile_json = json.loads(metadata["json"])
                for layer in tile_json.get("vector_layers", []):
                    if isinstance(layer, dict) and isinstance(layer.get("id"), str):
                        vector_layers.append(layer["id"])
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
        raise _format_error(
            "INVALID_MBTILES",
            "The MBTiles archive is invalid.",
            "A readable SQLite archive with metadata and non-empty tiles is required.",
        ) from exc
    return MBTilesInfo(
        name=metadata.get("name") or path.stem,
        format=tile_format,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        tile_count=int(tile_count),
        bounds=bounds,
        vector_layers=vector_layers,
        metadata=metadata,
    )


def mbtiles_metadata(path: Path) -> dict[str, Any]:
    info = inspect_mbtiles(path)
    return {
        "file_size": path.stat().st_size,
        "name": info.name,
        "tile_format": info.format,
        "tile_media_type": MBTILES_FORMAT_MEDIA_TYPES[info.format],
        "min_zoom": info.min_zoom,
        "max_zoom": info.max_zoom,
        "tile_count": info.tile_count,
        "bounds": None
        if info.bounds is None
        else {
            "min_x": info.bounds[0],
            "min_y": info.bounds[1],
            "max_x": info.bounds[2],
            "max_y": info.bounds[3],
        },
        "crs": "EPSG:4326",
        "vector_layers": info.vector_layers,
    }


def read_mbtiles_tile(path: Path, z: int, x: int, y: int) -> tuple[bytes, str, bool]:
    if min(z, x, y) < 0 or z > 30 or x >= (1 << z) or y >= (1 << z):
        raise ApplicationError(
            status_code=404,
            code="TILE_NOT_FOUND",
            message="The requested tile was not found.",
            details="The tile coordinates are outside the archive range.",
        )
    info = inspect_mbtiles(path)
    tms_y = (1 << z) - 1 - y
    try:
        with closing(sqlite3.connect(_sqlite_uri(path), uri=True)) as connection:
            row = connection.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                (z, x, tms_y),
            ).fetchone()
    except sqlite3.Error as exc:
        raise _format_error(
            "INVALID_MBTILES",
            "The MBTiles archive could not be read.",
            "The tile database query failed.",
        ) from exc
    if row is None:
        raise ApplicationError(
            status_code=404,
            code="TILE_NOT_FOUND",
            message="The requested tile was not found.",
            details="No tile exists at the requested coordinates.",
        )
    data = bytes(row[0])
    is_gzip = data.startswith(b"\x1f\x8b")
    return data, MBTILES_FORMAT_MEDIA_TYPES[info.format], is_gzip


def build_mbtiles(
    tile_root: Path,
    destination: Path,
    *,
    name: str,
    bounds: dict[str, Any] | None = None,
) -> MBTilesInfo:
    tile_files = sorted(
        path
        for path in tile_root.glob("*/*/*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".pbf"}
    )
    if not tile_files:
        raise ApplicationError(
            status_code=409,
            code="TILES_NOT_AVAILABLE",
            message="No generated tiles are available for export.",
            details="Complete tile generation before exporting MBTiles.",
        )
    extension = tile_files[0].suffix.lower().lstrip(".")
    tile_format = "jpg" if extension == "jpeg" else extension
    if any(("jpg" if path.suffix.lower() == ".jpeg" else path.suffix.lower().lstrip(".")) != tile_format for path in tile_files):
        raise ApplicationError(
            status_code=409,
            code="MIXED_TILE_FORMATS",
            message="The generated tiles use multiple formats.",
            details="MBTiles export requires one tile encoding per archive.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    zoom_levels = [int(path.relative_to(tile_root).parts[0]) for path in tile_files]
    metadata_rows = {
        "name": name,
        "type": "baselayer",
        "version": "1.3",
        "description": f"Generated by MapTiler Clone for {name}",
        "format": tile_format,
        "minzoom": str(min(zoom_levels)),
        "maxzoom": str(max(zoom_levels)),
    }
    if bounds:
        values = [
            bounds.get("min_longitude", bounds.get("min_x")),
            bounds.get("min_latitude", bounds.get("min_y")),
            bounds.get("max_longitude", bounds.get("max_x")),
            bounds.get("max_latitude", bounds.get("max_y")),
        ]
        if all(value is not None and math.isfinite(float(value)) for value in values):
            metadata_rows["bounds"] = ",".join(str(float(value)) for value in values)
    try:
        with closing(sqlite3.connect(destination)) as connection:
            connection.executescript(
                """
                PRAGMA application_id = 1297103682;
                CREATE TABLE metadata (name TEXT NOT NULL, value TEXT);
                CREATE TABLE tiles (
                    zoom_level INTEGER NOT NULL,
                    tile_column INTEGER NOT NULL,
                    tile_row INTEGER NOT NULL,
                    tile_data BLOB NOT NULL
                );
                CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
                """
            )
            connection.executemany(
                "INSERT INTO metadata(name, value) VALUES (?, ?)",
                sorted(metadata_rows.items()),
            )
            with connection:
                for path in tile_files:
                    relative = path.relative_to(tile_root)
                    z = int(relative.parts[0])
                    x = int(relative.parts[1])
                    y = int(path.stem)
                    tms_y = (1 << z) - 1 - y
                    connection.execute(
                        "INSERT INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                        (z, x, tms_y, path.read_bytes()),
                    )
    except (OSError, sqlite3.Error, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise ApplicationError(
            status_code=500,
            code="MBTILES_EXPORT_FAILED",
            message="The MBTiles archive could not be created.",
            details="Generated tiles could not be written to SQLite.",
        ) from exc
    return inspect_mbtiles(destination)


def maybe_decompress_tile(data: bytes, is_gzip: bool) -> bytes:
    return gzip.decompress(data) if is_gzip else data
