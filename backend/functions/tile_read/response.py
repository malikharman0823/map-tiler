from typing import Any

TILE_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The requested PNG map tile.",
        "content": {"image/png": {}},
    }
}
