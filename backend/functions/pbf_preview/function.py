import json
import logging
from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID

import osmium
from starlette.concurrency import run_in_threadpool

from database import DatabaseError, DatabaseSession
from functions.pbf_preview.response import PbfPreviewData, PbfPreviewResponse
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOADS_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
POINT_FEATURE_LIMIT = 1_000
WAY_FEATURE_LIMIT = 4_000
COORDINATE_LIMIT = 200_000
TAG_LIMIT = 32
TAG_VALUE_LIMIT = 256
POLYGON_TAGS = {
    "amenity",
    "building",
    "boundary",
    "landuse",
    "leisure",
    "natural",
    "place",
    "shop",
    "tourism",
    "water",
}


def _bounds_dict(values: list[float] | None) -> dict[str, float] | None:
    if values is None:
        return None
    return {
        "min_x": values[0],
        "min_y": values[1],
        "max_x": values[2],
        "max_y": values[3],
    }


def _safe_tags(tags: Any) -> dict[str, str]:
    properties: dict[str, str] = {}
    for index, tag in enumerate(tags):
        if index >= TAG_LIMIT:
            break
        properties[str(tag.k)[:TAG_VALUE_LIMIT]] = str(tag.v)[:TAG_VALUE_LIMIT]
    return properties


def _is_polygon(tags: dict[str, str], closed: bool) -> bool:
    if not closed or tags.get("area") == "no":
        return False
    return tags.get("area") == "yes" or any(key in tags for key in POLYGON_TAGS)


class _OsmPreviewHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.node_count = 0
        self.way_count = 0
        self.relation_count = 0
        self.point_feature_count = 0
        self.way_feature_count = 0
        self.coordinate_count = 0
        self.features: list[dict[str, Any]] = []
        self.bounds: list[float] | None = None
        self.truncated = False

    def _extend_bounds(self, coordinates: list[list[float]]) -> None:
        for longitude, latitude in coordinates:
            if self.bounds is None:
                self.bounds = [longitude, latitude, longitude, latitude]
            else:
                self.bounds[0] = min(self.bounds[0], longitude)
                self.bounds[1] = min(self.bounds[1], latitude)
                self.bounds[2] = max(self.bounds[2], longitude)
                self.bounds[3] = max(self.bounds[3], latitude)

    def node(self, node: Any) -> None:
        self.node_count += 1
        if not node.tags:
            return
        if self.point_feature_count >= POINT_FEATURE_LIMIT:
            self.truncated = True
            return
        try:
            if not node.location.valid():
                return
            coordinates = [float(node.lon), float(node.lat)]
        except (RuntimeError, ValueError):
            return

        properties = {"osm_id": str(node.id), "osm_type": "node"}
        properties.update(_safe_tags(node.tags))
        self.features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "Point", "coordinates": coordinates},
            }
        )
        self.point_feature_count += 1
        self.coordinate_count += 1
        self._extend_bounds([coordinates])

    def way(self, way: Any) -> None:
        self.way_count += 1
        if not way.tags:
            return
        if self.way_feature_count >= WAY_FEATURE_LIMIT:
            self.truncated = True
            return

        try:
            coordinates = [
                [float(node.lon), float(node.lat)]
                for node in way.nodes
                if node.location.valid()
            ]
        except (RuntimeError, ValueError):
            return
        if len(coordinates) < 2:
            return
        if self.coordinate_count + len(coordinates) > COORDINATE_LIMIT:
            self.truncated = True
            return

        tags = _safe_tags(way.tags)
        closed = len(coordinates) >= 4 and coordinates[0] == coordinates[-1]
        geometry: dict[str, Any]
        if _is_polygon(tags, closed):
            geometry = {"type": "Polygon", "coordinates": [coordinates]}
        else:
            geometry = {"type": "LineString", "coordinates": coordinates}

        properties = {"osm_id": str(way.id), "osm_type": "way"}
        properties.update(tags)
        self.features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            }
        )
        self.way_feature_count += 1
        self.coordinate_count += len(coordinates)
        self._extend_bounds(coordinates)

    def relation(self, relation: Any) -> None:
        self.relation_count += 1


