import asyncio
from contextlib import asynccontextmanager
import io
import logging
import zipfile
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from storage.session import (
    RepositoryError,
    SessionRepository,
    cleanup_expired_sessions,
    cleanup_orphaned_storage,
    get_session_repository,
    initialize_sessions,
    session_storage,
    validate_session_id,
)
from functions.dataset_delete.function import delete_dataset
from functions.dataset_delete.request import DatasetDeleteRequest
from functions.dataset_delete.response import DatasetDeleteResponse
from functions.dataset_detail.function import (
    get_dataset_detail,
    get_dataset_source_image,
)
from functions.dataset_detail.request import DatasetDetailRequest
from functions.dataset_detail.response import DatasetDetailResponse
from functions.dataset_list.function import list_datasets
from functions.dataset_list.response import DatasetListResponse
from functions.control_points.function import (
    create_control_point,
    delete_control_point,
    list_control_points,
    update_control_point,
)
from functions.control_points.request import (
    ControlPointRequest,
    CreateControlPointRequest,
    DatasetControlPointsRequest,
    UpdateControlPointRequest,
)
from functions.control_points.response import (
    ControlPointListResponse,
    ControlPointResponse,
)
from functions.georeference.function import (
    georeference_dataset,
    get_georeference_config,
    mark_georeference_publication_failed,
)
from functions.georeference.request import (
    GeoreferenceOptionsRequest,
    GeoreferenceRequest,
)
from functions.georeference.response import (
    GeoreferenceLookupResponse,
    GeoreferenceResponse,
)
from functions.pbf_preview.function import get_pbf_preview
from functions.pbf_preview.response import PbfPreviewResponse
from functions.raster_process.function import process_raster
from functions.raster_process.request import (
    RasterProcessOptionsRequest,
    RasterProcessRequest,
)
from functions.raster_process.response import RasterProcessResponse
from functions.tile_generation.function import generate_tiles
from functions.tile_generation.request import (
    TileGenerationOptionsRequest,
    TileGenerationRequest,
)
from functions.tile_generation.response import TileGenerationResponse
from functions.tile_read.function import read_tile
from functions.tile_read.request import TileReadRequest
from functions.tile_read.response import TILE_READ_RESPONSES
from functions.upload.function import upload_file
from functions.upload.response import UploadData, UploadResponse
from functions.raster_zip.function import import_raster_zip
from functions.icon_points.function import (
    create_icon_point,
    delete_icon_point,
    list_icon_points,
    update_icon_point,
)
from functions.icon_points.request import (
    CreateIconPointRequest,
    DatasetIconPointsRequest,
    UpdateIconPointRequest,
    IconPointRequest,
)
from functions.icon_points.response import (
    IconPointListResponse,
    IconPointResponse,
)
from functions.map_projects.request import MapProjectUpdateRequest
from functions.map_projects.response import MapProjectResponse
from functions.map_projects.function import get_project, update_project
from functions.map_projects.export import export_project
from functions.map_projects.import_func import import_project
from functions.map_projects.import_folder import import_project_folder
from functions.vector_preview.function import get_vector_preview
from functions.mbtiles.function import get_mbtiles_tile
from functions.workspace.layers import (
    WorkspaceTableRecordsResponse,
    get_workspace_table_records as get_legacy_workspace_table_records,
)
from functions.workspace.function import (
    attach_workspace_member,
    detach_workspace_member,
    get_workspace_manifest,
    get_workspace_records,
    update_workspace_member,
    update_workspace_state,
)
from functions.workspace.request import (
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceStateUpdateRequest,
)
from functions.workspace.response import (
    WorkspaceManifestResponse,
    WorkspaceRecordsResponse,
)
from models.dataset import Dataset
from schemas.error import ApplicationError, make_error_response
from functions.background_removal.request import BackgroundRemovalRequest
from functions.background_removal.response import BackgroundRemovalResponse
from functions.background_removal.function import (
    get_background_removal_status,
    handle_background_removal,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_sessions()
    cleanup_orphaned_storage()

    stop_event = asyncio.Event()

    async def _cleanup_loop():
        while not stop_event.is_set():
            try:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                cleanup_expired_sessions()
                cleanup_orphaned_storage()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in background session cleanup loop")

    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    stop_event.set()
    cleanup_task.cancel()
    # On server shutdown, purge all active session data and temporary images
    if not settings.restore_sessions_on_startup:
        session_storage.purge_all_sessions()


app = FastAPI(title="MapTiler Clone API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "ETag", "X-Session-ID"],
)


@app.middleware("http")
async def session_header_middleware(request: Request, call_next):
    response = await call_next(request)
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        response.headers["X-Session-ID"] = session_id
    return response


@app.exception_handler(ApplicationError)
async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    logger.warning("Application error [%s]: %s - %s (field: %s)", exc.code, exc.message, exc.details, exc.field)
    return make_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        field=exc.field,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = first_error.get("loc", ())
    field = str(location[-1]) if location else None
    if field in {"latitude", "longitude"}:
        return make_error_response(
            status_code=422,
            code="INVALID_COORDINATES",
            message="The map coordinates are invalid.",
            details=(
                "Latitude must be between -90 and 90 and longitude must be "
                "between -180 and 180."
            ),
            field=field,
        )
    if field in {"image_x", "image_y"}:
        return make_error_response(
            status_code=422,
            code="INVALID_IMAGE_COORDINATES",
            message="The image coordinates are invalid.",
            details="Image X and Y coordinates must be zero or greater.",
            field=field,
        )
    return make_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="The request contains invalid data.",
        details="One or more fields failed validation.",
        field=field,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if exc.status_code == 404:
        return make_error_response(
            status_code=404,
            code="NOT_FOUND",
            message="The requested resource was not found.",
            details="The requested API route does not exist.",
        )

    return make_error_response(
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message="The request could not be completed.",
        details="The server rejected the request.",
    )


@app.exception_handler(RepositoryError)
async def repository_error_handler(
    request: Request,
    exc: RepositoryError,
) -> JSONResponse:
    logger.exception("A session repository operation failed.", exc_info=exc)
    return make_error_response(
        status_code=500,
        code="DATABASE_ERROR",
        message="A session storage error occurred.",
        details="The operation could not be completed.",
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("An unexpected server error occurred.", exc_info=exc)
    return make_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred.",
        details="The server could not complete the request.",
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {"success": True, "data": {"status": "ok"}}


from storage.session import session_storage, validate_session_id
from storage.session import cleanup_expired_sessions


@app.post("/sessions", status_code=201)
def create_session_endpoint() -> dict[str, object]:
    repo = session_storage.create_session()
    return {
        "success": True,
        "data": {
            "session_id": repo.session_id,
            "status": repo.status,
            "created_at": repo.created_at.isoformat(),
            "last_accessed_at": repo.last_accessed_at.isoformat(),
        },
    }


@app.get("/sessions/current")
def get_current_session_endpoint(db: SessionRepository = Depends(get_session_repository)) -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "session_id": db.session_id,
            "status": db.status,
            "created_at": db.created_at.isoformat(),
            "last_accessed_at": db.last_accessed_at.isoformat(),
            "dataset_count": len(db.datasets),
            "map_configuration": db.get_map_configuration(),
        },
    }


