from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class WorkspaceMember:
    map_project_id: uuid.UUID
    dataset_id: uuid.UUID
    sort_order: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    alias: str | None = None
    visible: bool = True
    raster_visible: bool = True
    control_points_visible: bool = True
    icon_points_visible: bool = True
    raster_opacity: float = 0.65
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
