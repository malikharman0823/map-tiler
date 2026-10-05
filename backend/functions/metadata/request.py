from pydantic import BaseModel


class MetadataRequest(BaseModel):
    file_path: str
    format: str
    category: str
