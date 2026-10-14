import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any, BinaryIO, cast
from uuid import uuid4
import zipfile

from fastapi import BackgroundTasks, UploadFile
from rasterio.crs import CRS
from rasterio.transform import Affine, array_bounds
from starlette.concurrency import run_in_threadpool

from storage.session import RepositoryError, SessionRepository, DuplicateValueError, settings
from functions.metadata.function import extract_metadata
from functions.metadata.request import MetadataRequest
from functions.raster_process.function import process_raster
from functions.raster_process.request import RasterProcessRequest
from functions.tile_generation.function import generate_tiles
from functions.tile_generation.request import TileGenerationRequest
from functions.upload.function import _build_upload_response
from functions.upload.response import UploadResponse
from models.dataset import Dataset
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = BACKEND_DIRECTORY / "storage" / "uploads"
COPY_CHUNK_SIZE = 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50000
MAX_COMPRESSION_RATIO = 200
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
WORLD_SUFFIXES = {
    ".png": {".pgw", ".wld"},
    ".jpg": {".jgw", ".jpw", ".wld"},
    ".jpeg": {".jgw", ".jpw", ".wld"},
    ".tif": {".tfw", ".wld"},
    ".tiff": {".tfw", ".wld"},
    ".webp": {".wld"},
    ".bmp": {".bpw", ".wld"},
}
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _error(code: str, message: str, details: str) -> ApplicationError:
    return ApplicationError(
        status_code=400,
        code=code,
        message=message,
        details=details,
        field="file",
    )


def _safe_zip_name(filename: str | None) -> str:
    if not filename:
        raise _error(
            "INVALID_FILENAME",
            "The dataset ZIP has an invalid filename.",
            "Choose a non-empty .zip file.",
        )
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name.lower().endswith(".zip"):
        raise _error(
            "ZIP_REQUIRED",
            "A ZIP raster bundle is required.",
            "The redesigned upload accepts .zip files only.",
        )
    return name


def _safe_archive_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise _error(
            "UNSAFE_RASTER_ARCHIVE",
            "The raster bundle contains an unsafe path.",
            "Archive entries must use relative POSIX paths.",
        )
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".."} for part in path.parts):
        raise _error(
            "UNSAFE_RASTER_ARCHIVE",
            "The raster bundle contains an unsafe path.",
            "Archive entries cannot traverse directories.",
        )
    if path.parts and ":" in path.parts[0]:
        raise _error(
            "UNSAFE_RASTER_ARCHIVE",
            "The raster bundle contains an unsafe path.",
            "Windows drive paths are not allowed.",
        )
    return path.as_posix()


def _copy_upload(source: BinaryIO, destination: Path) -> None:
    total = 0
    maximum_size = settings.max_upload_size_mb * 1024 * 1024
    with destination.open("xb") as output:
        while chunk := source.read(COPY_CHUNK_SIZE):
            total += len(chunk)
            if total > maximum_size:
                raise ApplicationError(
                    status_code=413,
                    code="FILE_TOO_LARGE",
                    message="The dataset ZIP is too large.",
                    details=f"The maximum allowed size is {settings.max_upload_size_mb} MB.",
                    field="file",
                )
            output.write(chunk)
    if total == 0:
        raise _error(
            "EMPTY_FILE",
            "The dataset ZIP is empty.",
            "Choose a non-empty raster bundle.",
        )


