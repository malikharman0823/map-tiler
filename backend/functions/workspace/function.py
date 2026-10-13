import math
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID

from storage.session import (
    RepositoryError,
    SessionRepository,
    DuplicateValueError,
)
from functions.dataset_detail.function import get_dataset_detail
from functions.dataset_detail.request import DatasetDetailRequest
from functions.dataset_detail.response import DatasetDetailData, GeoreferenceSummary
from functions.map_projects.function import _ensure_primary_member
from functions.workspace.request import (
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceStateUpdateRequest,
)
from functions.workspace.response import (
    ControlPointWorkspaceRecord,
    IconPointWorkspaceRecord,
    RasterWorkspaceRecord,
    WorkspaceCamera,
    WorkspaceManifestData,
    WorkspaceManifestResponse,
    WorkspaceMemberData,
    WorkspaceRecordsData,
    WorkspaceRecordsResponse,
    WorkspaceSublayerSummary,
)
from models.map_project import MapProject
from models.workspace_member import WorkspaceMember
from schemas.error import ApplicationError


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]


def _error(
    status_code: int,
    code: str,
    message: str,
    details: str,
    field: str | None = None,
) -> ApplicationError:
    return ApplicationError(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        field=field,
    )


def _portable_path(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(BACKEND_DIRECTORY.resolve())
        except (OSError, RuntimeError, ValueError):
            candidate = Path(candidate.name)
    return PurePosixPath(*candidate.parts).as_posix()


def _load_project(primary_dataset_id: UUID, db: SessionRepository) -> MapProject:
    dataset = db.get_dataset(primary_dataset_id)
    if dataset is None:
        raise _error(
            404,
            "DATASET_NOT_FOUND",
            "The primary dataset was not found.",
            "Choose an existing dataset workspace.",
            "dataset_id",
        )
    project = db.get_map_project_by_dataset_id(primary_dataset_id)
    if project is None:
        project = MapProject(
            name=dataset.filename,
            dataset_id=primary_dataset_id,
            configuration={"activeView": "map"},
        )
        db.insert_map_project(project)
    _ensure_primary_member(project, db)
    return project


def _workspace_dataset_detail(dataset_id: UUID, db: SessionRepository) -> DatasetDetailData:
    try:
        detail = get_dataset_detail(
            DatasetDetailRequest(dataset_id=dataset_id),
            db,
        ).data
    except ApplicationError as exc:
        if exc.code not in {"TILE_SOURCE_NOT_FOUND", "RASTER_OUTPUT_NOT_FOUND"}:
            raise
        dataset = db.get_dataset(dataset_id)
        if dataset is None:
            raise
        metadata = dataset.extracted_metadata or {}
        format_type = str(metadata.get("format") or "").lower()
        display_type = (
            "raster"
            if format_type in {"tiff", "tif", "jpg", "jpeg", "png", "mapstudio_folder"}
            else "vector"
            if format_type in {"geojson", "geopackage"}
            else "mbtiles"
            if format_type == "mbtiles"
            else "project"
            if format_type == "mtmap"
            else "unknown"
        )
        is_georeferenced = bool(
            dataset.georeference_status == "completed"
            or (metadata.get("crs") and metadata.get("transform"))
            or format_type in {"geojson", "geopackage", "mbtiles", "mapstudio_folder"}
        )
        configuration = db.get_active_georeference_config(dataset_id)
        detail = DatasetDetailData(
            id=dataset.id,
            filename=dataset.filename,
            file_size=dataset.file_size,
            content_type=dataset.content_type,
            file_hash=dataset.file_hash,
            storage_path=dataset.storage_path,
            metadata=metadata,
            georeferenced_path=dataset.georeferenced_path,
            georeference_status=dataset.georeference_status,
            processed_path=dataset.processed_path,
            process_status=dataset.process_status,
            tile_path=dataset.tile_path,
            tile_min_zoom=dataset.tile_min_zoom,
            tile_max_zoom=dataset.tile_max_zoom,
            tile_status=dataset.tile_status,
            display_type=display_type,
            is_spatial=display_type in {"raster", "vector", "mbtiles"} and is_georeferenced,
            is_georeferenced=is_georeferenced,
            georeference=(
                None
                if configuration is None
                else GeoreferenceSummary(
                    id=configuration.id,
                    status=configuration.status,
                    transformation=configuration.transformation,
                    control_point_count=configuration.control_point_count,
                    target_crs=configuration.target_crs,
                    source_width=configuration.source_width,
                    source_height=configuration.source_height,
                    output_format=configuration.output_format,
                    output_path=_portable_path(configuration.output_path) or "",
                )
            ),
            map_layer=None,
            created_at=dataset.created_at,
        )
    georeference = detail.georeference
    if georeference is not None:
        georeference = georeference.model_copy(
            update={"output_path": _portable_path(georeference.output_path) or ""}
        )
    return detail.model_copy(
        update={
            "storage_path": _portable_path(detail.storage_path) or detail.filename,
            "georeferenced_path": _portable_path(detail.georeferenced_path),
            "processed_path": _portable_path(detail.processed_path),
            "tile_path": _portable_path(detail.tile_path),
            "georeference": georeference,
        }
    )


def _member_data(
    project: MapProject,
    member: WorkspaceMember,
    db: SessionRepository,
) -> WorkspaceMemberData:
    detail = _workspace_dataset_detail(member.dataset_id, db)
    control_count = len(db.list_control_points(member.dataset_id))
    icon_count = len(db.list_icon_points(member.dataset_id))
    name = member.alias or detail.filename
    return WorkspaceMemberData(
        id=member.id,
        dataset_id=member.dataset_id,
        alias=member.alias,
        name=name,
        sort_order=member.sort_order,
        is_primary=member.dataset_id == project.dataset_id,
        visible=member.visible,
        raster_visible=member.raster_visible,
        control_points_visible=member.control_points_visible,
        icon_points_visible=member.icon_points_visible,
        raster_opacity=member.raster_opacity,
        sublayers=[
            WorkspaceSublayerSummary(
                kind="raster",
                label="Raster",
                count=1,
                visible=member.raster_visible,
            ),
            WorkspaceSublayerSummary(
                kind="control_point",
                label="Control Points",
                count=control_count,
                visible=member.control_points_visible,
            ),
            WorkspaceSublayerSummary(
                kind="icon_point",
                label="User Icons",
                count=icon_count,
                visible=member.icon_points_visible,
            ),
        ],
        dataset=detail,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def get_workspace_manifest(
    primary_dataset_id: UUID,
    db: SessionRepository,
) -> WorkspaceManifestResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        db.commit()
        members = db.list_workspace_members(project.id)
        member_data = [_member_data(project, member, db) for member in members]
    except ApplicationError:
        raise
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_LOAD_FAILED",
            "The dataset workspace could not be loaded.",
            "The workspace database state is unavailable.",
        ) from exc

    configuration = project.configuration or {}
    active_view = configuration.get("activeView", "map")
    if active_view not in {"map", "database"}:
        active_view = "map"
    camera_value = configuration.get("camera")
    camera = None
    if isinstance(camera_value, dict):
        try:
            camera = WorkspaceCamera.model_validate(camera_value)
        except ValueError:
            camera = None
    return WorkspaceManifestResponse(
        data=WorkspaceManifestData(
            id=project.id,
            primary_dataset_id=primary_dataset_id,
            name=project.name,
            active_view=active_view,
            camera=camera,
            members=member_data,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
    )


def attach_workspace_member(
    primary_dataset_id: UUID,
    request: WorkspaceMemberCreateRequest,
    db: SessionRepository,
) -> WorkspaceManifestResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        dataset = db.get_dataset(request.dataset_id)
        if dataset is None:
            raise _error(
                404,
                "DATASET_NOT_FOUND",
                "The dataset to attach was not found.",
                "Upload or choose an existing dataset.",
                "dataset_id",
            )
        if db.get_workspace_member(project.id, request.dataset_id) is not None:
            raise _error(
                409,
                "WORKSPACE_MEMBER_EXISTS",
                "The dataset is already attached.",
                "Choose a different dataset or update the existing layer.",
                "dataset_id",
            )
        members = db.list_workspace_members(project.id)
        next_order = max((member.sort_order for member in members), default=-1) + 1
        db.insert_workspace_member(
            WorkspaceMember(
                map_project_id=project.id,
                dataset_id=request.dataset_id,
                sort_order=next_order,
            )
        )
        db.commit()
    except ApplicationError:
        db.rollback()
        raise
    except DuplicateValueError as exc:
        db.rollback()
        raise _error(
            409,
            "WORKSPACE_MEMBER_EXISTS",
            "The dataset is already attached.",
            "Choose a different dataset or update the existing layer.",
            "dataset_id",
        ) from exc
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_UPDATE_FAILED",
            "The dataset could not be attached.",
            "The workspace database update failed.",
        ) from exc
    return get_workspace_manifest(primary_dataset_id, db)


def update_workspace_member(
    primary_dataset_id: UUID,
    member_dataset_id: UUID,
    request: WorkspaceMemberUpdateRequest,
    db: SessionRepository,
) -> WorkspaceManifestResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        member = db.get_workspace_member(project.id, member_dataset_id)
        if member is None:
            raise _error(
                404,
                "WORKSPACE_MEMBER_NOT_FOUND",
                "The workspace layer was not found.",
                "Reload the workspace and try again.",
                "dataset_id",
            )
        values = request.model_dump(exclude_unset=True)
        if "alias" in values and values["alias"] is not None:
            values["alias"] = values["alias"].strip() or None
        for name, value in values.items():
            setattr(member, name, value)
        db.save_workspace_member(member)
        db.commit()
    except ApplicationError:
        db.rollback()
        raise
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_UPDATE_FAILED",
            "The workspace layer could not be updated.",
            "The previous saved settings remain active.",
        ) from exc
    return get_workspace_manifest(primary_dataset_id, db)