@app.get("/sessions/{session_id}")
def get_session_endpoint(session_id: str) -> dict[str, object]:
    clean_id = validate_session_id(session_id)
    repo = session_storage.get_session(clean_id)
    if repo is None:
        raise StarletteHTTPException(status_code=404, detail="Session not found or expired")
    return {
        "success": True,
        "data": {
            "session_id": repo.session_id,
            "status": repo.status,
            "created_at": repo.created_at.isoformat(),
            "last_accessed_at": repo.last_accessed_at.isoformat(),
            "dataset_count": len(repo.datasets),
            "map_configuration": repo.get_map_configuration(),
        },
    }


@app.post("/sessions/current/end")
@app.delete("/sessions/current")
def end_current_session_endpoint(db: SessionRepository = Depends(get_session_repository)) -> dict[str, object]:
    sid = db.session_id
    success = session_storage.end_session(sid, force=True)
    cleanup_orphaned_storage()
    return {
        "success": True,
        "data": {
            "session_id": sid,
            "terminated": success,
            "message": "Current session ended and all image data deleted.",
        },
    }


@app.post("/sessions/{session_id}/end")
@app.delete("/sessions/{session_id}")
def end_session_endpoint(session_id: str) -> dict[str, object]:
    clean_id = validate_session_id(session_id)
    success = session_storage.end_session(clean_id, force=True)
    cleanup_orphaned_storage()
    return {
        "success": True,
        "data": {
            "session_id": clean_id,
            "terminated": success,
            "message": "Session ended and all temporary image and workspace data removed.",
        },
    }


