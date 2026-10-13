from typing import Any
from uuid import UUID

from storage.session import SessionRepository
from functions.formats.function import (
    MAX_VECTOR_PREVIEW_FEATURES,
    as_feature_collection,
    geopackage_preview,
    read_json_document,
    resolve_managed_path,
    validate_geojson,
)
from schemas.error import ApplicationError


def get_vector_preview(dataset_id: UUID, db: SessionRepository) -> dict[str, Any]:
    dataset = db.get_dataset(dataset_id)
    if dataset is None:
        raise ApplicationError(
            status_code=404,
            code="DATASET_NOT_FOUND",
            message="The dataset was not found.",
            details="No dataset exists with the requested identifier.",
        )
    source_path = resolve_managed_path(dataset.storage_path)
    if not source_path.is_file():
        raise ApplicationError(
            status_code=404,
            code="SOURCE_FILE_NOT_FOUND",
            message="The dataset source file is unavailable.",
            details="The managed source file does not exist.",
        )
    format_name = str(dataset.extracted_metadata.get("format") or "").lower()
    if not format_name:
        format_name = {
            ".gpkg": "geopackage",
            ".geojson": "geojson",
        }.get(source_path.suffix.lower(), "")
    if format_name == "geopackage":
        preview = geopackage_preview(source_path)
    elif format_name == "geojson":
        document = read_json_document(source_path)
        validate_geojson(document)
        collection = as_feature_collection(document)
        features = collection["features"]
        preview = {
            "geojson": {
                "type": "FeatureCollection",
                "features": features[:MAX_VECTOR_PREVIEW_FEATURES],
            },
            "truncated": len(features) > MAX_VECTOR_PREVIEW_FEATURES,
            "feature_limit": MAX_VECTOR_PREVIEW_FEATURES,
            "layers": [],
        }
    else:
        raise ApplicationError(
            status_code=409,
            code="VECTOR_PREVIEW_UNAVAILABLE",
            message="A vector preview is not available for this dataset.",
            details="Only GeoJSON and vector GeoPackage datasets use this preview endpoint.",
        )
    return {"success": True, "data": preview}
