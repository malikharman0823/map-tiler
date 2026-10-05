from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class Dataset:
    filename: str
    file_size: int
    content_type: str | None
    file_hash: str
    storage_path: str
    extracted_metadata: dict[str, Any]
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    georeferenced_path: str | None = None
    georeference_status: str = "not_started"
    processed_path: str | None = None
    process_status: str = "not_started"
    tile_path: str | None = None
    tile_min_zoom: int | None = None
    tile_max_zoom: int | None = None
    tile_status: str = "not_started"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