@app.get("/sessions/{session_id}/map-config")
def get_session_map_config_endpoint(session_id: str) -> dict[str, object]:
    clean_id = validate_session_id(session_id)
    repo = session_storage.get_session(clean_id)
    if repo is None:
        raise StarletteHTTPException(status_code=404, detail="Session not found")
    return {"success": True, "data": repo.get_map_configuration()}


@app.put("/sessions/{session_id}/map-config")
def save_session_map_config_endpoint(session_id: str, config: dict[str, object]) -> dict[str, object]:
    clean_id = validate_session_id(session_id)
    repo = session_storage.get_session(clean_id)
    if repo is None:
        raise StarletteHTTPException(status_code=404, detail="Session not found")
    repo.save_map_configuration(config)
    return {"success": True, "data": repo.get_map_configuration()}


@app.post("/sessions/cleanup")
def trigger_cleanup_endpoint() -> dict[str, object]:
    cleaned = cleanup_expired_sessions()
    return {"success": True, "data": {"cleaned_sessions": cleaned}}


import os
from pydantic import BaseModel

class IconListResponse(BaseModel):
    icons: list[str]

@app.get("/icons", response_model=IconListResponse)
def get_icons() -> IconListResponse:
    icon_dir = os.environ.get("ICON_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "icons"))
    if not icon_dir or not os.path.exists(icon_dir):
        return IconListResponse(icons=[])
    icons = [f for f in os.listdir(icon_dir) if f.endswith(('.png', '.svg', '.jpg', '.jpeg'))]
    icon_keys = [os.path.splitext(f)[0] for f in icons]
    return IconListResponse(icons=icon_keys)


@app.get("/icons/{icon_key}", response_class=FileResponse)
def get_icon(icon_key: str) -> FileResponse:
    icon_dir = os.environ.get("ICON_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "icons"))
    if not icon_dir or not os.path.exists(icon_dir):
        raise StarletteHTTPException(status_code=404, detail="Icon directory not configured")

    # Try finding the file with any supported extension
    for ext in ['.png', '.svg', '.jpg', '.jpeg']:
        path = os.path.join(icon_dir, f"{icon_key}{ext}")
        if os.path.exists(path):
            return FileResponse(path)

    raise StarletteHTTPException(status_code=404, detail="Icon not found")


async def _try_import_project_zip(file: UploadFile, db: SessionRepository) -> UploadResponse | None:
    try:
        await file.seek(0)
        content = await file.read()
        await file.seek(0)
        bio = io.BytesIO(content)
        if zipfile.is_zipfile(bio):
            with zipfile.ZipFile(bio, "r") as z:
                if "mapstudio.json" in z.namelist():
                    await file.seek(0)
                    project_res = await import_project(file, db)
                    dataset = (
                        db.get_dataset(project_res.dataset_id)
                        if project_res.dataset_id is not None
                        else None
                    )
                    if dataset is not None:
                        return UploadResponse(
                            data=UploadData(
                                id=dataset.id,
                                filename=dataset.filename,
                                file_size=dataset.file_size,
                                content_type=dataset.content_type,
                                file_hash=dataset.file_hash,
                                storage_path=dataset.storage_path,
                                metadata=dataset.extracted_metadata or {},
                                existing=False,
                                message="Project package imported successfully.",
                                is_georeferenced=dataset.georeferenced_path is not None,
                                georeference_status=dataset.georeference_status,
                            )
                        )
    except Exception:
        await file.seek(0)
    return None


@app.post("/upload", response_model=UploadResponse, status_code=201)
async def upload(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile | None, File()] = None,
    db: SessionRepository = Depends(get_session_repository),
) -> UploadResponse:
    if file is not None and (file.filename or "").lower().endswith(".zip"):
        project_resp = await _try_import_project_zip(file, db)
        if project_resp is not None:
            return project_resp
        return await import_raster_zip(
            file=file,
            db=db,
            background_tasks=background_tasks,
        )
    return await upload_file(file=file, db=db, background_tasks=background_tasks)


@app.post("/datasets/import-zip", response_model=UploadResponse, status_code=201)
async def import_dataset_zip(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile | None, File()] = None,
    db: SessionRepository = Depends(get_session_repository),
) -> UploadResponse:
    if file is not None and not (file.filename or "").lower().endswith(".zip"):
        return await upload_file(file=file, db=db, background_tasks=background_tasks)
    if file is not None:
        project_resp = await _try_import_project_zip(file, db)
        if project_resp is not None:
            return project_resp
    return await import_raster_zip(
        file=file,
        db=db,
        background_tasks=background_tasks,
    )


