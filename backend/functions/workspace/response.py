from datetime import datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field

from functions.dataset_detail.response import DatasetDetailData


class WorkspaceSublayerSummary(BaseModel):
    kind: Literal["raster", "control_point", "icon_point"]
    label: str
    count: int
    visible: bool


class WorkspaceMemberData(BaseModel):
    id: UUID
    dataset_id: UUID
    alias: str | None
    name: str
    sort_order: int
    is_primary: bool
    visible: bool
    raster_visible: bool
    control_points_visible: bool
    icon_points_visible: bool
    raster_opacity: float
    sublayers: list[WorkspaceSublayerSummary]
    dataset: DatasetDetailData
    created_at: datetime
    updated_at: datetime


class WorkspaceCamera(BaseModel):
    longitude: float
    latitude: float
    zoom: float
    bearing: float = 0
    pitch: float = 0


class WorkspaceManifestData(BaseModel):
    id: UUID
    primary_dataset_id: UUID
    name: str
    active_view: Literal["map", "database"] = "map"
    camera: WorkspaceCamera | None = None
    members: list[WorkspaceMemberData]
    created_at: datetime
    updated_at: datetime


class WorkspaceManifestResponse(BaseModel):
    success: Literal[True] = True
    data: WorkspaceManifestData


class WorkspaceRecordBase(BaseModel):
    id: str
    kind: str
    member_id: UUID
    dataset_id: UUID
    dataset_name: str
    name: str
    status: str
    visible: bool
    managed_path: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RasterWorkspaceRecord(WorkspaceRecordBase):
    kind: Literal["raster"] = "raster"
    georeferenced_path: str | None = None
    crs: str | None = None
    bounds: list[float] | dict[str, float] | None = None
    width: int | None = None
    height: int | None = None
    opacity: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlPointWorkspaceRecord(WorkspaceRecordBase):
    kind: Literal["control_point"] = "control_point"
    pair_number: int
    image_x: float
    image_y: float
    longitude: float
    latitude: float
    crs: Literal["EPSG:4326"] = "EPSG:4326"


class IconPointWorkspaceRecord(WorkspaceRecordBase):
    kind: Literal["icon_point"] = "icon_point"
    icon_key: str | None = None
    description: str | None = None
    longitude: float
    latitude: float
    crs: Literal["EPSG:4326"] = "EPSG:4326"


WorkspaceRecord = Annotated[
    Union[
        RasterWorkspaceRecord,
        ControlPointWorkspaceRecord,
        IconPointWorkspaceRecord,
    ],
    Field(discriminator="kind"),
]


class WorkspaceRecordsData(BaseModel):
    records: list[WorkspaceRecord]
    total: int
    page: int
    page_size: int
    pages: int


class WorkspaceRecordsResponse(BaseModel):
    success: Literal[True] = True
    data: WorkspaceRecordsData
