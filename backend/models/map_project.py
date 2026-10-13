from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

@dataclass
class MapProject:
    name: str
    dataset_id: uuid.UUID | None
    configuration: dict
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

