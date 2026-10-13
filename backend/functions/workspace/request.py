from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceMemberCreateRequest(BaseModel):
    dataset_id: UUID


class WorkspaceMemberUpdateRequest(BaseModel):
    alias: str | None = Field(default=None, max_length=255)
    sort_order: int | None = Field(default=None, ge=0)
    visible: bool | None = None
    raster_visible: bool | None = None
    control_points_visible: bool | None = None
    icon_points_visible: bool | None = None
    raster_opacity: float | None = Field(default=None, ge=0, le=1)


class WorkspaceCameraRequest(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    zoom: float = Field(ge=0, le=24)
    bearing: float = Field(default=0, ge=-360, le=360)
    pitch: float = Field(default=0, ge=0, le=85)


class WorkspaceStateUpdateRequest(BaseModel):
    active_view: Literal["map", "database"] | None = None
    camera: WorkspaceCameraRequest | None = None
