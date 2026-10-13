from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from storage.session import RepositoryError, SessionRepository, settings
from functions.map_projects.response import MapProjectResponse
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError


PROJECT_DOCUMENT_VERSION = 1
MAX_FOLDER_FILES = 100_000
COPY_CHUNK_SIZE = 1024 * 1024
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"
SOURCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
REQUIRED_VIEWERS = {"index.html", "leaflet.html", "openlayers.html", "googlemaps.html"}
TILE_PATH = re.compile(r"^(\d+)/(\d+)/(\d+)\.png$")


def _error(code: str, message: str, details: str) -> ApplicationError:
    return ApplicationError(
        status_code=400,
        code=code,
        message=message,
        details=details,
        field="folder",
    )


def _response(project: MapProject) -> MapProjectResponse:
    return MapProjectResponse(
        id=project.id,
        name=project.name,
        dataset_id=project.dataset_id,
        configuration=project.configuration,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _safe_path(value: str) -> str:
    if not value or "\\" in value or value.startswith(("/", "\\")):
        raise _error(
            "UNSAFE_FOLDER_PATH",
            "The selected folder contains an unsafe path.",
            "Folder files must use relative paths without backslashes.",
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _error(
            "UNSAFE_FOLDER_PATH",
            "The selected folder contains an unsafe path.",
            "Folder paths cannot be absolute or traverse directories.",
        )
    if path.parts and ":" in path.parts[0]:
        raise _error(
            "UNSAFE_FOLDER_PATH",
            "The selected folder contains an unsafe path.",
            "Windows drive paths are not allowed.",
        )
    return path.as_posix()


def _normalized_paths(paths: list[str]) -> list[str]:
    safe = [_safe_path(value) for value in paths]
    parts = [PurePosixPath(value).parts for value in safe]
    if parts and all(len(item) > 1 for item in parts):
        root = parts[0][0]
        if all(item[0].casefold() == root.casefold() for item in parts):
            safe = [PurePosixPath(*item[1:]).as_posix() for item in parts]
    folded: set[str] = set()
    for path in safe:
        key = path.casefold()
        if key in folded:
            raise _error(
                "DUPLICATE_FOLDER_PATH",
                "The selected folder contains duplicate paths.",
                "Every folder file path must be unique, including letter case.",
            )
        folded.add(key)
    return safe


async def _stage_files(
    files: list[UploadFile],
    paths: list[str],
    root: Path,
) -> tuple[dict[str, Path], str, int]:
    maximum_size = settings.max_upload_size_mb * 1024 * 1024
    total_size = 0
    staged: dict[str, Path] = {}
    fingerprints: list[tuple[str, str, int]] = []
    for upload, relative in zip(files, paths, strict=True):
        destination = (root / Path(*PurePosixPath(relative).parts)).resolve()
        try:
            destination.relative_to(root.resolve())
        except ValueError as exc:
            raise _error(
                "UNSAFE_FOLDER_PATH",
                "The selected folder contains an unsafe path.",
                "A folder file resolves outside temporary storage.",
            ) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        await upload.seek(0)
        with destination.open("xb") as output:
            while chunk := await upload.read(COPY_CHUNK_SIZE):
                size += len(chunk)
                total_size += len(chunk)
                if total_size > maximum_size:
                    raise _error(
                        "PROJECT_FOLDER_TOO_LARGE",
                        "The selected project folder is too large.",
                        f"The maximum allowed folder size is {settings.max_upload_size_mb} MB.",
                    )
                digest.update(chunk)
                output.write(chunk)
        staged[relative] = destination
        fingerprints.append((relative, digest.hexdigest(), size))
    package_digest = hashlib.sha256()
    for relative, digest, size in sorted(fingerprints):
        package_digest.update(relative.encode("utf-8"))
        package_digest.update(b"\0")
        package_digest.update(str(size).encode("ascii"))
        package_digest.update(b"\0")
        package_digest.update(digest.encode("ascii"))
    return staged, package_digest.hexdigest(), total_size


def _json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("JSON file exceeds its size limit.")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise _error(
            "INVALID_FOLDER_JSON",
            "The selected project folder contains invalid metadata.",
            f"{name} must contain one valid UTF-8 JSON object.",
        ) from exc
    if not isinstance(value, dict):
        raise _error(
            "INVALID_FOLDER_JSON",
            "The selected project folder contains invalid metadata.",
            f"{name} must contain a JSON object.",
        )
    return value


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder contains invalid data.",
            f"{field} must be a finite number.",
        ) from exc
    if not math.isfinite(number):
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder contains invalid data.",
            f"{field} must be a finite number.",
        )
    return number


