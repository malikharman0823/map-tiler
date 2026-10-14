from __future__ import annotations

from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field

from functions.raster_transform.request import CoordinatePoint, RasterCorners


class RasterTransformData(BaseModel):
    dataset_id: UUID
    status: str = Field(description="'completed', 'preview', 'reset', 'undone', 'redone', 'not_configured'")
    corners: RasterCorners | None = None
    original_corners: RasterCorners | None = None
    bounds: list[float] | None = None  # [min_lng, min_lat, max_lng, max_lat]
    width: int | None = None
    height: int | None = None
    crs: str | None = None
    rotation_angle: float | None = None
    lock_aspect_ratio: bool = False
    can_undo: bool = False
    can_redo: bool = False
    history_length: int = 0
    tile_url_template: str | None = None
    updated_at: str | None = None
    message: str | None = None


class RasterTransformResponse(BaseModel):
    data: RasterTransformData