def detach_workspace_member(
    primary_dataset_id: UUID,
    member_dataset_id: UUID,
    db: SessionRepository,
) -> WorkspaceManifestResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        if member_dataset_id == project.dataset_id:
            raise _error(
                409,
                "PRIMARY_DATASET_REQUIRED",
                "The primary dataset cannot be detached.",
                "Delete the workspace from the library instead.",
                "dataset_id",
            )
        member = db.get_workspace_member(project.id, member_dataset_id)
        if member is None:
            raise _error(
                404,
                "WORKSPACE_MEMBER_NOT_FOUND",
                "The workspace layer was not found.",
                "Reload the workspace and try again.",
                "dataset_id",
            )
        db.delete_workspace_member(member.id)
        db.commit()
    except ApplicationError:
        db.rollback()
        raise
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_UPDATE_FAILED",
            "The workspace layer could not be detached.",
            "The dataset and its files were not deleted.",
        ) from exc
    return get_workspace_manifest(primary_dataset_id, db)


def update_workspace_state(
    primary_dataset_id: UUID,
    request: WorkspaceStateUpdateRequest,
    db: SessionRepository,
) -> WorkspaceManifestResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        configuration = dict(project.configuration or {})
        if request.active_view is not None:
            configuration["activeView"] = request.active_view
        if request.camera is not None:
            configuration["camera"] = request.camera.model_dump()
        project.configuration = configuration
        db.save_map_project(project)
        db.commit()
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_STATE_SAVE_FAILED",
            "The workspace view could not be saved.",
            "Retry the workspace save.",
        ) from exc
    return get_workspace_manifest(primary_dataset_id, db)


