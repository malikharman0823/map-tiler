from __future__ import annotations

import hashlib
import json
import math
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from uuid import uuid4

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from storage.session import RepositoryError, SessionRepository, settings
from functions.map_projects.response import MapProjectResponse
from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from schemas.error import ApplicationError

PACKAGE_VERSION = 1
MAX_ARCHIVE_ENTRIES = 500000  # Zips can have a lot of tiles
MAX_COMPRESSION_RATIO = 200
COPY_CHUNK_SIZE = 1024 * 1024
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
PROCESSED_DIRECTORY = BACKEND_DIRECTORY / "storage" / "processed"
TILES_DIRECTORY = BACKEND_DIRECTORY / "storage" / "tiles"

FORMAT_BY_SUFFIX = {
    ".jpg": ("jpg", "raster"),
    ".jpeg": ("jpeg", "raster"),
    ".png": ("png", "raster"),
    ".tif": ("tiff", "raster"),
    ".tiff": ("tiff", "raster"),
    ".gpkg": ("geopackage", "vector"),
    ".geojson": ("geojson", "vector"),
    ".json": ("json", "document"),
    ".mbtiles": ("mbtiles", "tiles"),
    ".kml": ("kml", "vector"),
    ".kmz": ("kmz", "vector"),
    ".osm": ("osm", "osm"),
    ".pbf": ("osm_pbf", "osm"),
}

def _error(code: str, message: str, details: str) -> ApplicationError:
    return ApplicationError(
        status_code=400,
        code=code,
        message=message,
        details=details,
        field="file",
    )

def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise _error(
            "INVALID_FILENAME",
            "The project file has an invalid filename.",
            "A .zip filename is required.",
        )
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not (name.lower().endswith(".zip") or name.lower().endswith(".mtmap")):
        raise _error(
            "UNSUPPORTED_PROJECT_FORMAT",
            "The project file type is not supported.",
            "Open Project accepts .mtmap and .zip packages only.",
        )
    return name

