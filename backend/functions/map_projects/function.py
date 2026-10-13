import logging
from uuid import UUID, uuid4

from storage.session import RepositoryError, SessionRepository
from models.map_project import MapProject
from models.workspace_member import WorkspaceMember
from schemas.error import ApplicationError
from functions.map_projects.request import MapProjectUpdateRequest
from functions.map_projects.response import MapProjectResponse

logger = logging.getLogger(__name__)


def _ensure_primary_member(project: MapProject, db: SessionRepository) -> None:
    if project.dataset_id is None:
        return
    member = db.get_workspace_member(project.id, project.dataset_id)
    if member is not None:
        return
    visibility = project.configuration.get("layerVisibility") or {}
    opacity = project.configuration.get("opacity", 0.65)
    try:
        opacity = min(1.0, max(0.0, float(opacity)))
    except (TypeError, ValueError):
        opacity = 0.65
    db.insert_workspace_member(
        WorkspaceMember(
            map_project_id=project.id,
            dataset_id=project.dataset_id,
            sort_order=0,
            raster_visible=bool(visibility.get("dataset", True)),
            control_points_visible=bool(visibility.get("controlPoints", True)),
            icon_points_visible=bool(visibility.get("iconPoints", True)),
            raster_opacity=opacity,
        )
    )

def get_project(dataset_id: UUID, db: SessionRepository) -> MapProjectResponse:
    try:
        project = db.get_map_project_by_dataset_id(dataset_id)
        if not project:
            project = MapProject(
                name="Untitled Project",
                dataset_id=dataset_id,
                configuration={},
            )
            db.insert_map_project(project)
        _ensure_primary_member(project, db)
        db.commit()
        
        return MapProjectResponse(
            id=project.id,
            name=project.name,
            dataset_id=project.dataset_id,
            configuration=project.configuration,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to get map project.", exc_info=exc)
        raise ApplicationError(status_code=500, code="DATABASE_ERROR", message="Failed to retrieve map project", details=str(exc))

def update_project(dataset_id: UUID, request: MapProjectUpdateRequest, db: SessionRepository) -> MapProjectResponse:
    try:
        project = db.get_map_project_by_dataset_id(dataset_id)
        if not project:
            project = MapProject(
                name=request.name or "Untitled Project",
                dataset_id=dataset_id,
                configuration=request.configuration,
            )
            db.insert_map_project(project)
        else:
            if request.name is not None:
                project.name = request.name
            project.configuration = request.configuration
            db.save_map_project(project)
        _ensure_primary_member(project, db)
        db.commit()

        return MapProjectResponse(
            id=project.id,
            name=project.name,
            dataset_id=project.dataset_id,
            configuration=project.configuration,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to update map project.", exc_info=exc)
        raise ApplicationError(status_code=500, code="DATABASE_ERROR", message="Failed to update map project", details=str(exc))

