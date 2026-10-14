from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
import time
from typing import Annotated

from fastapi import Header, Query, Request

from config import settings
from schemas.error import ApplicationError
from storage.repository import DuplicateValueError, RepositoryError, SessionRepository

logger = logging.getLogger(__name__)

SESSION_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def remove_directory(path: Path, attempts: int = 5) -> bool:
    """Remove a temporary directory reliably on Windows and OneDrive filesystems."""
    if not path.exists():
        return True
    for attempt in range(attempts):
        try:
            for item in path.rglob("*"):
                try:
                    item.chmod(stat.S_IWRITE)
                except OSError:
                    pass
            path.chmod(stat.S_IWRITE)
            shutil.rmtree(path)
            return True
        except OSError:
            if attempt == attempts - 1:
                return False
            time.sleep(0.05 * (2**attempt))
    return False


def validate_session_id(session_id: str | None) -> str:
    """Validate a session ID before using it as part of a filesystem path."""
    if not session_id or not isinstance(session_id, str):
        raise ApplicationError(
            status_code=400,
            code="INVALID_SESSION_ID",
            message="A valid session identifier is required.",
            details="Session ID must be between 16 and 64 alphanumeric characters.",
            field="session_id",
        )
    clean_id = session_id.strip()
    if not SESSION_ID_REGEX.match(clean_id):
        raise ApplicationError(
            status_code=400,
            code="INVALID_SESSION_ID",
            message="Invalid session identifier format.",
            details="Session ID must contain only alphanumeric characters, underscores, or hyphens.",
            field="session_id",
        )
    return clean_id


