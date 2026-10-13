from pathlib import Path
from typing import Any
from uuid import UUID
from pydantic import BaseModel

from storage.session import SessionRepository
from models.dataset import Dataset


class WorkspaceTableRecord(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str
    sublayer_type: str  # "raster" | "control_point" | "icon_point"
    name: str
    local_storage_path: str
    georeferenced_path: str | None = None
    coordinates: str
    pixel_coordinates: str | None = None
    bounds: list[float] | None = None
    crs: str
    status: str  # "georeferenced" | "raw" | "tiled"
    visible: bool = True
    metadata: dict[str, Any] = {}
    created_at: str | None = None


class WorkspaceTableRecordsResponse(BaseModel):
    success: bool = True
    total_records: int
    datasets_count: int
    records: list[WorkspaceTableRecord]


def get_workspace_table_records(
    db: SessionRepository,
    dataset_ids: list[UUID] | None = None,
) -> WorkspaceTableRecordsResponse:
    if dataset_ids:
        datasets: list[Dataset] = []
        for did in dataset_ids:
            ds = db.get_dataset(did)
            if ds:
                datasets.append(ds)
    else:
        datasets = db.list_datasets()

    records: list[WorkspaceTableRecord] = []

    for dataset in datasets:
        ds_id_str = str(dataset.id)
        storage_path_abs = str(Path(dataset.storage_path).resolve())
        georef_path_abs = (
            str(Path(dataset.georeferenced_path).resolve())
            if dataset.georeferenced_path
            else None
        )

        # 1. Raster Layer Record
        crs_val = dataset.extracted_metadata.get("crs") or (
            "EPSG:4326" if dataset.georeferenced_path else "Unprojected"
        )
        is_geo = bool(
            dataset.georeference_status == "completed"
            or dataset.georeferenced_path
            or (dataset.extracted_metadata.get("crs") and dataset.extracted_metadata.get("crs") != "Unknown")
        )
        status_val = "georeferenced" if is_geo else "raw"
        if dataset.tile_status == "completed":
            status_val = "tiled"

        bounds_val = dataset.extracted_metadata.get("bounds")
        parsed_bounds: list[float] | None = None
        coord_display = "—"
        if isinstance(bounds_val, (list, tuple)) and len(bounds_val) == 4:
            try:
                parsed_bounds = [float(v) for v in bounds_val]
                coord_display = f"[{parsed_bounds[0]:.4f}, {parsed_bounds[1]:.4f}, {parsed_bounds[2]:.4f}, {parsed_bounds[3]:.4f}]"
            except (ValueError, TypeError):
                pass
        elif isinstance(bounds_val, dict):
            try:
                left = float(bounds_val.get("left", bounds_val.get("min_x", 0)))
                bottom = float(bounds_val.get("bottom", bounds_val.get("min_y", 0)))
                right = float(bounds_val.get("right", bounds_val.get("max_x", 0)))
                top = float(bounds_val.get("top", bounds_val.get("max_y", 0)))
                parsed_bounds = [left, bottom, right, top]
                coord_display = f"[{left:.4f}, {bottom:.4f}, {right:.4f}, {top:.4f}]"
            except (ValueError, TypeError):
                pass

        raster_record = WorkspaceTableRecord(
            id=f"raster-{ds_id_str}",
            dataset_id=ds_id_str,
            dataset_name=dataset.filename,
            sublayer_type="raster",
            name=dataset.filename,
            local_storage_path=storage_path_abs,
            georeferenced_path=georef_path_abs,
            coordinates=coord_display,
            pixel_coordinates=f"{dataset.extracted_metadata.get('width', '—')} × {dataset.extracted_metadata.get('height', '—')} px",
            bounds=parsed_bounds,
            crs=str(crs_val),
            status=status_val,
            visible=True,
            metadata={
                "file_size": dataset.file_size,
                "content_type": dataset.content_type,
                "tile_status": dataset.tile_status,
                "georeference_status": dataset.georeference_status,
                "width": dataset.extracted_metadata.get("width"),
                "height": dataset.extracted_metadata.get("height"),
                "format": dataset.extracted_metadata.get("format"),
            },
            created_at=dataset.created_at.isoformat() if dataset.created_at else None,
        )
        records.append(raster_record)

        # 2. Control Points Sublayers
        control_points = db.list_control_points(dataset.id)
        for idx, cp in enumerate(control_points):
            cp_record = WorkspaceTableRecord(
                id=str(cp.id),
                dataset_id=ds_id_str,
                dataset_name=dataset.filename,
                sublayer_type="control_point",
                name=f"Control Point #{idx + 1}",
                local_storage_path=storage_path_abs,
                georeferenced_path=georef_path_abs,
                coordinates=f"Lat {cp.latitude:.6f}, Lng {cp.longitude:.6f}",
                pixel_coordinates=f"X: {cp.image_x}, Y: {cp.image_y}",
                bounds=None,
                crs="EPSG:4326",
                status="georeferenced",
                visible=True,
                metadata={
                    "point_index": idx + 1,
                    "image_x": cp.image_x,
                    "image_y": cp.image_y,
                    "latitude": cp.latitude,
                    "longitude": cp.longitude,
                },
                created_at=cp.created_at.isoformat() if cp.created_at else None,
            )
            records.append(cp_record)

        # 3. User Icon Points Sublayers
        icon_points = db.list_icon_points(dataset.id)
        for idx, ip in enumerate(icon_points):
            ip_record = WorkspaceTableRecord(
                id=str(ip.id),
                dataset_id=ds_id_str,
                dataset_name=dataset.filename,
                sublayer_type="icon_point",
                name=ip.description or f"Icon #{idx + 1} ({ip.icon_key})",
                local_storage_path=storage_path_abs,
                georeferenced_path=georef_path_abs,
                coordinates=f"Lat {ip.latitude:.6f}, Lng {ip.longitude:.6f}",
                pixel_coordinates=None,
                bounds=None,
                crs="EPSG:4326",
                status="georeferenced",
                visible=True,
                metadata={
                    "icon_key": ip.icon_key,
                    "description": ip.description,
                    "latitude": ip.latitude,
                    "longitude": ip.longitude,
                },
                created_at=ip.created_at.isoformat() if ip.created_at else None,
            )
            records.append(ip_record)

    return WorkspaceTableRecordsResponse(
        success=True,
        total_records=len(records),
        datasets_count=len(datasets),
        records=records,
    )