def _coordinate(value: Any, field: str) -> float:
    number = _finite(value, field)
    minimum, maximum = (-90, 90) if field == "latitude" else (-180, 180)
    if number < minimum or number > maximum:
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder contains invalid coordinates.",
            f"{field} must be between {minimum} and {maximum}.",
        )
    return number


def _image_coordinate(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number < 0:
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder contains invalid image coordinates.",
            f"{field} must be zero or greater.",
        )
    return number


def _bounds(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise _error(
            "INVALID_FOLDER_METADATA",
            "The selected project folder has invalid map bounds.",
            "metadata.json bounds must contain west, south, east, and north.",
        )
    west, south, east, north = (_finite(item, "bounds") for item in value)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise _error(
            "INVALID_FOLDER_METADATA",
            "The selected project folder has invalid map bounds.",
            "The folder bounds must be a valid WGS84 extent.",
        )
    return [west, south, east, north]


def _zoom(value: Any, field: str) -> int:
    try:
        zoom = int(value)
    except (TypeError, ValueError) as exc:
        raise _error(
            "INVALID_FOLDER_METADATA",
            "The selected project folder has an invalid zoom range.",
            f"{field} must be an integer.",
        ) from exc
    if zoom < 0 or zoom > 30:
        raise _error(
            "INVALID_FOLDER_METADATA",
            "The selected project folder has an invalid zoom range.",
            f"{field} must be between 0 and 30.",
        )
    return zoom


def _validate_structure(
    staged: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, Path]], str | None]:
    required = {"mapstudio.json", "metadata.json", *REQUIRED_VIEWERS}
    missing = sorted(required.difference(staged))
    if missing:
        raise _error(
            "INCOMPLETE_PROJECT_FOLDER",
            "The selected folder is not a complete Map Studio project.",
            f"Missing required file: {missing[0]}.",
        )
    project_data = _json_object(staged["mapstudio.json"], "mapstudio.json")
    metadata = _json_object(staged["metadata.json"], "metadata.json")
    if (
        project_data.get("format") != "mapstudio-folder"
        or project_data.get("version") != PROJECT_DOCUMENT_VERSION
    ):
        raise _error(
            "UNSUPPORTED_FOLDER_VERSION",
            "The selected Map Studio folder version is not supported.",
            f"mapstudio.json must use version {PROJECT_DOCUMENT_VERSION}.",
        )
    if str(metadata.get("format", "")).lower() != "png":
        raise _error(
            "UNSUPPORTED_FOLDER_TILES",
            "The selected project folder does not contain PNG tiles.",
            "metadata.json format must be png.",
        )
    min_zoom = _zoom(metadata.get("minzoom"), "minzoom")
    max_zoom = _zoom(metadata.get("maxzoom"), "maxzoom")
    if max_zoom < min_zoom:
        raise _error(
            "INVALID_FOLDER_METADATA",
            "The selected project folder has an invalid zoom range.",
            "maxzoom must be greater than or equal to minzoom.",
        )
    metadata["bounds"] = _bounds(metadata.get("bounds"))
    metadata["minzoom"] = min_zoom
    metadata["maxzoom"] = max_zoom

    project = project_data.get("project")
    dataset = project_data.get("dataset")
    if not isinstance(project, dict) or not isinstance(project.get("configuration"), dict):
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder has invalid project settings.",
            "A project object with a configuration object is required.",
        )
    if not isinstance(dataset, dict):
        raise _error(
            "INVALID_FOLDER_PROJECT",
            "The selected project folder has invalid dataset settings.",
            "A dataset object is required.",
        )
    for key in ("control_points", "icon_points"):
        if not isinstance(project_data.get(key), list):
            raise _error(
                "INVALID_FOLDER_PROJECT",
                "The selected project folder has invalid point data.",
                f"{key} must be an array.",
            )

    source_asset = dataset.get("source_asset")
    if source_asset is not None:
        if not isinstance(source_asset, str) or _safe_path(source_asset) != source_asset:
            raise _error(
                "INVALID_FOLDER_SOURCE",
                "The selected project folder has an invalid raster source path.",
                "The source asset must use a safe relative path.",
            )
        if source_asset not in staged or not source_asset.startswith("assets/source/"):
            raise _error(
                "INVALID_FOLDER_SOURCE",
                "The selected project folder is missing its raster source.",
                "The source asset declared by mapstudio.json must exist under assets/source/.",
            )
        if PurePosixPath(source_asset).suffix.lower() not in SOURCE_EXTENSIONS:
            raise _error(
                "INVALID_FOLDER_SOURCE",
                "The selected project folder has an unsupported raster source.",
                "Only JPG, PNG, and TIFF source assets are supported.",
            )

    tiles: list[tuple[str, Path]] = []
    allowed = required | ({source_asset} if source_asset else set())
    for relative, path in staged.items():
        match = TILE_PATH.fullmatch(relative)
        if match is None:
            if relative not in allowed:
                raise _error(
                    "UNSUPPORTED_FOLDER_FILE",
                    "The selected project folder contains an unsupported file.",
                    f"Unexpected folder file: {relative}.",
                )
            continue
        zoom, column, row = (int(value) for value in match.groups())
        limit = 1 << zoom if 0 <= zoom <= 30 else 0
        if (
            zoom < min_zoom
            or zoom > max_zoom
            or not (0 <= column < limit)
            or not (0 <= row < limit)
        ):
            raise _error(
                "INVALID_FOLDER_TILE",
                "The selected project folder contains an invalid tile path.",
                f"Tile coordinates are outside the declared zoom grid: {relative}.",
            )
        tiles.append((relative, path))
    if not tiles:
        raise _error(
            "EMPTY_PROJECT_FOLDER",
            "The selected project folder contains no PNG map tiles.",
            "At least one valid z/x/y.png tile is required.",
        )
    return project_data, metadata, tiles, source_asset


