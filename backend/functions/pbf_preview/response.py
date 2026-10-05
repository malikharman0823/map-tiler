from typing import Any, Literal

from pydantic import BaseModel


class PbfPreviewData(BaseModel):
    geojson: dict[str, Any]
    feature_count: int
    truncated: bool
    bounds: dict[str, float] | None


class PbfPreviewResponse(BaseModel):
    success: Literal[True] = True
    data: PbfPreviewData