class SessionStorage:
    """Manage session-lifetime repositories and their temporary directories."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = Path(root_dir or settings.session_storage_dir).resolve()
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionRepository] = {}
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self) -> str:
        return secrets.token_urlsafe(32)

    def create_session(self, session_id: str | None = None) -> SessionRepository:
        with self._lock:
            sid = validate_session_id(session_id) if session_id else self.generate_session_id()
            session_dir = self.root_dir / sid
            if session_dir.exists() and sid in self._sessions:
                return self._sessions[sid]

            session_dir.mkdir(parents=True, exist_ok=True)
            repo = SessionRepository(session_id=sid, session_dir=session_dir)
            self._sessions[sid] = repo
            logger.info("Created session workspace: %s", sid)
            return repo

    def get_session(
        self, session_id: str, touch: bool = True, allow_expired: bool = False
    ) -> SessionRepository | None:
        sid = validate_session_id(session_id)
        with self._lock:
            repo = self._sessions.get(sid)
            if repo is None:
                session_dir = self.root_dir / sid
                if not session_dir.is_dir() or not (session_dir / "manifest.json").exists():
                    return None
                repo = SessionRepository(session_id=sid, session_dir=session_dir)
                repo.load_from_disk()
                if self._is_expired(repo) and not allow_expired:
                    return None
                self._sessions[sid] = repo

            if self._is_expired(repo) and not allow_expired:
                self.end_session(sid, force=True)
                return None
            if repo.status in {"closing", "ended"} and not allow_expired:
                return None
            if touch:
                repo.touch()
            return repo

    def restore_session(self, session_id: str) -> SessionRepository | None:
        return self.get_session(session_id, touch=True)

    @staticmethod
    def _is_expired(repo: SessionRepository) -> bool:
        now = datetime.now(timezone.utc)
        inactivity = (now - repo.last_accessed_at).total_seconds()
        lifetime = (now - repo.created_at).total_seconds()
        return (
            inactivity > settings.session_inactivity_timeout_seconds
            or lifetime > settings.session_max_lifetime_seconds
        )

    def _cleanup_repo_files(self, repo: SessionRepository) -> None:
        """Remove all files and directories associated with datasets in this repository."""
        backend_dir = Path(__file__).resolve().parents[1]
        for dataset_id, dataset in list(repo.datasets.items()):
            # 1. Dataset directory inside session
            try:
                ds_dir = repo.get_dataset_dir(dataset_id)
                if ds_dir.exists():
                    remove_directory(ds_dir)
            except Exception:
                pass

            # 2. Paths recorded on dataset
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
                                remove_directory(target)
                            else:
                                target.unlink(missing_ok=True)
                        except Exception:
                            pass

            # 3. Any legacy storage directories matching dataset_id
            for legacy_folder in ("uploads", "processed", "tiles"):
                legacy_dir = backend_dir / "storage" / legacy_folder / str(dataset_id)
                if legacy_dir.exists():
                    try:
                        remove_directory(legacy_dir)
                    except Exception:
                        pass

    def end_session(self, session_id: str, force: bool = False) -> bool:
        sid = validate_session_id(session_id)
        with self._lock:
            repo = self._sessions.get(sid)
            session_dir = self.root_dir / sid
            if repo:
                with repo._lock:
                    if repo.active_operations > 0 and not force:
                        logger.warning("Session %s has active operations; cannot end now.", sid)
                        return False
                    repo.status = "closing"
                    self._cleanup_repo_files(repo)
                self._sessions.pop(sid, None)

            if session_dir.exists():
                if not remove_directory(session_dir):
                    logger.error("Failed to delete session directory %s", sid)
                    return False
            return True

    def purge_all_sessions(self) -> int:
        """Purge all sessions and all temporary images and files from disk."""
        cleaned_count = 0
        with self._lock:
            for sid in list(self._sessions.keys()):
                self.end_session(sid, force=True)
                cleaned_count += 1
            if self.root_dir.exists():
                for item in self.root_dir.iterdir():
                    if item.is_dir():
                        remove_directory(item)
                        cleaned_count += 1
            # Clean legacy uploads, processed, and tiles directories
            backend_dir = Path(__file__).resolve().parents[1]
            for legacy_name in ("uploads", "processed", "tiles"):
                legacy_dir = backend_dir / "storage" / legacy_name
                if legacy_dir.exists():
                    for item in legacy_dir.iterdir():
                        if item.is_dir() and not item.name.startswith("."):
                            remove_directory(item)
        return cleaned_count

    def restore_all_on_startup(self) -> int:
        if not settings.restore_sessions_on_startup:
            return 0

        restored_count = 0
        with self._lock:
            if not self.root_dir.exists():
                return 0
            for entry in self.root_dir.iterdir():
                if not entry.is_dir() or not (entry / "manifest.json").exists():
                    continue
                try:
                    sid = validate_session_id(entry.name)
                except ApplicationError:
                    continue
                repo = SessionRepository(session_id=sid, session_dir=entry)
                repo.load_from_disk()
                if self._is_expired(repo) or repo.status in {"closing", "ended"}:
                    if not remove_directory(entry):
                        logger.warning("Could not purge expired session %s", sid)
                else:
                    self._sessions[sid] = repo
                    restored_count += 1
        return restored_count

    def list_active_sessions(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())


session_storage = SessionStorage()


def cleanup_orphaned_storage() -> None:
    """Remove orphaned images in backend/storage that do not belong to active sessions."""
    backend_dir = Path(__file__).resolve().parents[1]
    active_dataset_ids: set[str] = set()
    with session_storage._lock:
        for repo in session_storage._sessions.values():
            with repo._lock:
                for did in repo.datasets.keys():
                    active_dataset_ids.add(str(did))

    for legacy_name in ("uploads", "processed", "tiles"):
        legacy_dir = backend_dir / "storage" / legacy_name
        if legacy_dir.exists():
            for item in legacy_dir.iterdir():
                if item.is_dir() and item.name not in active_dataset_ids and not item.name.startswith("."):
                    remove_directory(item)


def initialize_sessions() -> None:
    """Initialize session storage, purging old data if persistence is disabled."""
    if not settings.restore_sessions_on_startup:
        session_storage.purge_all_sessions()
    else:
        session_storage.restore_all_on_startup()
    cleanup_orphaned_storage()


def get_session_repository(
    request: Request = None,  # type: ignore[assignment]
    x_session_id: Annotated[str | None, Header(alias="X-Session-ID")] = None,
    session_id: Annotated[str | None, Query(alias="session_id")] = None,
) -> SessionRepository:
    """Resolve or create the repository associated with an API request."""
    resolved_id = x_session_id or session_id
    if resolved_id:
        repo = session_storage.get_session(validate_session_id(resolved_id))
        if repo is None:
            raise ApplicationError(
                status_code=404,
                code="SESSION_NOT_FOUND",
                message="The requested workspace session was not found or has expired.",
                details="Start a new session or refresh the workspace.",
                field="session_id",
            )
    else:
        repo = None
        active_sessions = session_storage.list_active_sessions()
        if active_sessions:
            repo = session_storage.get_session(active_sessions[-1])
        if repo is None:
            repo = session_storage.create_session()

    if request is not None:
        request.state.session_id = repo.session_id
    return repo


def cleanup_expired_sessions(
    storage: SessionStorage | None = None, force: bool = False
) -> list[str]:
    """Remove expired sessions after active operations have finished."""
    manager = storage or session_storage
    cleaned: list[str] = []
    all_ids = set(manager.list_active_sessions())
    if manager.root_dir.exists():
        all_ids.update(item.name for item in manager.root_dir.iterdir() if item.is_dir())

    for session_id in all_ids:
        try:
            repo = manager.get_session(session_id, touch=False, allow_expired=True)
        except ApplicationError:
            session_dir = manager.root_dir / session_id
            if session_dir.exists() and session_dir.is_dir():
                if remove_directory(session_dir):
                    cleaned.append(session_id)
                else:
                    logger.warning("Could not remove orphan session %s", session_id)
            continue

        if repo is None:
            session_dir = manager.root_dir / session_id
            if session_dir.exists():
                if remove_directory(session_dir):
                    cleaned.append(session_id)
                else:
                    logger.warning("Could not remove orphan session %s", session_id)
            continue

        with repo._lock:
            now = datetime.now(timezone.utc)
            expired = (
                (now - repo.last_accessed_at).total_seconds()
                > settings.session_inactivity_timeout_seconds
                or (now - repo.created_at).total_seconds()
                > settings.session_max_lifetime_seconds
                or repo.status in {"closing", "ended"}
            )
            if not expired and not force:
                continue
            if repo.active_operations > 0 and not force:
                continue
            repo.status = "closing"

        if manager.end_session(session_id, force=True):
            cleaned.append(session_id)
    cleanup_orphaned_storage()
    return cleaned


def cleanup_old_exports(
    repo: SessionRepository, retention_seconds: int | None = None
) -> int:
    """Remove exports older than the configured retention period."""
    retention = retention_seconds or settings.export_retention_seconds
    removed = 0
    if not repo.exports_dir.exists():
        return removed
    now = time.time()
    with repo._lock:
        for item in repo.exports_dir.iterdir():
            if not item.is_file():
                continue
            try:
                if now - os.path.getmtime(item) > retention:
                    item.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                logger.warning("Could not remove expired export %s", item)
    return removed