async def import_project_folder(
    files: list[UploadFile],
    paths: list[str],
    db: SessionRepository,
) -> MapProjectResponse:
    if not files or len(files) != len(paths) or len(files) > MAX_FOLDER_FILES:
        raise _error(
            "INVALID_PROJECT_FOLDER",
            "The selected project folder is invalid.",
            f"Provide matching files and paths, up to {MAX_FOLDER_FILES} files.",
        )
    normalized = _normalized_paths(paths)
    temporary_directory = Path(tempfile.mkdtemp(prefix="mapstudio-folder-import-"))
    final_directories: list[Path] = []
    try:
        staged, package_hash, total_size = await _stage_files(
            files,
            normalized,
            temporary_directory,
        )
        existing_dataset = db.find_dataset_by_hash(package_hash)
        if existing_dataset is not None:
            existing_project = db.get_map_project_by_dataset_id(existing_dataset.id)
            if existing_project is not None:
                return _response(existing_project)

        project_data, metadata, tiles, source_asset = _validate_structure(staged)
        project_value = project_data["project"]
        dataset_value = project_data["dataset"]
        new_dataset_id = uuid4()
        upload_directory = UPLOAD_DIRECTORY / str(new_dataset_id)
        tile_directory = TILES_DIRECTORY / str(new_dataset_id)
        upload_directory.mkdir(parents=True, exist_ok=False)
        final_directories.append(upload_directory)
        tile_directory.mkdir(parents=True, exist_ok=False)
        final_directories.append(tile_directory)

        project_copy = upload_directory / "mapstudio.json"
        shutil.copy2(staged["mapstudio.json"], project_copy)
        stored_source = project_copy
        content_type = "application/json"
        if source_asset is not None:
            source_name = PurePosixPath(source_asset).name
            stored_source = upload_directory / source_name
            shutil.copy2(staged[source_asset], stored_source)
            content_type = dataset_value.get("content_type") or "application/octet-stream"

        for relative, source in tiles:
            destination = tile_directory / Path(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        source_filename = PurePosixPath(str(dataset_value.get("filename") or stored_source.name)).name
        if not source_filename:
            source_filename = stored_source.name
        restored_metadata = {
            "format": "mapstudio_folder",
            "category": "tiles",
            "tile_format": "png",
            "bounds": metadata["bounds"],
            "min_zoom": metadata["minzoom"],
            "max_zoom": metadata["maxzoom"],
            "profile": metadata.get("profile", "mercator"),
            "source_asset": None if source_asset is None else stored_source.relative_to(BACKEND_DIRECTORY).as_posix(),
        }
        dataset = Dataset(
            id=new_dataset_id,
            filename=source_filename,
            file_size=total_size,
            content_type=content_type,
            file_hash=package_hash,
            storage_path=stored_source.relative_to(BACKEND_DIRECTORY).as_posix(),
            extracted_metadata=restored_metadata,
            georeference_status="completed",
            process_status="completed",
            tile_path=tile_directory.relative_to(BACKEND_DIRECTORY).as_posix(),
            tile_min_zoom=metadata["minzoom"],
            tile_max_zoom=metadata["maxzoom"],
            tile_status="completed",
        )
        project = MapProject(
            name=str(project_value.get("name") or "Imported Project")[:255],
            dataset_id=new_dataset_id,
            configuration=project_value["configuration"],
        )
        db.insert_dataset(dataset)
        for value in project_data["control_points"]:
            if not isinstance(value, dict):
                raise _error(
                    "INVALID_FOLDER_PROJECT",
                    "The selected project folder contains invalid control points.",
                    "Every control point must be an object.",
                )
            db.insert_control_point(
                ControlPoint(
                    dataset_id=new_dataset_id,
                    image_x=_image_coordinate(value.get("image_x"), "image_x"),
                    image_y=_image_coordinate(value.get("image_y"), "image_y"),
                    longitude=_coordinate(value.get("longitude"), "longitude"),
                    latitude=_coordinate(value.get("latitude"), "latitude"),
                )
            )
        for value in project_data["icon_points"]:
            if not isinstance(value, dict):
                raise _error(
                    "INVALID_FOLDER_PROJECT",
                    "The selected project folder contains invalid user-created points.",
                    "Every icon point must be an object.",
                )
            db.insert_icon_point(
                IconPoint(
                    dataset_id=new_dataset_id,
                    icon_key=(str(value["icon_key"]) if value.get("icon_key") else None),
                    description=(str(value["description"]) if value.get("description") else None),
                    longitude=_coordinate(value.get("longitude"), "longitude"),
                    latitude=_coordinate(value.get("latitude"), "latitude"),
                )
            )
        db.insert_map_project(project)
        db.commit()
        return _response(project)
    except ApplicationError:
        db.rollback()
        for directory in reversed(final_directories):
            shutil.rmtree(directory, ignore_errors=True)
        raise
    except RepositoryError as exc:
        db.rollback()
        for directory in reversed(final_directories):
            shutil.rmtree(directory, ignore_errors=True)
        raise ApplicationError(
            status_code=500,
            code="FOLDER_IMPORT_DATABASE_ERROR",
            message="The project folder could not be imported.",
            details="The database transaction failed and staged files were removed.",
            field="folder",
        ) from exc
    except Exception as exc:
        db.rollback()
        for directory in reversed(final_directories):
            shutil.rmtree(directory, ignore_errors=True)
        raise ApplicationError(
            status_code=500,
            code="FOLDER_IMPORT_FAILED",
            message="The project folder could not be imported.",
            details="The folder could not be restored and staged files were removed.",
            field="folder",
        ) from exc
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)
