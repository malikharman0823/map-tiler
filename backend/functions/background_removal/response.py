from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, Field


class BackgroundRemovalData(BaseModel):
    dataset_id: UUID
    status: str = Field(description="'preview', 'completed', 'reset', or 'not_configured'")
    enabled: bool = False
    color: str = "#ffffff"
    threshold: int = 30
    edge_softness: int = 10
    preview_data_url: str | None = None
    original_data_url: str | None = None
    tile_url_template: str | None = None
    message: str | None = None
    updated_at: str | None = None


class BackgroundRemovalResponse(BaseModel):
    data: BackgroundRemovalData
