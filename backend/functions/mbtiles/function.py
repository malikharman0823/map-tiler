from uuid import UUID

from fastapi.responses import Response

from storage.session import SessionRepository
from functions.formats.function import (
    read_mbtiles_tile,
    resolve_managed_path,
)
from schemas.error import ApplicationError


def get_mbtiles_tile(
    dataset_id: UUID,
    z: int,
    x: int,
    y: int,
    db: SessionRepository,
) -> Response:
    dataset = db.get_dataset(dataset_id)
    if dataset is None:
        raise ApplicationError(
            status_code=404,
            code="DATASET_NOT_FOUND",
            message="The dataset was not found.",
            details="No dataset exists with the requested identifier.",
        )
    metadata = dataset.extracted_metadata
    archive_path_value = metadata.get("mbtiles_path")
    if not archive_path_value and str(metadata.get("format", "")).lower() == "mbtiles":
        archive_path_value = dataset.storage_path
    if not isinstance(archive_path_value, str):
        raise ApplicationError(
            status_code=409,
            code="MBTILES_NOT_AVAILABLE",
            message="No MBTiles archive is available for this dataset.",
            details="Import MBTiles or generate a portable tile archive first.",
        )
    archive_path = resolve_managed_path(archive_path_value)
    if not archive_path.is_file():
        raise ApplicationError(
            status_code=404,
            code="MBTILES_NOT_FOUND",
            message="The MBTiles archive is unavailable.",
            details="The managed MBTiles file does not exist.",
        )
    data, media_type, is_gzip = read_mbtiles_tile(archive_path, z, x, y)
    headers = {"Cache-Control": "public, max-age=3600"}
    if is_gzip:
        headers["Content-Encoding"] = "gzip"
    return Response(content=data, media_type=media_type, headers=headers)
