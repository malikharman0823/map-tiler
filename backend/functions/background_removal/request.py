from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class BackgroundRemovalRequest(BaseModel):
    action: Literal["apply", "preview", "reset", "status"] = "apply"
    color: str = Field(default="#ffffff", description="Hex color of the background to remove, e.g. #ffffff")
    threshold: int = Field(default=30, ge=0, le=255, description="Color distance tolerance (0-255)")
    edge_softness: int = Field(default=10, ge=0, le=100, description="Soft transition width for antialiased edges")

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.startswith("#"):
            cleaned = cleaned[1:]
        if len(cleaned) not in {3, 6}:
            raise ValueError("Color must be a 3-character or 6-character hex string (e.g. #ffffff or #fff).")
        try:
            int(cleaned, 16)
        except ValueError as exc:
            raise ValueError("Color must contain valid hexadecimal characters.") from exc
        return f"#{cleaned.lower()}"
