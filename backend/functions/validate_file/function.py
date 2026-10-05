import os
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from database import settings
from functions.validate_file.response import ValidateFileData, ValidateFileResponse
from schemas.error import ApplicationError


SUPPORTED_FORMATS = {
    ".jpg": {"format": "jpg", "category": "raster"},
    ".jpeg": {"format": "jpeg", "category": "raster"},
    ".png": {"format": "png", "category": "raster"},
    ".tif": {"format": "tiff", "category": "raster"},
    ".tiff": {"format": "tiff", "category": "raster"},
    ".kml": {"format": "kml", "category": "vector"},
    ".kmz": {"format": "kmz", "category": "vector"},
    ".shp": {"format": "shapefile", "category": "vector"},
    ".shx": {"format": "shapefile", "category": "vector"},
    ".dbf": {"format": "shapefile", "category": "vector"},
    ".prj": {"format": "shapefile", "category": "vector"},
    ".cpg": {"format": "shapefile", "category": "vector"},
    ".osm": {"format": "osm", "category": "osm"},
    ".pbf": {"format": "osm_pbf", "category": "osm"},
    ".osm.pbf": {"format": "osm_pbf", "category": "osm"},
}


def _get_filename(filename: str | None) -> str:
    if not filename:
        raise ApplicationError(
            status_code=400,
            code="INVALID_FILENAME",
            message="The uploaded file has an invalid filename.",
            details="A valid filename is required to determine the file format.",
            field="filename",
        )

    safe_filename = PurePosixPath(filename.replace("\\", "/")).name
    if not safe_filename or safe_filename in {".", ".."}:
        raise ApplicationError(
            status_code=400,
            code="INVALID_FILENAME",
            message="The uploaded file has an invalid filename.",
            details="A valid filename is required to determine the file format.",
            field="filename",
        )
    return safe_filename


def _get_extension(filename: str) -> str:
    lowercase_filename = filename.lower()
    if lowercase_filename.endswith(".osm.pbf"):
        return ".osm.pbf"
    return Path(lowercase_filename).suffix


def _measure_file(source: BinaryIO) -> int:
    original_position = source.tell()
    try:
        source.seek(0, os.SEEK_END)
        return source.tell()
    finally:
        source.seek(original_position)


async def validate_file(file: UploadFile | None) -> ValidateFileResponse:
    if file is None:
        raise ApplicationError(
            status_code=400,
            code="FILE_REQUIRED",
            message="A file is required.",
            details="No file was included in the upload request.",
            field="file",
        )

    filename = _get_filename(file.filename)
    extension = _get_extension(filename)
    format_details = SUPPORTED_FORMATS.get(extension)

    if format_details is None:
        raise ApplicationError(
            status_code=400,
            code="UNSUPPORTED_FILE_TYPE",
            message="The uploaded file type is not supported.",
            details=(
                "Supported formats are JPG, JPEG, PNG, TIFF, KML, KMZ, "
                "Shapefile components, OSM, and OSM PBF."
            ),
            field="filename",
        )

    file_size = file.size
    if file_size is None:
        file_size = await run_in_threadpool(_measure_file, file.file)

    if file_size == 0:
        raise ApplicationError(
            status_code=400,
            code="EMPTY_FILE",
            message="The uploaded file is empty.",
            details="The file contains no data and cannot be processed.",
            field="file",
        )

    maximum_size_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > maximum_size_bytes:
        raise ApplicationError(
            status_code=413,
            code="FILE_TOO_LARGE",
            message="The uploaded file is too large.",
            details=(
                f"The maximum allowed file size is "
                f"{settings.max_upload_size_mb} MB."
            ),
            field="file",
        )

    return ValidateFileResponse(
        data=ValidateFileData(
            filename=filename,
            extension=extension,
            format=format_details["format"],
            category=format_details["category"],
            file_size=file_size,
            content_type=file.content_type,
            message="File is valid.",
        )
    )
