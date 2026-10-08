from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class GeoreferenceSummary(BaseModel):
    id: UUID
    status: str
    transformation: str
    control_point_count: int
    target_crs: str
    source_width: int
    source_height: int
    output_format: str
    output_path: str


class GeographicBounds(BaseModel):
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float


class MapLayerSummary(BaseModel):
    name: str
    status: Literal["completed"] = "completed"
    source_crs: str
    bounds_crs: Literal["EPSG:4326"] = "EPSG:4326"
    bounds: GeographicBounds
    tile_url_template: str
    tile_min_zoom: int
    tile_max_zoom: int
    tile_size: int = 256
    format: Literal["png"] = "png"


class DatasetDetailData(BaseModel):
    id: UUID
    filename: str
    file_size: int
    content_type: str | None
    file_hash: str
    storage_path: str
    metadata: dict[str, Any]
    georeferenced_path: str | None
    georeference_status: str
    processed_path: str | None
    process_status: str
    tile_path: str | None
    tile_min_zoom: int | None
    tile_max_zoom: int | None
    tile_status: str
    georeference: GeoreferenceSummary | None = None
    map_layer: MapLayerSummary | None = None
    created_at: datetime


class DatasetDetailResponse(BaseModel):
    success: Literal[True] = True
    data: DatasetDetailData