def _build_records(
    project: MapProject,
    members: list[WorkspaceMember],
    db: SessionRepository,
):
    records = []
    for member in members:
        dataset = db.get_dataset(member.dataset_id)
        if dataset is None:
            continue
        alias = member.alias or dataset.filename
        metadata = dataset.extracted_metadata or {}
        is_georeferenced = bool(
            dataset.georeference_status == "completed"
            or (metadata.get("crs") and metadata.get("transform"))
        )
        status = (
            "tiled"
            if dataset.tile_status == "completed"
            else "georeferenced"
            if is_georeferenced
            else "raw"
        )
        records.append(
            RasterWorkspaceRecord(
                id=f"raster-{dataset.id}",
                member_id=member.id,
                dataset_id=dataset.id,
                dataset_name=alias,
                name=alias,
                status=status,
                visible=member.visible and member.raster_visible,
                managed_path=_portable_path(dataset.storage_path) or dataset.filename,
                georeferenced_path=_portable_path(dataset.georeferenced_path),
                crs=metadata.get("crs"),
                bounds=metadata.get("bounds"),
                width=metadata.get("width"),
                height=metadata.get("height"),
                opacity=member.raster_opacity,
                metadata={
                    "format": metadata.get("format"),
                    "content_type": dataset.content_type,
                    "file_size": dataset.file_size,
                    "process_status": dataset.process_status,
                    "tile_status": dataset.tile_status,
                },
                created_at=dataset.created_at,
                updated_at=dataset.created_at,
            )
        )
        for index, point in enumerate(db.list_control_points(dataset.id), start=1):
            records.append(
                ControlPointWorkspaceRecord(
                    id=str(point.id),
                    member_id=member.id,
                    dataset_id=dataset.id,
                    dataset_name=alias,
                    name=f"Control Point {index}",
                    status="georeferenced" if is_georeferenced else "pending",
                    visible=member.visible and member.control_points_visible,
                    managed_path=_portable_path(dataset.storage_path) or dataset.filename,
                    pair_number=index,
                    image_x=point.image_x,
                    image_y=point.image_y,
                    longitude=point.longitude,
                    latitude=point.latitude,
                    created_at=point.created_at,
                    updated_at=point.updated_at,
                )
            )
        for index, point in enumerate(db.list_icon_points(dataset.id), start=1):
            records.append(
                IconPointWorkspaceRecord(
                    id=str(point.id),
                    member_id=member.id,
                    dataset_id=dataset.id,
                    dataset_name=alias,
                    name=point.description or f"User Icon {index}",
                    status="georeferenced",
                    visible=member.visible and member.icon_points_visible,
                    managed_path=_portable_path(dataset.storage_path) or dataset.filename,
                    icon_key=point.icon_key,
                    description=point.description,
                    longitude=point.longitude,
                    latitude=point.latitude,
                    created_at=point.created_at,
                    updated_at=point.updated_at,
                )
            )
    return records


