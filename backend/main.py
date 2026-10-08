import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import DatabaseError, DatabaseSession, get_db, initialize_database
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
from functions.upload.response import UploadResponse
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
from functions.vector_preview.function import get_vector_preview
from functions.mbtiles.function import get_mbtiles_tile
from models.dataset import Dataset
from schemas.error import ApplicationError, make_error_response


logger = logging.getLogger(__name__)


app = FastAPI(title="MapTiler Clone API")


@app.on_event("startup")
def create_missing_database_tables() -> None:
    initialize_database()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "ETag"],
)


@app.exception_handler(ApplicationError)
async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
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


@app.exception_handler(DatabaseError)
async def database_error_handler(
    request: Request,
    exc: DatabaseError,
) -> JSONResponse:
    logger.exception("A database operation failed.", exc_info=exc)
    return make_error_response(
        status_code=500,
        code="DATABASE_ERROR",
        message="A database error occurred.",
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


@app.post("/upload", response_model=UploadResponse, status_code=201)
async def upload(
    file: Annotated[UploadFile | None, File()] = None,
    db: DatabaseSession = Depends(get_db),
) -> UploadResponse:
    return await upload_file(file=file, db=db)


@app.get("/datasets", response_model=DatasetListResponse)
def get_datasets(
    db: DatabaseSession = Depends(get_db),
) -> DatasetListResponse:
    return list_datasets(db)


@app.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    dataset_id: UUID,
    db: DatabaseSession = Depends(get_db),
) -> DatasetDetailResponse:
    return get_dataset_detail(
        DatasetDetailRequest(dataset_id=dataset_id),
        db,
    )


@app.get("/datasets/{dataset_id}/source-image", response_class=FileResponse)
def get_dataset_source(
    dataset_id: UUID,
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
) -> PbfPreviewResponse:
    return await get_pbf_preview(dataset_id, db)


@app.get("/datasets/{dataset_id}/vector-preview")
def get_dataset_vector_preview(
    dataset_id: UUID,
    raw: bool = False,
    db: DatabaseSession = Depends(get_db),
) -> dict[str, object]:
    response = get_vector_preview(dataset_id, db)
    return response["data"]["geojson"] if raw else response


@app.get("/datasets/{dataset_id}/mbtiles/{z}/{x}/{y}")
def read_dataset_mbtiles_tile(
    dataset_id: UUID,
    z: int,
    x: int,
    y: int,
    db: DatabaseSession = Depends(get_db),
):
    return get_mbtiles_tile(dataset_id, z, x, y, db)


@app.delete("/datasets/{dataset_id}", response_model=DatasetDeleteResponse)
def remove_dataset(
    dataset_id: UUID,
    db: DatabaseSession = Depends(get_db),
) -> DatasetDeleteResponse:
    return delete_dataset(
        DatasetDeleteRequest(dataset_id=dataset_id),
        db,
    )


@app.post(
    "/datasets/{dataset_id}/control-points",
    response_model=ControlPointResponse,
    status_code=201,
)
def create_dataset_control_point(
    dataset_id: UUID,
    request: CreateControlPointRequest,
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
) -> IconPointListResponse:
    return list_icon_points(
        DatasetIconPointsRequest(dataset_id=dataset_id), db
    )


@app.put("/icon-points/{icon_point_id}", response_model=IconPointResponse)
def replace_icon_point(
    icon_point_id: UUID,
    request: UpdateIconPointRequest,
    db: DatabaseSession = Depends(get_db),
) -> IconPointResponse:
    return update_icon_point(
        IconPointRequest(icon_point_id=icon_point_id), request, db
    )


@app.delete("/icon-points/{icon_point_id}", response_model=IconPointResponse)
def remove_icon_point(
    icon_point_id: UUID,
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
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
    db: DatabaseSession = Depends(get_db),
) -> FileResponse:
    return read_tile(
        TileReadRequest(dataset_id=dataset_id, z=z, x=x, y=y),
        db,
    )


@app.get("/datasets/{dataset_id}/project", response_model=MapProjectResponse)
def get_map_project(
    dataset_id: UUID,
    db: DatabaseSession = Depends(get_db),
) -> MapProjectResponse:
    return get_project(dataset_id, db)


@app.put("/datasets/{dataset_id}/project", response_model=MapProjectResponse)
def put_map_project(
    dataset_id: UUID,
    request: MapProjectUpdateRequest,
    db: DatabaseSession = Depends(get_db),
) -> MapProjectResponse:
    return update_project(dataset_id, request, db)


@app.get("/datasets/{dataset_id}/export/{format}")
def export_map_project(
    dataset_id: UUID,
    format: str,
    db: DatabaseSession = Depends(get_db),
):
    return export_project(dataset_id, format, db)


@app.post("/map-projects/import", response_model=MapProjectResponse)
async def post_import_project(
    file: Annotated[UploadFile, File()],
    db: DatabaseSession = Depends(get_db),
) -> MapProjectResponse:
    return await import_project(file, db)
