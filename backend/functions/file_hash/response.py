from typing import Literal

from pydantic import BaseModel


class FileHashData(BaseModel):
    file_hash: str
    algorithm: Literal["sha256"] = "sha256"
    message: str


class FileHashResponse(BaseModel):
    success: Literal[True] = True
    data: FileHashData