def _copy_upload(source: BinaryIO, destination: Path, maximum_size: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with destination.open("xb") as output:
        while chunk := source.read(COPY_CHUNK_SIZE):
            total += len(chunk)
            if total > maximum_size:
                raise _error(
                    "PROJECT_FILE_TOO_LARGE",
                    "The project package is too large.",
                    f"The maximum allowed package size is {settings.max_upload_size_mb} MB.",
                )
            digest.update(chunk)
            output.write(chunk)
    if total == 0:
        raise _error(
            "EMPTY_FILE",
            "The project package is empty.",
            "A non-empty .zip package is required.",
        )
    return digest.hexdigest()

def _safe_archive_name(name: str) -> str:
    if not name or "\\" in name or name.startswith(("/", "\\")):
        raise _error(
            "UNSAFE_PROJECT_ARCHIVE",
            "The project package contains an unsafe path.",
            "Archive entries must use relative POSIX paths.",
        )
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _error(
            "UNSAFE_PROJECT_ARCHIVE",
            "The project package contains an unsafe path.",
            "Archive entries cannot be absolute or traverse directories.",
        )
    if path.parts and ":" in path.parts[0]:
        raise _error(
            "UNSAFE_PROJECT_ARCHIVE",
            "The project package contains an unsafe path.",
            "Windows drive paths are not allowed in project packages.",
        )
    return path.as_posix()

def _validate_archive_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
        raise _error(
            "INVALID_PROJECT_ARCHIVE",
            "The project package has an invalid number of entries.",
            f"Packages must contain 1 to {MAX_ARCHIVE_ENTRIES} files.",
        )
    maximum_expanded_size = settings.max_upload_size_mb * 4 * 1024 * 1024
    total_size = 0
    entries: dict[str, zipfile.ZipInfo] = {}
    casefolded: set[str] = set()
    for info in infos:
        name = _safe_archive_name(info.filename.rstrip("/"))
        folded = name.casefold()
        if folded in casefolded:
            raise _error(
                "DUPLICATE_ARCHIVE_ENTRY",
                "The project package contains duplicate paths.",
                "Archive paths must be unique, including letter case.",
            )
        casefolded.add(folded)
        mode = info.external_attr >> 16
        if info.flag_bits & 0x1 or stat.S_ISLNK(mode):
            raise _error(
                "UNSAFE_PROJECT_ARCHIVE",
                "The project package contains an unsupported entry.",
                "Encrypted files and symbolic links are not allowed.",
            )
        if info.is_dir():
            continue
        total_size += info.file_size
        if total_size > maximum_expanded_size:
            raise _error(
                "PROJECT_ARCHIVE_TOO_LARGE",
                "The expanded project package is too large.",
                "The archive exceeds the bounded expanded-size limit.",
            )
        if (
            info.file_size > 1024 * 1024
            and info.compress_size > 0
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise _error(
                "SUSPICIOUS_COMPRESSION_RATIO",
                "The project package has an unsafe compression ratio.",
                "The archive may be a decompression bomb.",
            )
        entries[name] = info
    return entries

def _read_archive_json(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    name: str,
    maximum_size: int = 5 * 1024 * 1024,
) -> dict[str, Any] | None:
    info = entries.get(name)
    if info is None:
        return None
    if info.file_size > maximum_size:
        raise _error(
            "INVALID_PROJECT_PACKAGE",
            "The project package has a file that is too large.",
            f"{name} must remain within its size limit.",
        )
    try:
        value = json.loads(archive.read(info).decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error(
            "INVALID_PROJECT_JSON",
            "The project package metadata is invalid.",
            f"{name} must contain one valid UTF-8 JSON object.",
        ) from exc
    if not isinstance(value, dict):
        raise _error(
            "INVALID_PROJECT_JSON",
            "The project package metadata is invalid.",
            f"{name} must contain a JSON object.",
        )
    return value

def _response(project: MapProject) -> MapProjectResponse:
    return MapProjectResponse(
        id=project.id,
        name=project.name,
        dataset_id=project.dataset_id,
        configuration=project.configuration,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )

def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _error(
            "INVALID_PROJECT_DATA",
            "The project contains invalid point data.",
            f"{field} must be a finite number.",
        ) from exc
    if not math.isfinite(number):
        raise _error(
            "INVALID_PROJECT_DATA",
            "The project contains invalid point data.",
            f"{field} must be a finite number.",
        )
    return number

def _coordinate(value: Any, field: str) -> float:
    number = _finite(value, field)
    minimum, maximum = (-90, 90) if field == "latitude" else (-180, 180)
    if number < minimum or number > maximum:
        raise _error(
            "INVALID_PROJECT_DATA",
            "The project contains invalid point coordinates.",
            f"{field} must be between {minimum} and {maximum}.",
        )
    return number

def _image_coordinate(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number < 0:
        raise _error(
            "INVALID_PROJECT_DATA",
            "The project contains invalid image coordinates.",
            f"{field} must be zero or greater.",
        )
    return number


def _parse_zoom_level(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def import_project(file: UploadFile, db: SessionRepository) -> MapProjectResponse:
    _safe_filename(file.filename)
    temporary_directory = Path(tempfile.mkdtemp(prefix="maptiler-import-"))
    package_path = temporary_directory / "upload.zip"
    final_directories: list[Path] = []
    try:
        await file.seek(0)
        package_hash = await run_in_threadpool(
            _copy_upload,
            file.file,
            package_path,
            settings.max_upload_size_mb * 1024 * 1024,
        )
        existing_dataset = db.find_dataset_by_hash(package_hash)
        if existing_dataset is not None:
            existing_project = db.get_map_project_by_dataset_id(existing_dataset.id)
            if existing_project is not None:
                return _response(existing_project)

        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                entries = _validate_archive_entries(archive)
                manifest_json = _read_archive_json(archive, entries, "manifest.json")
                if manifest_json is not None:
                    files_declared = manifest_json.get("files", [])
                    for item in files_declared:
                        rel_path = item.get("path")
                        if not rel_path or rel_path not in entries:
                            raise _error(
                                "PROJECT_INTEGRITY_ERROR",
                                "The project package has been corrupted or altered.",
                                f"Declared file {rel_path} was not found in the archive.",
                            )
                        raw_bytes = archive.read(entries[rel_path])
                        if len(raw_bytes) != item.get("size"):
                            raise _error(
                                "PROJECT_INTEGRITY_ERROR",
                                "The project package has been corrupted or altered.",
                                f"File size mismatch for {rel_path}.",
                            )
                        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
                        if actual_hash != item.get("sha256"):
                            raise _error(
                                "PROJECT_INTEGRITY_ERROR",
                                "The project package has been corrupted or altered.",
                                f"File hash mismatch for {rel_path}.",
                            )

                    project_json = _read_archive_json(archive, entries, "project.json")
                    if project_json is None:
                        raise _error(
                            "PROJECT_INTEGRITY_ERROR",
                            "The project package is missing project.json.",
                            "A project.json file must be declared and present.",
                        )

                    new_dataset_id = uuid4()
                    upload_directory = UPLOAD_DIRECTORY / str(new_dataset_id)
                    upload_directory.mkdir(parents=True, exist_ok=False)
                    final_directories.append(upload_directory)

                    source_decl = next((f for f in files_declared if f.get("role") == "source"), None)
                    source_rel = source_decl.get("path") if source_decl else None
                    dataset_meta = project_json.get("dataset", {})
                    source_filename = dataset_meta.get("filename") or (Path(source_rel).name if source_rel else "source.bin")
                    content_type = dataset_meta.get("content_type") or "application/octet-stream"

                    if source_rel and source_rel in entries:
                        source_dest = upload_directory / Path(source_rel).name
                        with archive.open(entries[source_rel]) as src, source_dest.open("xb") as dst:
                            shutil.copyfileobj(src, dst)
                        relative_source = source_dest.relative_to(BACKEND_DIRECTORY).as_posix()
                        file_size = source_dest.stat().st_size
                    else:
                        stored_pkg = upload_directory / source_filename
                        shutil.copy2(package_path, stored_pkg)
                        relative_source = stored_pkg.relative_to(BACKEND_DIRECTORY).as_posix()
                        file_size = stored_pkg.stat().st_size

                    dataset = Dataset(
                        id=new_dataset_id,
                        filename=source_filename,
                        file_size=file_size,
                        content_type=content_type,
                        file_hash=package_hash,
                        storage_path=relative_source,
                        extracted_metadata={},
                        georeference_status="not_started",
                        process_status="not_started",
                        tile_status="not_started",
                    )
                    db.insert_dataset(dataset)

                    project_info = project_json.get("project", {})
                    project = MapProject(
                        id=uuid4(),
                        name=str(project_info.get("name") or "Imported Project")[:255],
                        dataset_id=new_dataset_id,
                        configuration=project_info.get("configuration", {}),
                    )
                    db.insert_map_project(project)

                    for pt in project_json.get("control_points", []):
                        db.insert_control_point(
                            ControlPoint(
                                id=uuid4(),
                                dataset_id=new_dataset_id,
                                image_x=_image_coordinate(pt.get("image_x"), "image_x"),
                                image_y=_image_coordinate(pt.get("image_y"), "image_y"),
                                longitude=_coordinate(pt.get("longitude"), "longitude"),
                                latitude=_coordinate(pt.get("latitude"), "latitude"),
                            )
                        )

                    for ip in project_json.get("icon_points", []):
                        db.insert_icon_point(
                            IconPoint(
                                id=uuid4(),
                                dataset_id=new_dataset_id,
                                icon_key=(str(ip["icon_key"]) if ip.get("icon_key") else None),
                                description=(str(ip["description"]) if ip.get("description") else None),
                                longitude=_coordinate(ip.get("longitude"), "longitude"),
                                latitude=_coordinate(ip.get("latitude"), "latitude"),
                            )
                        )

                    db.commit()
                    return _response(project)

                metadata_json = _read_archive_json(archive, entries, "metadata.json")
                if metadata_json is None:
                    raise _error(
                        "MISSING_METADATA",
                        "The project package is missing metadata.json.",
                        "A metadata.json file must be at the root of the archive.",
                    )
                
                mapstudio_json = _read_archive_json(archive, entries, "mapstudio.json")

                new_dataset_id = uuid4()
                upload_directory = UPLOAD_DIRECTORY / str(new_dataset_id)
                tiles_directory = TILES_DIRECTORY / str(new_dataset_id)
                upload_directory.mkdir(parents=True, exist_ok=False)
                tiles_directory.mkdir(parents=True, exist_ok=False)
                final_directories.extend([upload_directory, tiles_directory])
                
                # Extract tiles
                tile_count = 0
                for name, info in entries.items():
                    # Tiles are usually named like 15/123/456.png
                    parts = name.split("/")
                    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].endswith(".png"):
                        destination = (tiles_directory / name).resolve()
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as source, destination.open("xb") as output:
                            shutil.copyfileobj(source, output)
                        tile_count += 1
                
                # Extract source asset if any
                source_asset_path = None
                source_filename = f"import_{new_dataset_id}.zip"
                content_type = "application/zip"
                if mapstudio_json:
                    dataset_meta = mapstudio_json.get("dataset", {})
                    source_asset = dataset_meta.get("source_asset")
                    source_filename = dataset_meta.get("filename") or source_filename
                    content_type = dataset_meta.get("content_type") or content_type
                    if source_asset and source_asset in entries:
                        source_info = entries[source_asset]
                        source_destination = upload_directory / Path(source_asset).name
                        with archive.open(source_info) as source, source_destination.open("xb") as output:
                            shutil.copyfileobj(source, output)
                        source_asset_path = source_destination
                
                # Map Studio folder ZIPs are already georeferenced tile packages.
                is_mapstudio_folder = mapstudio_json is not None and tile_count > 0
                min_zoom = _parse_zoom_level(metadata_json.get("minzoom"))
                max_zoom = _parse_zoom_level(metadata_json.get("maxzoom"))
                if is_mapstudio_folder:
                    db_metadata = {
                        "format": "mapstudio_folder",
                        "category": "tiles",
                        "tile_format": "png",
                        "bounds": metadata_json.get("bounds"),
                        "min_zoom": min_zoom if min_zoom is not None else 0,
                        "max_zoom": max_zoom if max_zoom is not None else 0,
                        "profile": metadata_json.get("profile", "mercator"),
                        "import_package_hash": package_hash,
                    }
                else:
                    db_metadata = dict(metadata_json)
                    db_metadata["import_package_hash"] = package_hash

                if source_asset_path:
                    relative_source = source_asset_path.relative_to(BACKEND_DIRECTORY).as_posix()
                    file_size = source_asset_path.stat().st_size
                else:
                    # Save the whole package in upload_directory if no individual source asset
                    stored_package = upload_directory / source_filename
                    shutil.copy2(package_path, stored_package)
                    relative_source = stored_package.relative_to(BACKEND_DIRECTORY).as_posix()
                    file_size = stored_package.stat().st_size

                if is_mapstudio_folder:
                    db_metadata["source_asset"] = relative_source if source_asset_path else None
                
                georeferenced_path = None
                georeference_status = "completed" if is_mapstudio_folder else "not_started"
                processed_path = None
                process_status = "completed" if is_mapstudio_folder else "not_started"
                
                # Setup dataset
                dataset = Dataset(
                    id=new_dataset_id,
                    filename=source_filename,
                    file_size=file_size,
                    content_type=content_type,
                    file_hash=package_hash,
                    storage_path=relative_source,
                    extracted_metadata=db_metadata,
                    georeferenced_path=georeferenced_path,
                    georeference_status=georeference_status,
                    processed_path=processed_path,
                    process_status=process_status,
                    tile_path=tiles_directory.relative_to(BACKEND_DIRECTORY).as_posix() if tile_count > 0 else None,
                    tile_min_zoom=min_zoom,
                    tile_max_zoom=max_zoom,
                    tile_status="completed" if tile_count > 0 else "not_started",
                )
                db.insert_dataset(dataset)
                
                # Setup project
                if mapstudio_json:
                    project_meta = mapstudio_json.get("project", {})
                    project = MapProject(
                        id=uuid4(),
                        name=str(project_meta.get("name") or "Imported Project")[:255],
                        dataset_id=new_dataset_id,
                        configuration=project_meta.get("configuration", {}),
                    )
                    
                    for point in mapstudio_json.get("control_points", []):
                        db.insert_control_point(
                            ControlPoint(
                                id=uuid4(),
                                dataset_id=new_dataset_id,
                                image_x=_image_coordinate(point.get("image_x"), "image_x"),
                                image_y=_image_coordinate(point.get("image_y"), "image_y"),
                                longitude=_coordinate(point.get("longitude"), "longitude"),
                                latitude=_coordinate(point.get("latitude"), "latitude"),
                            )
                        )
                    
                    for point in mapstudio_json.get("icon_points", []):
                        db.insert_icon_point(
                            IconPoint(
                                id=uuid4(),
                                dataset_id=new_dataset_id,
                                icon_key=(str(point["icon_key"]) if point.get("icon_key") else None),
                                description=(str(point["description"]) if point.get("description") else None),
                                longitude=_coordinate(point.get("longitude"), "longitude"),
                                latitude=_coordinate(point.get("latitude"), "latitude"),
                            )
                        )
                else:
                    project = MapProject(
                        id=uuid4(),
                        name=str(metadata_json.get("name") or "Imported Map")[:255],
                        dataset_id=new_dataset_id,
                        configuration={},
                    )
                db.insert_map_project(project)
                db.commit()
                return _response(project)
        except zipfile.BadZipFile as exc:
            raise _error(
                "INVALID_PROJECT_ARCHIVE",
                "The project package is not a valid ZIP archive.",
                "The .zip file is corrupt or incomplete.",
            ) from exc

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
            code="PROJECT_IMPORT_DATABASE_ERROR",
            message="The project could not be imported.",
            details="The database transaction failed and staged files were removed.",
            field="file",
        ) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Import failed:", exc_info=exc)
        db.rollback()
        for directory in reversed(final_directories):
            shutil.rmtree(directory, ignore_errors=True)
        raise ApplicationError(
            status_code=500,
            code="PROJECT_IMPORT_FAILED",
            message="The project could not be imported.",
            details="The package could not be restored and staged files were removed.",
            field="file",
        ) from exc
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)