@app.get("/datasets", response_model=DatasetListResponse)
def get_datasets(
    db: SessionRepository = Depends(get_session_repository),
) -> DatasetListResponse:
    return list_datasets(db)


@app.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> DatasetDetailResponse:
    return get_dataset_detail(
        DatasetDetailRequest(dataset_id=dataset_id),
        db,
    )


@app.get("/datasets/{dataset_id}/source-image", response_class=FileResponse)
def get_dataset_source(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> FileResponse:
    source_image = get_dataset_source_image(dataset_id, db)
    return FileResponse(
        path=source_image.path,
        media_type=source_image.media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get(
    "/datasets/{dataset_id}/pbf-preview",
    response_model=PbfPreviewResponse,
)
async def get_dataset_pbf_preview(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> PbfPreviewResponse:
    return await get_pbf_preview(dataset_id, db)


@app.get("/datasets/{dataset_id}/vector-preview")
def get_dataset_vector_preview(
    dataset_id: UUID,
    raw: bool = False,
    db: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    response = get_vector_preview(dataset_id, db)
    data = response.get("data")
    if raw and isinstance(data, dict):
        geojson_data = data.get("geojson")
        if isinstance(geojson_data, dict):
            return geojson_data
    return response


@app.get("/datasets/{dataset_id}/mbtiles/{z}/{x}/{y}")
def read_dataset_mbtiles_tile(
    dataset_id: UUID,
    z: int,
    x: int,
    y: int,
    db: SessionRepository = Depends(get_session_repository),
):
    return get_mbtiles_tile(dataset_id, z, x, y, db)


@app.delete("/datasets/{dataset_id}", response_model=DatasetDeleteResponse)
def remove_dataset(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> DatasetDeleteResponse:
    return delete_dataset(
        DatasetDeleteRequest(dataset_id=dataset_id),
        db,
    )


@app.get(
    "/datasets/{dataset_id}/background-removal",
    response_model=BackgroundRemovalResponse,
)
def get_dataset_background_removal(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> BackgroundRemovalResponse:
    return get_background_removal_status(dataset_id, db)


@app.post(
    "/datasets/{dataset_id}/background-removal",
    response_model=BackgroundRemovalResponse,
)
def post_dataset_background_removal(
    dataset_id: UUID,
    request: BackgroundRemovalRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> BackgroundRemovalResponse:
    return handle_background_removal(dataset_id, request, db)


@app.post(
    "/datasets/{dataset_id}/control-points",
    response_model=ControlPointResponse,
    status_code=201,
)
def create_dataset_control_point(
    dataset_id: UUID,
    request: CreateControlPointRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> ControlPointResponse:
    return create_control_point(
        DatasetControlPointsRequest(dataset_id=dataset_id),
        request,
        db,
    )


@app.get(
    "/datasets/{dataset_id}/control-points",
    response_model=ControlPointListResponse,
)
def get_dataset_control_points(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> ControlPointListResponse:
    return list_control_points(
        DatasetControlPointsRequest(dataset_id=dataset_id),
        db,
    )


@app.put(
    "/control-points/{control_point_id}",
    response_model=ControlPointResponse,
)
def replace_control_point(
    control_point_id: UUID,
    request: UpdateControlPointRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> ControlPointResponse:
    return update_control_point(
        ControlPointRequest(control_point_id=control_point_id),
        request,
        db,
    )


@app.delete(
    "/control-points/{control_point_id}",
    response_model=ControlPointResponse,
)
def remove_control_point(
    control_point_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> ControlPointResponse:
    return delete_control_point(
        ControlPointRequest(control_point_id=control_point_id),
        db,
    )


@app.post(
    "/datasets/{dataset_id}/georeference",
    response_model=GeoreferenceResponse,
)
def georeference_raster_dataset(
    dataset_id: UUID,
    request: GeoreferenceOptionsRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> GeoreferenceResponse:
    response = georeference_dataset(
        GeoreferenceRequest(
            dataset_id=dataset_id,
            **request.model_dump(),
        ),
        db,
    )
    if request.action != "save":
        return response
    try:
        process_raster(
            RasterProcessRequest(
                dataset_id=dataset_id,
                target_crs="EPSG:3857",
                resampling="bilinear",
            ),
            db,
        )
        generate_tiles(
            TileGenerationRequest(
                dataset_id=dataset_id,
                min_zoom=0,
                max_zoom=18,
            ),
            db,
        )
    except ApplicationError:
        mark_georeference_publication_failed(dataset_id, db)
        raise
    return response


@app.get(
    "/datasets/{dataset_id}/georeference",
    response_model=GeoreferenceLookupResponse,
)
def get_saved_georeference(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> GeoreferenceLookupResponse:
    return get_georeference_config(dataset_id, db)


@app.post(
    "/datasets/{dataset_id}/icon-points",
    response_model=IconPointResponse,
    status_code=201,
)
def create_dataset_icon_point(
    dataset_id: UUID,
    request: CreateIconPointRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> IconPointResponse:
    return create_icon_point(
        DatasetIconPointsRequest(dataset_id=dataset_id), request, db
    )


@app.get(
    "/datasets/{dataset_id}/icon-points",
    response_model=IconPointListResponse,
)
def get_dataset_icon_points(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> IconPointListResponse:
    return list_icon_points(
        DatasetIconPointsRequest(dataset_id=dataset_id), db
    )


@app.put("/icon-points/{icon_point_id}", response_model=IconPointResponse)
def replace_icon_point(
    icon_point_id: UUID,
    request: UpdateIconPointRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> IconPointResponse:
    return update_icon_point(
        IconPointRequest(icon_point_id=icon_point_id), request, db
    )


@app.delete("/icon-points/{icon_point_id}", response_model=IconPointResponse)
def remove_icon_point(
    icon_point_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> IconPointResponse:
    return delete_icon_point(
        IconPointRequest(icon_point_id=icon_point_id), db
    )


@app.post(
    "/datasets/{dataset_id}/process-raster",
    response_model=RasterProcessResponse,
)
def process_raster_dataset(
    dataset_id: UUID,
    request: RasterProcessOptionsRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> RasterProcessResponse:
    return process_raster(
        RasterProcessRequest(
            dataset_id=dataset_id,
            **request.model_dump(),
        ),
        db,
    )


@app.post(
    "/datasets/{dataset_id}/generate-tiles",
    response_model=TileGenerationResponse,
)
def generate_dataset_tiles(
    dataset_id: UUID,
    request: TileGenerationOptionsRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> TileGenerationResponse:
    return generate_tiles(
        TileGenerationRequest(
            dataset_id=dataset_id,
            **request.model_dump(),
        ),
        db,
    )


@app.get(
    "/datasets/{dataset_id}/tiles/{z}/{x}/{y}.png",
    response_class=FileResponse,
    responses=TILE_READ_RESPONSES,
)
def read_dataset_tile(
    dataset_id: UUID,
    z: int,
    x: int,
    y: int,
    db: SessionRepository = Depends(get_session_repository),
) -> FileResponse:
    return read_tile(
        TileReadRequest(dataset_id=dataset_id, z=z, x=x, y=y),
        db,
    )


@app.get("/datasets/{dataset_id}/project", response_model=MapProjectResponse)
def get_map_project(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> MapProjectResponse:
    return get_project(dataset_id, db)


@app.put("/datasets/{dataset_id}/project", response_model=MapProjectResponse)
def put_map_project(
    dataset_id: UUID,
    request: MapProjectUpdateRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> MapProjectResponse:
    return update_project(dataset_id, request, db)


@app.get("/datasets/{dataset_id}/export")
def export_map_project(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
):
    with db.protect_operation("export"):
        return export_project(dataset_id, db)


@app.post("/map-projects/import", response_model=MapProjectResponse)
async def post_import_project(
    file: Annotated[UploadFile, File()],
    db: SessionRepository = Depends(get_session_repository),
) -> MapProjectResponse:
    return await import_project(file, db)


@app.post("/map-projects/import-folder", response_model=MapProjectResponse)
async def post_import_project_folder(
    files: Annotated[list[UploadFile], File()],
    paths: Annotated[list[str], Form()],
    db: SessionRepository = Depends(get_session_repository),
) -> MapProjectResponse:
    return await import_project_folder(files, paths, db)


@app.get("/workspace/table-records", response_model=WorkspaceTableRecordsResponse)
def get_legacy_workspace_records(
    dataset_ids: str | None = None,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceTableRecordsResponse:
    parsed_ids = None
    if dataset_ids:
        try:
            parsed_ids = [UUID(did.strip()) for did in dataset_ids.split(",") if did.strip()]
        except ValueError:
            parsed_ids = None
    return get_legacy_workspace_table_records(db, parsed_ids)


@app.get(
    "/datasets/{dataset_id}/workspace",
    response_model=WorkspaceManifestResponse,
)
def get_dataset_workspace(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceManifestResponse:
    return get_workspace_manifest(dataset_id, db)


@app.post(
    "/datasets/{dataset_id}/workspace/members",
    response_model=WorkspaceManifestResponse,
    status_code=201,
)
def post_dataset_workspace_member(
    dataset_id: UUID,
    request: WorkspaceMemberCreateRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceManifestResponse:
    return attach_workspace_member(dataset_id, request, db)


@app.patch(
    "/datasets/{dataset_id}/workspace/members/{member_dataset_id}",
    response_model=WorkspaceManifestResponse,
)
def patch_dataset_workspace_member(
    dataset_id: UUID,
    member_dataset_id: UUID,
    request: WorkspaceMemberUpdateRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceManifestResponse:
    return update_workspace_member(
        dataset_id,
        member_dataset_id,
        request,
        db,
    )


@app.delete(
    "/datasets/{dataset_id}/workspace/members/{member_dataset_id}",
    response_model=WorkspaceManifestResponse,
)
def delete_dataset_workspace_member(
    dataset_id: UUID,
    member_dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceManifestResponse:
    return detach_workspace_member(dataset_id, member_dataset_id, db)


@app.patch(
    "/datasets/{dataset_id}/workspace/state",
    response_model=WorkspaceManifestResponse,
)
def patch_dataset_workspace_state(
    dataset_id: UUID,
    request: WorkspaceStateUpdateRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceManifestResponse:
    return update_workspace_state(dataset_id, request, db)


@app.get(
    "/datasets/{dataset_id}/workspace/records",
    response_model=WorkspaceRecordsResponse,
)
def get_dataset_workspace_records(
    dataset_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: str | None = None,
    member_dataset_id: UUID | None = None,
    kind: Literal["raster", "control_point", "icon_point"] | None = None,
    status: str | None = None,
    sort: Literal["name", "kind", "dataset", "status", "updated_at"] = "name",
    order: Literal["asc", "desc"] = "asc",
    db: SessionRepository = Depends(get_session_repository),
) -> WorkspaceRecordsResponse:
    return get_workspace_records(
        dataset_id,
        db,
        page=page,
        page_size=page_size,
        search=search,
        dataset_id=member_dataset_id,
        kind=kind,
        status=status,
        sort=sort,
        order=order,
    )


@app.post(
    "/datasets/{dataset_id}/background-removal",
    response_model=BackgroundRemovalResponse,
)
def post_background_removal(
    dataset_id: UUID,
    request: BackgroundRemovalRequest,
    db: SessionRepository = Depends(get_session_repository),
) -> BackgroundRemovalResponse:
    return handle_background_removal(dataset_id, request, db)


@app.get(
    "/datasets/{dataset_id}/background-removal",
    response_model=BackgroundRemovalResponse,
)
def get_background_removal(
    dataset_id: UUID,
    db: SessionRepository = Depends(get_session_repository),
) -> BackgroundRemovalResponse:
    return get_background_removal_status(dataset_id, db)
