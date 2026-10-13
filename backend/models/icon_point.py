from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class IconPoint:
    dataset_id: uuid.UUID
    latitude: float
    longitude: float
    icon_key: str | None = None
    description: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
