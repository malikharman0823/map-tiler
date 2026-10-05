import hashlib
import logging
from typing import BinaryIO

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from functions.file_hash.response import FileHashData, FileHashResponse
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
HASH_CHUNK_SIZE = 1024 * 1024


def _calculate_sha256(source: BinaryIO) -> str:
    hash_object = hashlib.sha256()
    try:
        source.seek(0)
        while chunk := source.read(HASH_CHUNK_SIZE):
            hash_object.update(chunk)
        return hash_object.hexdigest()
    finally:
        source.seek(0)


async def calculate_file_hash(file: UploadFile | None) -> FileHashResponse:
    if file is None:
        raise ApplicationError(
            status_code=400,
            code="FILE_REQUIRED",
            message="A file is required.",
            details="No file was included in the upload request.",
            field="file",
        )

    try:
        file_hash = await run_in_threadpool(_calculate_sha256, file.file)
    except Exception as exc:
        logger.exception("Failed to calculate the uploaded file hash.", exc_info=exc)
        raise ApplicationError(
            status_code=500,
            code="HASH_ERROR",
            message="The file hash could not be calculated.",
            details="The server encountered an error while reading the uploaded file.",
            field="file",
        ) from exc

    return FileHashResponse(
        data=FileHashData(
            file_hash=file_hash,
            message="File hash calculated successfully.",
        )
    )
