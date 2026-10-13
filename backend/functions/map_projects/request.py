from pydantic import BaseModel
from uuid import UUID

class MapProjectUpdateRequest(BaseModel):
    name: str | None = None
    configuration: dict

class MapProjectImportRequest(BaseModel):
    # This will be handled as form data with a file
    pass
