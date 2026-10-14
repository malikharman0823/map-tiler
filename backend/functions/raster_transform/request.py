from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class CoordinatePoint(BaseModel):
    longitude: float = Field(..., ge=-180.0, le=180.0)
    latitude: float = Field(..., ge=-90.0, le=90.0)


class RasterCorners(BaseModel):
    top_left: CoordinatePoint
    top_right: CoordinatePoint
    bottom_right: CoordinatePoint
    bottom_left: CoordinatePoint


class RasterTransformRequest(BaseModel):
    action: Literal["apply", "preview", "undo", "redo", "reset", "status"] = "apply"
    mode: Literal["move", "resize", "rotate", "free", "control_points"] = "free"
    corners: RasterCorners | None = None
    pivot: CoordinatePoint | None = None
    rotation_angle: float | None = Field(default=None, description="Angle in degrees if rotate mode")
    lock_aspect_ratio: bool = False
    target_crs: str = "EPSG:3857"
    resampling: Literal["nearest", "bilinear", "cubic"] = "bilinear"
