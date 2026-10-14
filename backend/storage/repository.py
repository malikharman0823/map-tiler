from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any
from uuid import UUID, uuid4

from config import settings
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.georeference_config import GeoreferenceConfig
from models.icon_point import IconPoint
from models.map_project import MapProject
from models.workspace_member import WorkspaceMember
from schemas.error import ApplicationError

logger = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Base exception for session repository operations."""


class DuplicateValueError(RepositoryError):
    """A unique constraint in the session repository was violated."""


class SessionClosingError(RepositoryError):
    """The session is closing or ended and cannot accept new operations."""


class QuotaExceededError(RepositoryError):
    """The session or temporary storage quota has been exceeded."""


def atomic_write_json(file_path: Path, data: Any) -> None:
    """Write data to a file atomically via a temporary file and replace."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_name(f"{file_path.name}.tmp.{uuid4().hex}")
    with temp_path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, default=str)
        file_handle.flush()
        try:
            os.fsync(file_handle.fileno())
        except OSError:
            pass
    for attempt in range(5):
        try:
            temp_path.replace(file_path)
            break
        except (PermissionError, OSError) as exc:
            if attempt == 4:
                try:
                    file_path.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")
                    temp_path.unlink(missing_ok=True)
                    break
                except Exception:
                    raise exc
            time.sleep(0.02 * (2 ** attempt))