def _preview_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.name}.preview.geojson")


def _write_preview(file_path: Path, preview: dict[str, Any]) -> None:
    preview_path = _preview_path(file_path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(preview, temporary_file, separators=(",", ":"))
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(preview_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_pbf_with_preview(
    file_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    handler = _OsmPreviewHandler()
    try:
        handler.apply_file(
            str(file_path),
            locations=True,
            idx="flex_mem",
        )
    except Exception as exc:
        raise ApplicationError(
            status_code=400,
            code="INVALID_OSM_FILE",
            message="The OSM PBF file is invalid.",
            details="The stored file does not contain readable OSM PBF data.",
            field="file",
        ) from exc

    bounds = _bounds_dict(handler.bounds)
    preview = {
        "geojson": {
            "type": "FeatureCollection",
            "features": handler.features,
        },
        "feature_count": len(handler.features),
        "truncated": handler.truncated,
        "bounds": bounds,
    }
    _write_preview(file_path, preview)
    metadata = {
        "file_size": file_path.stat().st_size,
        "node_count": handler.node_count,
        "way_count": handler.way_count,
        "relation_count": handler.relation_count,
        "preview_feature_count": len(handler.features),
        "preview_truncated": handler.truncated,
        "crs": "EPSG:4326",
        "bounds": bounds,
    }
    return metadata, preview


def _read_cached_preview(file_path: Path) -> dict[str, Any] | None:
    preview_path = _preview_path(file_path)
    if not preview_path.is_file() or preview_path.stat().st_mtime < file_path.stat().st_mtime:
        return None
    try:
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(preview, dict) or "geojson" not in preview:
        return None
    return preview


def load_or_create_pbf_preview(file_path: Path) -> dict[str, Any]:
    cached_preview = _read_cached_preview(file_path)
    if cached_preview is not None:
        return cached_preview
    _, preview = parse_pbf_with_preview(file_path)
    return preview


def _dataset_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="DATASET_NOT_FOUND",
        message="The dataset was not found.",
        details="No dataset exists for the supplied dataset ID.",
        field="dataset_id",
    )


def _load_pbf_path(dataset_id: UUID, db: DatabaseSession) -> Path:
    try:
        dataset = db.get_dataset(dataset_id)
    except DatabaseError as exc:
        db.rollback()
        raise ApplicationError(
            status_code=500,
            code="DATABASE_ERROR",
            message="The PBF preview could not be loaded.",
            details="The database operation failed.",
        ) from exc
    if dataset is None:
        raise _dataset_not_found()
    if not dataset.filename.lower().endswith(".pbf"):
        raise ApplicationError(
            status_code=400,
            code="PBF_REQUIRED",
            message="This dataset is not an OSM PBF file.",
            details="PBF preview is available only for .pbf and .osm.pbf files.",
            field="dataset_id",
        )

    dataset_directory = (UPLOADS_DIRECTORY / str(dataset.id)).resolve()
    file_path = (dataset_directory / dataset.filename).resolve()
    if file_path.parent != dataset_directory or not file_path.is_file():
        raise ApplicationError(
            status_code=404,
            code="PBF_FILE_NOT_FOUND",
            message="The OSM PBF file was not found.",
            details="The stored dataset file is unavailable.",
            field="dataset_id",
        )
    return file_path


async def get_pbf_preview(
    dataset_id: UUID,
    db: DatabaseSession,
) -> PbfPreviewResponse:
    file_path = _load_pbf_path(dataset_id, db)
    try:
        preview = await run_in_threadpool(load_or_create_pbf_preview, file_path)
    except ApplicationError:
        raise
    except Exception as exc:
        logger.exception("Failed to create an OSM PBF preview.", exc_info=exc)
        raise ApplicationError(
            status_code=500,
            code="PBF_PREVIEW_ERROR",
            message="The OSM PBF preview could not be created.",
            details="The stored file could not be converted for map display.",
            field="dataset_id",
        ) from exc
    return PbfPreviewResponse(data=PbfPreviewData(**preview))
