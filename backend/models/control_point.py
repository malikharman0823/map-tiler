from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class ControlPoint:
    dataset_id: uuid.UUID
    image_x: float
    image_y: float
    longitude: float
    latitude: float
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