def _archive_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
        raise _error(
            "INVALID_RASTER_ARCHIVE",
            "The raster bundle has an invalid number of entries.",
            f"A bundle must contain 1 to {MAX_ARCHIVE_ENTRIES} entries.",
        )
    maximum_expanded = settings.max_upload_size_mb * 4 * 1024 * 1024
    total_expanded = 0
    entries: dict[str, zipfile.ZipInfo] = {}
    folded_names: set[str] = set()
    for info in infos:
        raw_name = info.filename.replace("\\", "/").rstrip("/")
        if not raw_name or info.is_dir():
            continue

        name = _safe_archive_name(raw_name)

        # Skip macOS metadata, hidden resource forks, thumbs.db, and git metadata
        path_parts = name.split("/")
        if (
            any(part == "__MACOSX" for part in path_parts)
            or any(part.startswith("._") for part in path_parts)
            or any(part.startswith(".") for part in path_parts)
            or path_parts[-1].lower() in {".ds_store", "thumbs.db", "desktop.ini"}
        ):
            continue

        folded = name.casefold()
        if folded in folded_names:
            raise _error(
                "DUPLICATE_ARCHIVE_ENTRY",
                "The raster bundle contains duplicate paths.",
                "Archive paths must be unique, including letter case.",
            )
        folded_names.add(folded)
        mode = info.external_attr >> 16
        if info.flag_bits & 0x1 or stat.S_ISLNK(mode):
            raise _error(
                "UNSAFE_RASTER_ARCHIVE",
                "The raster bundle contains an unsupported entry.",
                "Encrypted files and symbolic links are not allowed.",
            )
        total_expanded += info.file_size
        if total_expanded > maximum_expanded:
            raise _error(
                "RASTER_ARCHIVE_TOO_LARGE",
                "The expanded raster bundle is too large.",
                "The archive exceeds the bounded expanded-size limit.",
            )
        if (
            info.file_size > 1024 * 1024
            and info.compress_size > 0
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise _error(
                "SUSPICIOUS_COMPRESSION_RATIO",
                "The raster bundle has an unsafe compression ratio.",
                "The archive may be a decompression bomb.",
            )
        entries[name] = info
    return entries


def _is_preview_or_thumb(name: str) -> bool:
    stem = PurePosixPath(name).stem.lower()
    return any(p in stem for p in ("preview", "thumb", "thumbnail", "quicklook", "overview"))


def _select_bundle_entries(
    entries: dict[str, zipfile.ZipInfo],
) -> list[tuple[str, list[str]]]:
    all_raster_names = [
        name for name in entries if PurePosixPath(name).suffix.lower() in RASTER_SUFFIXES
    ]
    if not all_raster_names:
        raise _error(
            "RASTER_NOT_FOUND",
            "The ZIP does not contain a supported raster.",
            "Include one or more PNG, JPEG, TIFF, or GeoTIFF files.",
        )

    non_previews = [n for n in all_raster_names if not _is_preview_or_thumb(n)]
    candidate_rasters = non_previews if non_previews else all_raster_names

    bundles: list[tuple[str, list[str]]] = []
    accounted_files: set[str] = set()

    for raster_name in candidate_rasters:
        raster_path = PurePosixPath(raster_name)
        allowed_world = WORLD_SUFFIXES.get(raster_path.suffix.lower(), set())

        selected = [raster_name]
        world_files: list[str] = []
        prj_files: list[str] = []

        for name in entries:
            if name == raster_name or name in candidate_rasters:
                continue
            path = PurePosixPath(name)
            same_source = (
                path.parent == raster_path.parent
                and path.stem.casefold() == raster_path.stem.casefold()
            )
            suffix = path.suffix.lower()
            if same_source and suffix in allowed_world:
                world_files.append(name)
            elif same_source and suffix == ".prj":
                prj_files.append(name)

        if len(world_files) > 1 or len(prj_files) > 1:
            raise _error(
                "AMBIGUOUS_RASTER_SIDECARS",
                "The ZIP contains duplicate georeference sidecars.",
                "Include at most one matching world file and one matching .prj file per raster.",
            )

        selected.extend(world_files)
        selected.extend(prj_files)
        accounted_files.update(selected)
        bundles.append((raster_name, selected))

    # Auxiliary files like manifest.json, README.txt, and documentation
    # do not prevent valid rasters from loading.
    return bundles


def _extract_floor_info(raster_name: str, manifest_data: dict, bundle_filename: str) -> dict[str, Any]:
    file_basename = PurePosixPath(raster_name).name.lower()
    floors = manifest_data.get("floors", []) if isinstance(manifest_data, dict) else []
    rec_group = manifest_data.get("recommended_grouping", {}) if isinstance(manifest_data, dict) else {}
    bundle_stem = PurePosixPath(bundle_filename).stem.replace("_", " ").title() if bundle_filename else "Building"
    building_name = (
        rec_group.get("building_name")
        or (manifest_data.get("project") if isinstance(manifest_data, dict) else None)
        or bundle_stem
    )

    for f in floors:
        if isinstance(f, dict) and PurePosixPath(f.get("filename", "")).name.lower() == file_basename:
            return {
                "building_name": building_name,
                "floor_level": int(f.get("level", 0)),
                "floor_label": str(f.get("label") or f.get("filename", "")),
                "floor_role": str(f.get("role", "")),
                "is_building_floor": True,
            }

    stem = PurePosixPath(raster_name).stem.lower()
    b_match = re.search(r'(?:basement[_-]?|b)(\d+)', stem)
    if b_match:
        lvl = -int(b_match.group(1))
        return {
            "building_name": building_name,
            "floor_level": lvl,
            "floor_label": f"BASEMENT {b_match.group(1)}",
            "floor_role": "parking",
            "is_building_floor": True,
        }
    if "ground" in stem or stem in {"g", "l0", "floor_0"}:
        return {
            "building_name": building_name,
            "floor_level": 0,
            "floor_label": "GROUND FLOOR",
            "floor_role": "lobby",
            "is_building_floor": True,
        }
    f_match = re.search(r'(?:floor[_-]?|level[_-]?|fl[_-]?|l)(\d+)', stem)
    if f_match:
        lvl = int(f_match.group(1))
        return {
            "building_name": building_name,
            "floor_level": lvl,
            "floor_label": f"FLOOR {lvl}",
            "floor_role": "office",
            "is_building_floor": True,
        }

    return {
        "building_name": building_name if len(floors) > 1 else None,
        "floor_level": 0,
        "floor_label": PurePosixPath(raster_name).stem.replace("_", " ").title(),
        "floor_role": None,
        "is_building_floor": bool(floors),
    }


def _extract_selected(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    selected: list[str],
    destination: Path,
) -> dict[str, Path]:
    extracted: dict[str, Path] = {}
    destination.mkdir(parents=True, exist_ok=False)
    for name in selected:
        output_path = destination / PurePosixPath(name).name
        with archive.open(entries[name], "r") as source, output_path.open("xb") as output:
            shutil.copyfileobj(source, output, COPY_CHUNK_SIZE)
        extracted[name] = output_path
    return extracted


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_sidecar_metadata(
    metadata: dict,
    raster_path: Path,
    selected_paths: list[Path],
) -> dict:
    result = dict(metadata)
    prj_path = next((path for path in selected_paths if path.suffix.lower() == ".prj"), None)
    world_path = next(
        (
            path
            for path in selected_paths
            if path != raster_path and path.suffix.lower() != ".prj"
        ),
        None,
    )
    if not result.get("crs") and prj_path is not None:
        try:
            result["crs"] = CRS.from_wkt(prj_path.read_text(encoding="utf-8")).to_string()
        except (OSError, UnicodeError, ValueError) as exc:
            raise _error(
                "INVALID_CRS_SIDECAR",
                "The raster CRS sidecar is invalid.",
                "The matching .prj file must contain valid WKT.",
            ) from exc
    if not result.get("transform") and world_path is not None:
        try:
            values = [float(line.strip()) for line in world_path.read_text().splitlines() if line.strip()]
            if len(values) != 6:
                raise ValueError("world file requires six values")
            a, d, b, e, center_x, center_y = values
            transform = Affine(
                a,
                b,
                center_x - (a + b) / 2,
                d,
                e,
                center_y - (d + e) / 2,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise _error(
                "INVALID_WORLD_FILE",
                "The raster world file is invalid.",
                "The matching world file must contain six finite numeric values.",
            ) from exc
        result["transform"] = [
            float(transform.a),
            float(transform.b),
            float(transform.c),
            float(transform.d),
            float(transform.e),
            float(transform.f),
        ]
        height = int(result["height"])
        width = int(result["width"])
        bounds = array_bounds(height, width, transform)
        left, bottom, right, top = bounds
        result["bounds"] = {
            "min_x": float(left),
            "min_y": float(bottom),
            "max_x": float(right),
            "max_y": float(top),
        }
    result["georeference_source"] = (
        "embedded"
        if metadata.get("crs") and metadata.get("transform")
        else "sidecar"
        if result.get("crs") and result.get("transform")
        else "none"
    )
    return result


def _schedule_processing(
    background_tasks: BackgroundTasks,
    dataset_id,
    session_id: str | None = None,
) -> None:
    def run_processing() -> None:
        from storage.session import session_storage
        bg_db = session_storage.get_session(session_id) if session_id else None
        if bg_db is None:
            from storage.session import get_session_repository
            bg_db = get_session_repository()
        with bg_db.protect_operation("processing"):
            try:
                process_raster(
                    RasterProcessRequest(
                        dataset_id=dataset_id,
                        target_crs="EPSG:3857",
                        resampling="bilinear",
                    ),
                    bg_db,
                )
                generate_tiles(
                    TileGenerationRequest(dataset_id=dataset_id, min_zoom=0, max_zoom=18),
                    bg_db,
                )
            except Exception as exc:
                logger.exception("Failed to process imported raster bundle.", exc_info=exc)

    background_tasks.add_task(run_processing)


async def import_raster_zip(
    file: UploadFile | None,
    db: SessionRepository,
    background_tasks: BackgroundTasks,
) -> UploadResponse:
    validated_file = cast(UploadFile, file)
    _safe_zip_name(None if file is None else file.filename)
    if file is None:
        raise _error("FILE_REQUIRED", "A dataset ZIP is required.", "No file was uploaded.")

    dataset_directory: Path | None = None
    with tempfile.TemporaryDirectory(prefix="mapstudio-raster-zip-") as temporary:
        temporary_root = Path(temporary)
        package_path = temporary_root / "bundle.zip"
        await validated_file.seek(0)
        await run_in_threadpool(_copy_upload, validated_file.file, package_path)
        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                entries = _archive_entries(archive)
                manifest_data = {}
                for entry_name in entries:
                    if PurePosixPath(entry_name).name.lower() == "manifest.json":
                        try:
                            manifest_data = json.loads(archive.read(entries[entry_name]).decode("utf-8"))
                        except Exception:
                            pass
                        break
                bundles = _select_bundle_entries(entries)
                imported_datasets: list[Dataset] = []
                any_existing = False

                for idx, (raster_name, selected) in enumerate(bundles):
                    staged_directory = temporary_root / f"dataset_{idx}"
                    extracted = _extract_selected(
                        archive,
                        entries,
                        selected,
                        staged_directory,
                    )
                    staged_raster = extracted[raster_name]
                    file_hash = await run_in_threadpool(_file_hash, staged_raster)

                    try:
                        existing = db.find_dataset_by_hash(file_hash)
                    except RepositoryError as exc:
                        raise ApplicationError(
                            status_code=500,
                            code="DATABASE_ERROR",
                            message="The raster bundle could not be checked.",
                            details="The database lookup failed.",
                        ) from exc

                    if existing is not None:
                        imported_datasets.append(existing)
                        any_existing = True
                        continue

                    suffix = staged_raster.suffix.lower()
                    format_name = "tiff" if suffix in {".tif", ".tiff"} else suffix.lstrip(".")
                    metadata_response = await extract_metadata(
                        MetadataRequest(
                            file_path=str(staged_raster),
                            format=format_name,
                            category="raster",
                        )
                    )
                    metadata = _apply_sidecar_metadata(
                        dict(metadata_response.data.metadata),
                        staged_raster,
                        list(extracted.values()),
                    )
                    metadata["format"] = metadata_response.data.format
                    metadata["category"] = "raster"
                    metadata["bundle_filename"] = validated_file.filename
                    floor_info = _extract_floor_info(raster_name, manifest_data, validated_file.filename or "")
                    metadata["building_name"] = floor_info["building_name"]
                    metadata["floor_level"] = floor_info["floor_level"]
                    metadata["floor_label"] = floor_info["floor_label"]
                    metadata["floor_role"] = floor_info["floor_role"]
                    metadata["is_building_floor"] = floor_info["is_building_floor"]
                    is_georeferenced = bool(metadata.get("crs") and metadata.get("transform"))

                    dataset_id = uuid4()
                    is_default_upload_dir = UPLOAD_DIRECTORY == BACKEND_DIRECTORY / "storage" / "uploads"
                    if is_default_upload_dir and hasattr(db, "get_source_dir") and hasattr(db, "session_dir"):
                        dataset_directory = db.get_source_dir(dataset_id)
                        stored_raster = dataset_directory / staged_raster.name
                        try:
                            relative_path = stored_raster.relative_to(BACKEND_DIRECTORY).as_posix()
                        except ValueError:
                            relative_path = stored_raster.as_posix()
                    else:
                        dataset_directory = UPLOAD_DIRECTORY / str(dataset_id)
                        stored_raster = dataset_directory / staged_raster.name
                        relative_path = (
                            Path("storage") / "uploads" / str(dataset_id) / staged_raster.name
                        ).as_posix()

                    try:
                        dataset_directory.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(staged_directory), str(dataset_directory))
                    except OSError as exc:
                        if dataset_directory.exists():
                            shutil.rmtree(dataset_directory, ignore_errors=True)
                        raise ApplicationError(
                            status_code=500,
                            code="FILE_SAVE_ERROR",
                            message="The raster bundle could not be saved.",
                            details="The server could not move the validated bundle into managed storage.",
                            field="file",
                        ) from exc

                    content_type = CONTENT_TYPES.get(suffix, "image/png" if suffix == ".png" else "application/octet-stream")
                    dataset = Dataset(
                        id=dataset_id,
                        filename=stored_raster.name,
                        file_size=stored_raster.stat().st_size,
                        content_type=content_type,
                        file_hash=file_hash,
                        storage_path=relative_path,
                        extracted_metadata=metadata,
                        georeferenced_path=relative_path if is_georeferenced else None,
                        georeference_status="completed" if is_georeferenced else "not_started",
                    )
                    try:
                        db.insert_dataset(dataset)
                        db.commit()
                    except DuplicateValueError:
                        db.rollback()
                        shutil.rmtree(dataset_directory, ignore_errors=True)
                        existing = db.find_dataset_by_hash(file_hash)
                        if existing is not None:
                            imported_datasets.append(existing)
                            any_existing = True
                            continue
                        raise
                    except RepositoryError as exc:
                        db.rollback()
                        shutil.rmtree(dataset_directory, ignore_errors=True)
                        raise ApplicationError(
                            status_code=500,
                            code="DATABASE_ERROR",
                            message="The raster bundle could not be registered.",
                            details="The database operation failed.",
                        ) from exc

                    if is_georeferenced:
                        _schedule_processing(background_tasks, dataset.id, getattr(db, "session_id", None))

                    imported_datasets.append(dataset)

        except zipfile.BadZipFile as exc:
            raise _error(
                "INVALID_RASTER_ARCHIVE",
                "The uploaded file is not a readable ZIP.",
                "Create a standard ZIP containing raster datasets.",
            ) from exc

    if not imported_datasets:
        raise _error(
            "RASTER_NOT_FOUND",
            "No valid raster datasets could be imported from the archive.",
            "Verify the archive contains supported raster files.",
        )

    if any((d.extracted_metadata or {}).get("is_building_floor") for d in imported_datasets):
        imported_datasets.sort(key=lambda d: (d.extracted_metadata or {}).get("floor_level", 0))

    primary = next(
        (d for d in imported_datasets if (d.extracted_metadata or {}).get("floor_level") == 0),
        imported_datasets[0],
    )

    if len(imported_datasets) > 1:
        try:
            from functions.workspace.function import _load_project, attach_workspace_member
            from functions.workspace.request import WorkspaceMemberCreateRequest
            project = _load_project(primary.id, db)
            b_name = (primary.extracted_metadata or {}).get("building_name")
            if b_name:
                project.name = b_name
                db.save_map_project(project)

            primary_mem = db.get_workspace_member(project.id, primary.id)
            if primary_mem:
                primary_mem.alias = (primary.extracted_metadata or {}).get("floor_label") or primary.filename
                primary_mem.sort_order = (primary.extracted_metadata or {}).get("floor_level", 0)
                db.save_workspace_member(primary_mem)

            for extra in imported_datasets:
                if extra.id != primary.id:
                    try:
                        attach_workspace_member(
                            primary.id,
                            WorkspaceMemberCreateRequest(dataset_id=extra.id),
                            db,
                        )
                        extra_mem = db.get_workspace_member(project.id, extra.id)
                        if extra_mem:
                            extra_mem.alias = (extra.extracted_metadata or {}).get("floor_label") or extra.filename
                            extra_mem.sort_order = (extra.extracted_metadata or {}).get("floor_level", 0)
                            db.save_workspace_member(extra_mem)
                    except Exception:
                        pass
            db.commit()
        except Exception:
            pass

    count = len(imported_datasets)
    message = (
        f"Imported {count} raster datasets successfully."
        if count > 1
        else ("This file already exists." if any_existing else "File uploaded successfully.")
    )
    return _build_upload_response(
        primary,
        existing=(count == 1 and any_existing),
        message=message,
        imported_datasets=imported_datasets,
    )