class SessionRepository:
    """Filesystem-backed temporary repository with in-memory indexes.
    
    Persists all datasets, control points, user points, georeferencing metadata,
    and map configuration for the entire lifetime of a workspace session.
    """

    _engine_to_session_id: dict[int, str] = {}

    def __init__(
        self,
        session_id: str | Any = None,
        session_dir: Path | None = None,
        created_at: datetime | None = None,
        last_accessed_at: datetime | None = None,
        status: str = "active",
        **kwargs: Any,
    ) -> None:
        legacy_obj = session_id if (session_id is not None and not isinstance(session_id, str)) else None
        should_load_from_disk = False
        if not session_id or not isinstance(session_id, str):
            if session_id is not None:
                key = id(getattr(session_id, "bind", None) or getattr(session_id, "engine", None) or session_id)
                if key not in SessionRepository._engine_to_session_id:
                    SessionRepository._engine_to_session_id[key] = f"session_{uuid4().hex}"
                session_id = SessionRepository._engine_to_session_id[key]
                should_load_from_disk = True
            else:
                session_id = f"session_{uuid4().hex}"
        self.session_id = session_id
        self._legacy_engine = legacy_obj
        if session_dir is None:
            session_dir = settings.session_storage_dir / self.session_id
        self.session_dir = Path(session_dir).resolve()
        now = datetime.now(timezone.utc)
        self.created_at = created_at or now
        self.last_accessed_at = last_accessed_at or now
        self.status = status
        self.active_operations = 0
        self._lock = threading.RLock()

        # Directories
        self.datasets_dir = self.session_dir / "datasets"
        self.edits_dir = self.session_dir / "edits"
        self.cache_dir = self.session_dir / "cache"
        self.exports_dir = self.session_dir / "exports"

        # In-memory indexes
        self.datasets: dict[UUID, Dataset] = {}
        self._dataset_by_hash: dict[str, UUID] = {}
        self.control_points: dict[UUID, list[ControlPoint]] = {}  # dataset_id -> points
        self._control_point_by_id: dict[UUID, ControlPoint] = {}
        self.icon_points: dict[UUID, list[IconPoint]] = {}  # dataset_id -> points
        self._icon_point_by_id: dict[UUID, IconPoint] = {}
        self.georeference_configs: dict[UUID, GeoreferenceConfig] = {}  # dataset_id -> config
        self.map_projects: dict[UUID, MapProject] = {}
        self.workspace_members: dict[UUID, WorkspaceMember] = {}
        self.map_configuration: dict[str, Any] = {
            "name": "Untitled Project",
            "activeView": "map",
            "center": [0.0, 0.0],
            "zoom": 2.0,
            "bearing": 0.0,
            "pitch": 0.0,
            "basemap": "streets",
            "layers": [],
        }

        # Initialize folders and files on disk
        self._init_layout()
        if should_load_from_disk:
            self.load_from_disk()

    def _init_layout(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.edits_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        # Write initial manifest and map config if they don't exist
        manifest_path = self.session_dir / "manifest.json"
        if not manifest_path.exists():
            self._save_manifest_atomic()

        map_config_path = self.session_dir / "map_config.json"
        if not map_config_path.exists():
            self._save_map_config_atomic()

    def touch(self) -> None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            self._save_manifest_atomic()

    @contextmanager
    def protect_operation(self, name: str = "operation"):
        """Protects active processing or export operations from concurrent cleanup."""
        with self._lock:
            if self.status in {"closing", "ended"}:
                raise SessionClosingError("The session is closing and cannot accept new operations.")
            self.active_operations += 1
            self.touch()
        try:
            yield
        finally:
            with self._lock:
                self.active_operations = max(0, self.active_operations - 1)
                self.touch()

    def get_session_size(self) -> int:
        total = 0
        try:
            for root, _, files in os.walk(self.session_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def check_quota(self, additional_bytes: int = 0) -> None:
        current = self.get_session_size()
        limit = settings.max_storage_per_session_bytes
        if current + additional_bytes > limit:
            raise ApplicationError(
                status_code=413,
                code="QUOTA_EXCEEDED",
                message="Session storage quota exceeded.",
                details=f"Current storage is {current / (1024 * 1024):.2f}MB, limit is {limit / (1024 * 1024):.2f}MB.",
                field="file",
            )

    # -------------------------------------------------------------------------
    # Dataset Directories
    # -------------------------------------------------------------------------

    def get_dataset_dir(self, dataset_id: UUID) -> Path:
        return self.datasets_dir / str(dataset_id)

    def get_source_dir(self, dataset_id: UUID) -> Path:
        return self.get_dataset_dir(dataset_id) / "source"

    def get_processed_dir(self, dataset_id: UUID) -> Path:
        return self.get_dataset_dir(dataset_id) / "processed"

    def get_tiles_dir(self, dataset_id: UUID) -> Path:
        return self.get_dataset_dir(dataset_id) / "tiles"

    def get_extracted_dir(self, dataset_id: UUID) -> Path:
        return self.get_dataset_dir(dataset_id) / "extracted"

    def create_dataset_directories(self, dataset_id: UUID) -> None:
        self.get_source_dir(dataset_id).mkdir(parents=True, exist_ok=True)
        self.get_processed_dir(dataset_id).mkdir(parents=True, exist_ok=True)
        self.get_tiles_dir(dataset_id).mkdir(parents=True, exist_ok=True)
        self.get_extracted_dir(dataset_id).mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Disk Persistence (Atomic Writes)
    # -------------------------------------------------------------------------

    def _save_manifest_atomic(self) -> None:
        data = {
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_accessed_at": self.last_accessed_at.isoformat(),
            "active_operations": self.active_operations,
            "datasets": {
                str(did): {
                    "id": str(ds.id),
                    "filename": ds.filename,
                    "file_size": ds.file_size,
                    "content_type": ds.content_type,
                    "file_hash": ds.file_hash,
                    "storage_path": ds.storage_path,
                    "extracted_metadata": ds.extracted_metadata,
                    "georeferenced_path": ds.georeferenced_path,
                    "georeference_status": ds.georeference_status,
                    "processed_path": ds.processed_path,
                    "process_status": ds.process_status,
                    "tile_path": ds.tile_path,
                    "tile_min_zoom": ds.tile_min_zoom,
                    "tile_max_zoom": ds.tile_max_zoom,
                    "tile_status": ds.tile_status,
                    "created_at": ds.created_at.isoformat() if ds.created_at else None,
                }
                for did, ds in self.datasets.items()
            },
            "map_projects": {
                str(pid): {
                    "id": str(p.id),
                    "name": p.name,
                    "dataset_id": str(p.dataset_id) if p.dataset_id else None,
                    "configuration": p.configuration,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for pid, p in self.map_projects.items()
            },
            "workspace_members": {
                str(mid): {
                    "id": str(m.id),
                    "map_project_id": str(m.map_project_id),
                    "dataset_id": str(m.dataset_id),
                    "alias": m.alias,
                    "sort_order": m.sort_order,
                    "visible": m.visible,
                    "raster_visible": m.raster_visible,
                    "control_points_visible": m.control_points_visible,
                    "icon_points_visible": m.icon_points_visible,
                    "raster_opacity": m.raster_opacity,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                }
                for mid, m in self.workspace_members.items()
            },
            "georeference_configs": {
                str(did): {
                    "id": str(cfg.id),
                    "dataset_id": str(cfg.dataset_id),
                    "transformation": cfg.transformation,
                    "source_file_hash": cfg.source_file_hash,
                    "source_crs": cfg.source_crs,
                    "target_crs": cfg.target_crs,
                    "source_width": cfg.source_width,
                    "source_height": cfg.source_height,
                    "control_point_count": cfg.control_point_count,
                    "source_coordinate_system": cfg.source_coordinate_system,
                    "transformation_parameters": cfg.transformation_parameters,
                    "output_path": cfg.output_path,
                    "output_format": cfg.output_format,
                    "status": cfg.status,
                    "is_active": cfg.is_active,
                    "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
                    "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
                }
                for did, cfg in self.georeference_configs.items()
            },
        }
        atomic_write_json(self.session_dir / "manifest.json", data)

    def _save_map_config_atomic(self) -> None:
        atomic_write_json(self.session_dir / "map_config.json", self.map_configuration)

    def _save_control_points_atomic(self) -> None:
        data = {
            str(did): [
                {
                    "id": str(pt.id),
                    "dataset_id": str(pt.dataset_id),
                    "image_x": pt.image_x,
                    "image_y": pt.image_y,
                    "longitude": pt.longitude,
                    "latitude": pt.latitude,
                    "created_at": pt.created_at.isoformat() if pt.created_at else None,
                    "updated_at": pt.updated_at.isoformat() if pt.updated_at else None,
                }
                for pt in points
            ]
            for did, points in self.control_points.items()
        }
        atomic_write_json(self.edits_dir / "control_points.json", data)

    def _save_user_points_atomic(self) -> None:
        data = {
            str(did): [
                {
                    "id": str(pt.id),
                    "dataset_id": str(pt.dataset_id),
                    "icon_key": pt.icon_key,
                    "latitude": pt.latitude,
                    "longitude": pt.longitude,
                    "description": pt.description,
                    "created_at": pt.created_at.isoformat() if pt.created_at else None,
                    "updated_at": pt.updated_at.isoformat() if pt.updated_at else None,
                }
                for pt in points
            ]
            for did, points in self.icon_points.items()
        }
        atomic_write_json(self.edits_dir / "user_points.json", data)

    def _save_dataset_metadata_atomic(self, dataset: Dataset) -> None:
        metadata_file = self.get_dataset_dir(dataset.id) / "metadata.json"
        data = {
            "id": str(dataset.id),
            "filename": dataset.filename,
            "file_size": dataset.file_size,
            "content_type": dataset.content_type,
            "file_hash": dataset.file_hash,
            "storage_path": dataset.storage_path,
            "extracted_metadata": dataset.extracted_metadata,
            "georeferenced_path": dataset.georeferenced_path,
            "georeference_status": dataset.georeference_status,
            "processed_path": dataset.processed_path,
            "process_status": dataset.process_status,
            "tile_path": dataset.tile_path,
            "tile_min_zoom": dataset.tile_min_zoom,
            "tile_max_zoom": dataset.tile_max_zoom,
            "tile_status": dataset.tile_status,
            "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        }
        atomic_write_json(metadata_file, data)

    def load_from_disk(self) -> None:
        """Loads and reconstructs in-memory index from disk manifests."""
        with self._lock:
            # 1. Manifest
            manifest_file = self.session_dir / "manifest.json"
            if manifest_file.exists():
                try:
                    with manifest_file.open("r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    self.status = manifest.get("status", "active")
                    if manifest.get("created_at"):
                        self.created_at = datetime.fromisoformat(manifest["created_at"])
                    if manifest.get("last_accessed_at"):
                        self.last_accessed_at = datetime.fromisoformat(manifest["last_accessed_at"])

                    # Datasets
                    for did_str, ds_dict in manifest.get("datasets", {}).items():
                        did = UUID(did_str)
                        created_at = (
                            datetime.fromisoformat(ds_dict["created_at"])
                            if ds_dict.get("created_at")
                            else datetime.now(timezone.utc)
                        )
                        dataset = Dataset(
                            id=did,
                            filename=ds_dict["filename"],
                            file_size=ds_dict["file_size"],
                            content_type=ds_dict.get("content_type"),
                            file_hash=ds_dict["file_hash"],
                            storage_path=ds_dict["storage_path"],
                            extracted_metadata=ds_dict.get("extracted_metadata", {}),
                            georeferenced_path=ds_dict.get("georeferenced_path"),
                            georeference_status=ds_dict.get("georeference_status", "not_started"),
                            processed_path=ds_dict.get("processed_path"),
                            process_status=ds_dict.get("process_status", "not_started"),
                            tile_path=ds_dict.get("tile_path"),
                            tile_min_zoom=ds_dict.get("tile_min_zoom"),
                            tile_max_zoom=ds_dict.get("tile_max_zoom"),
                            tile_status=ds_dict.get("tile_status", "not_started"),
                            created_at=created_at,
                        )
                        self.datasets[did] = dataset
                        self._dataset_by_hash[dataset.file_hash] = did

                    # Projects
                    for pid_str, p_dict in manifest.get("map_projects", {}).items():
                        pid = UUID(pid_str)
                        project = MapProject(
                            id=pid,
                            name=p_dict.get("name", "Untitled Project"),
                            dataset_id=UUID(p_dict["dataset_id"]) if p_dict.get("dataset_id") else None,
                            configuration=p_dict.get("configuration", {}),
                            created_at=datetime.fromisoformat(p_dict["created_at"]) if p_dict.get("created_at") else datetime.now(timezone.utc),
                            updated_at=datetime.fromisoformat(p_dict["updated_at"]) if p_dict.get("updated_at") else datetime.now(timezone.utc),
                        )
                        self.map_projects[pid] = project

                    # Members
                    for mid_str, m_dict in manifest.get("workspace_members", {}).items():
                        mid = UUID(mid_str)
                        member = WorkspaceMember(
                            id=mid,
                            map_project_id=UUID(m_dict["map_project_id"]),
                            dataset_id=UUID(m_dict["dataset_id"]),
                            alias=m_dict.get("alias"),
                            sort_order=m_dict.get("sort_order", 0),
                            visible=m_dict.get("visible", True),
                            raster_visible=m_dict.get("raster_visible", True),
                            control_points_visible=m_dict.get("control_points_visible", True),
                            icon_points_visible=m_dict.get("icon_points_visible", True),
                            raster_opacity=m_dict.get("raster_opacity", 0.65),
                            created_at=datetime.fromisoformat(m_dict["created_at"]) if m_dict.get("created_at") else datetime.now(timezone.utc),
                            updated_at=datetime.fromisoformat(m_dict["updated_at"]) if m_dict.get("updated_at") else datetime.now(timezone.utc),
                        )
                        self.workspace_members[mid] = member

                    # Georef configs
                    for did_str, cfg_dict in manifest.get("georeference_configs", {}).items():
                        did = UUID(did_str)
                        cfg = GeoreferenceConfig(
                            id=UUID(cfg_dict["id"]),
                            dataset_id=did,
                            transformation=cfg_dict["transformation"],
                            source_file_hash=cfg_dict["source_file_hash"],
                            source_crs=cfg_dict.get("source_crs"),
                            target_crs=cfg_dict["target_crs"],
                            source_width=cfg_dict["source_width"],
                            source_height=cfg_dict["source_height"],
                            control_point_count=cfg_dict["control_point_count"],
                            source_coordinate_system=cfg_dict.get("source_coordinate_system", {}),
                            transformation_parameters=cfg_dict.get("transformation_parameters", {}),
                            output_path=cfg_dict["output_path"],
                            output_format=cfg_dict["output_format"],
                            status=cfg_dict.get("status", "pending"),
                            is_active=cfg_dict.get("is_active", True),
                            created_at=datetime.fromisoformat(cfg_dict["created_at"]) if cfg_dict.get("created_at") else datetime.now(timezone.utc),
                            updated_at=datetime.fromisoformat(cfg_dict["updated_at"]) if cfg_dict.get("updated_at") else datetime.now(timezone.utc),
                        )
                        self.georeference_configs[did] = cfg
                except Exception as exc:
                    logger.exception("Failed to parse manifest %s", manifest_file, exc_info=exc)

            # 2. Map config
            map_config_file = self.session_dir / "map_config.json"
            if map_config_file.exists():
                try:
                    with map_config_file.open("r", encoding="utf-8") as f:
                        self.map_configuration = json.load(f)
                except Exception:
                    pass

            # 3. Control points
            cp_file = self.edits_dir / "control_points.json"
            if cp_file.exists():
                try:
                    with cp_file.open("r", encoding="utf-8") as f:
                        cp_data = json.load(f)
                    for did_str, pts in cp_data.items():
                        did = UUID(did_str)
                        self.control_points[did] = []
                        for pt in pts:
                            cp = ControlPoint(
                                id=UUID(pt["id"]),
                                dataset_id=did,
                                image_x=float(pt["image_x"]),
                                image_y=float(pt["image_y"]),
                                longitude=float(pt["longitude"]),
                                latitude=float(pt["latitude"]),
                                created_at=datetime.fromisoformat(pt["created_at"]) if pt.get("created_at") else datetime.now(timezone.utc),
                                updated_at=datetime.fromisoformat(pt["updated_at"]) if pt.get("updated_at") else datetime.now(timezone.utc),
                            )
                            self.control_points[did].append(cp)
                            self._control_point_by_id[cp.id] = cp
                except Exception:
                    pass

            # 4. Icon points
            ip_file = self.edits_dir / "user_points.json"
            if ip_file.exists():
                try:
                    with ip_file.open("r", encoding="utf-8") as f:
                        ip_data = json.load(f)
                    for did_str, pts in ip_data.items():
                        did = UUID(did_str)
                        self.icon_points[did] = []
                        for pt in pts:
                            ip = IconPoint(
                                id=UUID(pt["id"]),
                                dataset_id=did,
                                icon_key=pt.get("icon_key"),
                                latitude=float(pt["latitude"]),
                                longitude=float(pt["longitude"]),
                                description=pt.get("description"),
                                created_at=datetime.fromisoformat(pt["created_at"]) if pt.get("created_at") else datetime.now(timezone.utc),
                                updated_at=datetime.fromisoformat(pt["updated_at"]) if pt.get("updated_at") else datetime.now(timezone.utc),
                            )
                            self.icon_points[did].append(ip)
                            self._icon_point_by_id[ip.id] = ip
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Dataset Operations
    # -------------------------------------------------------------------------

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            return self.datasets.get(dataset_id)

    def find_dataset_by_hash(self, file_hash: str) -> Dataset | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            did = self._dataset_by_hash.get(file_hash)
            return self.datasets.get(did) if did else None

    def list_datasets(self) -> list[Dataset]:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            # Return sorted by created_at desc
            return sorted(
                self.datasets.values(),
                key=lambda d: d.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

    def insert_dataset(self, dataset: Dataset) -> None:
        with self._lock:
            if dataset.file_hash in self._dataset_by_hash:
                existing_id = self._dataset_by_hash[dataset.file_hash]
                if existing_id != dataset.id:
                    raise DuplicateValueError("A dataset with this file hash already exists.")
            self.datasets[dataset.id] = dataset
            self._dataset_by_hash[dataset.file_hash] = dataset.id
            self.create_dataset_directories(dataset.id)
            self._save_dataset_metadata_atomic(dataset)
            self._save_manifest_atomic()

    def save_dataset(self, dataset: Dataset) -> None:
        with self._lock:
            if dataset.id not in self.datasets:
                raise RepositoryError("Dataset does not exist.")
            self.datasets[dataset.id] = dataset
            self._dataset_by_hash[dataset.file_hash] = dataset.id
            self._save_dataset_metadata_atomic(dataset)
            self._save_manifest_atomic()

    def delete_dataset(self, dataset_id: UUID) -> None:
        with self._lock:
            dataset = self.datasets.pop(dataset_id, None)
            backend_dir = Path(__file__).resolve().parents[1]
            if dataset:
                self._dataset_by_hash.pop(dataset.file_hash, None)
                # Remove actual files and tiles tracked on dataset
                for path_attr in (
                    dataset.storage_path,
                    dataset.processed_path,
                    dataset.georeferenced_path,
                    dataset.tile_path,
                ):
                    if path_attr:
                        p = Path(path_attr)
                        target = p.resolve() if p.is_absolute() else (backend_dir / p).resolve()
                        if target.exists():
                            try:
                                if target.is_dir():
                                    shutil.rmtree(target, ignore_errors=True)
                                else:
                                    target.unlink(missing_ok=True)
                            except Exception:
                                pass

            # Clean any legacy storage directories matching dataset_id
            for legacy_folder in ("uploads", "processed", "tiles"):
                legacy_dir = backend_dir / "storage" / legacy_folder / str(dataset_id)
                if legacy_dir.exists():
                    try:
                        shutil.rmtree(legacy_dir, ignore_errors=True)
                    except Exception:
                        pass

            # Clean up control points
            pts = self.control_points.pop(dataset_id, [])
            for pt in pts:
                self._control_point_by_id.pop(pt.id, None)

            # Clean up icon points
            ips = self.icon_points.pop(dataset_id, [])
            for ip in ips:
                self._icon_point_by_id.pop(ip.id, None)

            # Clean up georeference config
            self.georeference_configs.pop(dataset_id, None)

            # Clean up workspace members
            members_to_delete = [
                mid for mid, m in self.workspace_members.items() if m.dataset_id == dataset_id
            ]
            for mid in members_to_delete:
                self.workspace_members.pop(mid, None)

            # Clean up map projects
            projects_to_delete = [
                pid for pid, p in self.map_projects.items() if p.dataset_id == dataset_id
            ]
            for pid in projects_to_delete:
                self.map_projects.pop(pid, None)

            # Remove dataset directory on disk
            ds_dir = self.get_dataset_dir(dataset_id)
            if ds_dir.exists():
                try:
                    shutil.rmtree(ds_dir, ignore_errors=True)
                except OSError:
                    logger.exception("Failed to remove dataset directory %s", ds_dir)

            self._save_control_points_atomic()
            self._save_user_points_atomic()
            self._save_manifest_atomic()

    # -------------------------------------------------------------------------
    # Control Points Operations
    # -------------------------------------------------------------------------

    def get_control_point(self, control_point_id: UUID) -> ControlPoint | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            return self._control_point_by_id.get(control_point_id)

    def list_control_points(self, dataset_id: UUID) -> list[ControlPoint]:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            points = self.control_points.get(dataset_id, [])
            return sorted(points, key=lambda p: (p.created_at, str(p.id)))

    def insert_control_point(self, point: ControlPoint) -> None:
        with self._lock:
            if point.dataset_id not in self.control_points:
                self.control_points[point.dataset_id] = []
            self.control_points[point.dataset_id].append(point)
            self._control_point_by_id[point.id] = point
            self._save_control_points_atomic()

    def save_control_point(self, point: ControlPoint) -> None:
        with self._lock:
            existing = self._control_point_by_id.get(point.id)
            if not existing:
                raise RepositoryError("Control point does not exist.")
            existing.image_x = point.image_x
            existing.image_y = point.image_y
            existing.longitude = point.longitude
            existing.latitude = point.latitude
            existing.updated_at = datetime.now(timezone.utc)
            point.updated_at = existing.updated_at
            self._save_control_points_atomic()

    def update_control_point(self, point: ControlPoint) -> None:
        self.save_control_point(point)

    def delete_control_point(self, control_point_id: UUID) -> None:
        with self._lock:
            point = self._control_point_by_id.pop(control_point_id, None)
            if point:
                pts = self.control_points.get(point.dataset_id, [])
                self.control_points[point.dataset_id] = [p for p in pts if p.id != control_point_id]
                self._save_control_points_atomic()

    def save_control_points(self, dataset_id: UUID, points: list[ControlPoint]) -> None:
        with self._lock:
            # Replace all control points for this dataset
            old_pts = self.control_points.get(dataset_id, [])
            for pt in old_pts:
                self._control_point_by_id.pop(pt.id, None)
            self.control_points[dataset_id] = list(points)
            for pt in points:
                self._control_point_by_id[pt.id] = pt
            self._save_control_points_atomic()

    # -------------------------------------------------------------------------
    # Icon Points Operations
    # -------------------------------------------------------------------------

    def get_icon_point(self, icon_point_id: UUID) -> IconPoint | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            return self._icon_point_by_id.get(icon_point_id)

    def list_icon_points(self, dataset_id: UUID) -> list[IconPoint]:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            points = self.icon_points.get(dataset_id, [])
            return sorted(points, key=lambda p: (p.created_at, str(p.id)))

    def insert_icon_point(self, point: IconPoint) -> None:
        with self._lock:
            if point.dataset_id not in self.icon_points:
                self.icon_points[point.dataset_id] = []
            self.icon_points[point.dataset_id].append(point)
            self._icon_point_by_id[point.id] = point
            self._save_user_points_atomic()

    def save_icon_point(self, point: IconPoint) -> None:
        with self._lock:
            existing = self._icon_point_by_id.get(point.id)
            if not existing:
                raise RepositoryError("Icon point does not exist.")
            existing.icon_key = point.icon_key
            existing.latitude = point.latitude
            existing.longitude = point.longitude
            existing.description = point.description
            existing.updated_at = datetime.now(timezone.utc)
            point.updated_at = existing.updated_at
            self._save_user_points_atomic()

    def delete_icon_point(self, icon_point_id: UUID) -> None:
        with self._lock:
            point = self._icon_point_by_id.pop(icon_point_id, None)
            if point:
                pts = self.icon_points.get(point.dataset_id, [])
                self.icon_points[point.dataset_id] = [p for p in pts if p.id != icon_point_id]
                self._save_user_points_atomic()

    def save_user_points(self, dataset_id: UUID, points: list[IconPoint]) -> None:
        with self._lock:
            old_pts = self.icon_points.get(dataset_id, [])
            for pt in old_pts:
                self._icon_point_by_id.pop(pt.id, None)
            self.icon_points[dataset_id] = list(points)
            for pt in points:
                self._icon_point_by_id[pt.id] = pt
            self._save_user_points_atomic()

    # -------------------------------------------------------------------------
    # Georeference Config Operations
    # -------------------------------------------------------------------------

    def get_active_georeference_config(self, dataset_id: UUID) -> GeoreferenceConfig | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            cfg = self.georeference_configs.get(dataset_id)
            return cfg if (cfg and cfg.is_active) else None

    def save_georeference_config(self, config: GeoreferenceConfig) -> None:
        with self._lock:
            self.georeference_configs[config.dataset_id] = config
            self._save_manifest_atomic()

    def mark_georeference_config_pending(self, dataset_id: UUID) -> None:
        with self._lock:
            cfg = self.get_active_georeference_config(dataset_id)
            if cfg is not None:
                cfg.status = "pending"
                cfg.updated_at = datetime.now(timezone.utc)
                self._save_manifest_atomic()

    # -------------------------------------------------------------------------
    # Map Project Operations
    # -------------------------------------------------------------------------

    def get_map_project(self, project_id: UUID) -> MapProject | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            return self.map_projects.get(project_id)

    def get_map_project_by_dataset_id(self, dataset_id: UUID) -> MapProject | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            matches = [p for p in self.map_projects.values() if p.dataset_id == dataset_id]
            if not matches:
                return None
            return sorted(matches, key=lambda p: p.created_at, reverse=True)[0]

    def insert_map_project(self, project: MapProject) -> None:
        with self._lock:
            self.map_projects[project.id] = project
            # Also keep map_configuration synced
            if project.configuration:
                self.map_configuration.update(project.configuration)
                self._save_map_config_atomic()
            self._save_manifest_atomic()

    def save_map_project(self, project: MapProject) -> None:
        with self._lock:
            if project.id not in self.map_projects:
                raise RepositoryError("Map project does not exist.")
            project.updated_at = datetime.now(timezone.utc)
            self.map_projects[project.id] = project
            if project.configuration:
                self.map_configuration.update(project.configuration)
                self._save_map_config_atomic()
            self._save_manifest_atomic()

    # -------------------------------------------------------------------------
    # Workspace Member Operations
    # -------------------------------------------------------------------------

    def get_workspace_member(self, map_project_id: UUID, dataset_id: UUID) -> WorkspaceMember | None:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            for m in self.workspace_members.values():
                if m.map_project_id == map_project_id and m.dataset_id == dataset_id:
                    return m
            return None

    def list_workspace_members(self, map_project_id: UUID) -> list[WorkspaceMember]:
        with self._lock:
            self.last_accessed_at = datetime.now(timezone.utc)
            members = [m for m in self.workspace_members.values() if m.map_project_id == map_project_id]
            return sorted(members, key=lambda m: (m.sort_order, m.created_at, str(m.id)))

    def insert_workspace_member(self, member: WorkspaceMember) -> None:
        with self._lock:
            existing = self.get_workspace_member(member.map_project_id, member.dataset_id)
            if existing and existing.id != member.id:
                raise DuplicateValueError("Workspace member for project and dataset already exists.")
            self.workspace_members[member.id] = member
            self._save_manifest_atomic()

    def save_workspace_member(self, member: WorkspaceMember) -> None:
        with self._lock:
            if member.id not in self.workspace_members:
                raise RepositoryError("Workspace member does not exist.")
            member.updated_at = datetime.now(timezone.utc)
            self.workspace_members[member.id] = member
            self._save_manifest_atomic()

    def delete_workspace_member(self, member_id: UUID) -> None:
        with self._lock:
            self.workspace_members.pop(member_id, None)
            self._save_manifest_atomic()

    # -------------------------------------------------------------------------
    # Map Configuration & Edits Persistence
    # -------------------------------------------------------------------------

    def save_map_configuration(self, configuration: dict[str, Any]) -> None:
        with self._lock:
            self.map_configuration.update(configuration)
            self._save_map_config_atomic()
            self.touch()

    def get_map_configuration(self) -> dict[str, Any]:
        with self._lock:
            self.touch()
            return dict(self.map_configuration)

    def save_edits(self, edits: dict[str, Any]) -> None:
        with self._lock:
            feature_edits_file = self.edits_dir / "feature_edits.json"
            atomic_write_json(feature_edits_file, edits)
            self.touch()

    def get_export_data(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "map_config": self.map_configuration,
                "datasets": [asdict(d) for d in self.datasets.values()],
                "control_points": {str(k): [asdict(p) for p in v] for k, v in self.control_points.items()},
                "icon_points": {str(k): [asdict(p) for p in v] for k, v in self.icon_points.items()},
            }

    # -------------------------------------------------------------------------
    # Lightweight transaction-style interface used by feature functions
    # -------------------------------------------------------------------------

    def ping(self) -> None:
        if self.status in {"closing", "ended"}:
            raise RepositoryError("Session is closed.")

    def commit(self) -> None:
        # Atomic file syncs are performed on writes
        pass

    def rollback(self) -> None:
        # Re-read manifest from disk if needed
        pass

    def close(self) -> None:
        pass