def get_workspace_records(
    primary_dataset_id: UUID,
    db: SessionRepository,
    *,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    dataset_id: UUID | None = None,
    kind: Literal["raster", "control_point", "icon_point"] | None = None,
    status: str | None = None,
    sort: Literal["name", "kind", "dataset", "status", "updated_at"] = "name",
    order: Literal["asc", "desc"] = "asc",
) -> WorkspaceRecordsResponse:
    try:
        project = _load_project(primary_dataset_id, db)
        db.commit()
        members = db.list_workspace_members(project.id)
        records = _build_records(project, members, db)
    except ApplicationError:
        raise
    except RepositoryError as exc:
        db.rollback()
        raise _error(
            500,
            "WORKSPACE_RECORDS_FAILED",
            "Workspace records could not be loaded.",
            "The database query failed.",
        ) from exc

    if dataset_id is not None:
        records = [record for record in records if record.dataset_id == dataset_id]
    if kind is not None:
        records = [record for record in records if record.kind == kind]
    if status:
        normalized_status = status.strip().lower()
        records = [record for record in records if record.status.lower() == normalized_status]
    if search and search.strip():
        needle = search.strip().lower()
        records = [
            record
            for record in records
            if needle
            in " ".join(
                [record.name, record.dataset_name, record.kind, record.status]
            ).lower()
        ]

    key_functions = {
        "name": lambda record: record.name.lower(),
        "kind": lambda record: record.kind,
        "dataset": lambda record: record.dataset_name.lower(),
        "status": lambda record: record.status,
        "updated_at": lambda record: str(record.updated_at or record.created_at or ""),
    }
    records.sort(key=key_functions[sort], reverse=order == "desc")
    total = len(records)
    start = (page - 1) * page_size
    return WorkspaceRecordsResponse(
        data=WorkspaceRecordsData(
            records=records[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )
    )
