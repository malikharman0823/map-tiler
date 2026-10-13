from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class GeoreferenceConfig:
    dataset_id: uuid.UUID
    transformation: str
    source_file_hash: str
    source_crs: str | None
    target_crs: str
    source_width: int
    source_height: int
    control_point_count: int
    source_coordinate_system: dict[str, Any]
    transformation_parameters: dict[str, Any]
    output_path: str
    output_format: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: str = "pending"
    is_active: bool = True
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
