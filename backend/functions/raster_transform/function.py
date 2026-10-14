from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID

from config import settings
from functions.raster_transform.algorithm import (
    extract_raster_corners_wgs84,
    polygon_is_simple_and_convex,
    warp_raster_to_corners,
)
from functions.raster_transform.request import RasterTransformRequest, RasterCorners, CoordinatePoint
from functions.raster_transform.response import (
    RasterTransformData,
    RasterTransformResponse,
)
from functions.tile_generation.function import generate_tiles
from functions.tile_generation.request import TileGenerationRequest
from models.dataset import Dataset
from schemas.error import ApplicationError
from storage.session import RepositoryError, SessionRepository

logger = logging.getLogger(__name__)
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


def _load_dataset(db: SessionRepository, dataset_id: UUID) -> Dataset:
    try:
        dataset = db.get_dataset(dataset_id)
    except RepositoryError as exc:
        db.rollback()
        logger.exception("Failed to load dataset for raster transform.", exc_info=exc)
        raise _error(500, "DATABASE_ERROR", "A database error occurred.", "Could not load dataset.") from exc

    if dataset is None:
        raise _error(
            404,
            "DATASET_NOT_FOUND",
            "The dataset was not found.",
            "No dataset exists for the supplied dataset ID.",
            field="dataset_id",
        )
    return dataset


def _resolve_active_raster(dataset: Dataset, db: SessionRepository) -> Path:
    """Resolve the active raster file to process or inspect."""
    candidates = []
    if hasattr(db, "get_processed_dir"):
        processed_file = db.get_processed_dir(dataset.id) / "processed.tif"
        if processed_file.is_file():
            candidates.append(processed_file.resolve())

    if dataset.processed_path:
        cand = Path(dataset.processed_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())

    if dataset.georeferenced_path:
        cand = Path(dataset.georeferenced_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())

    if dataset.storage_path:
        cand = Path(dataset.storage_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())

    for c in candidates:
        if c.is_file():
            return c

    raise _error(
        404,
        "RASTER_NOT_FOUND",
        "No readable georeferenced raster was found for this dataset.",
        "Ensure the dataset is georeferenced and processed.",
        field="dataset_id",
    )


def _get_history_file(db: SessionRepository, dataset_id: UUID) -> Path:
    if hasattr(db, "get_processed_dir"):
        p_dir = db.get_processed_dir(dataset_id)
    else:
        p_dir = BACKEND_DIRECTORY / "storage" / "processed" / str(dataset_id)
    p_dir.mkdir(parents=True, exist_ok=True)
    return p_dir / "transform_history.json"


def _load_history(db: SessionRepository, dataset_id: UUID) -> dict[str, Any]:
    history_file = _get_history_file(db, dataset_id)
    if history_file.is_file():
        try:
            return json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"past": [], "future": [], "original_corners": None}


def _save_history(db: SessionRepository, dataset_id: UUID, history: dict[str, Any]) -> None:
    history_file = _get_history_file(db, dataset_id)
    history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")


def get_raster_transform_status(
    dataset_id: UUID,
    db: SessionRepository,
) -> RasterTransformResponse:
    dataset = _load_dataset(db, dataset_id)
    active_raster = _resolve_active_raster(dataset, db)

    meta = dict(dataset.extracted_metadata or {})
    corners, bounds, width, height = extract_raster_corners_wgs84(
        active_raster, fallback_bounds=meta.get("bounds")
    )
    history = _load_history(db, dataset_id)

    if not history.get("original_corners"):
        history["original_corners"] = corners.model_dump()
        _save_history(db, dataset_id, history)

    orig_corners = None
    if history.get("original_corners"):
        orig_corners = RasterCorners(**history["original_corners"])

    tf_meta = meta.get("raster_transform", {})

    return RasterTransformResponse(
        data=RasterTransformData(
            dataset_id=dataset.id,
            status="completed" if tf_meta.get("updated_at") else "not_configured",
            corners=corners,
            original_corners=orig_corners or corners,
            bounds=bounds,
            width=width,
            height=height,
            crs="EPSG:3857",
            rotation_angle=tf_meta.get("rotation_angle"),
            lock_aspect_ratio=bool(tf_meta.get("lock_aspect_ratio", False)),
            can_undo=len(history.get("past", [])) > 0,
            can_redo=len(history.get("future", [])) > 0,
            history_length=len(history.get("past", [])),
            tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
            updated_at=tf_meta.get("updated_at"),
            message="Raster transform status retrieved.",
        )
    )


def handle_raster_transform(
    dataset_id: UUID,
    request: RasterTransformRequest,
    db: SessionRepository,
) -> RasterTransformResponse:
    dataset = _load_dataset(db, dataset_id)
    active_raster = _resolve_active_raster(dataset, db)

    if hasattr(db, "get_processed_dir"):
        processed_dir = db.get_processed_dir(dataset.id)
    else:
        processed_dir = BACKEND_DIRECTORY / "storage" / "processed" / str(dataset.id)
    processed_dir.mkdir(parents=True, exist_ok=True)

    processed_tif = processed_dir / "processed.tif"
    orig_tif = processed_dir / "transform_original.tif"
    history = _load_history(db, dataset_id)

    # 1. Action: STATUS
    if request.action == "status":
        return get_raster_transform_status(dataset_id, db)

    # 2. Action: PREVIEW (pure calculation & validation, client preview)
    if request.action == "preview":
        if not request.corners:
            raise _error(400, "MISSING_CORNERS", "Target corners must be provided for preview.", "corners")
        if not polygon_is_simple_and_convex(request.corners):
            raise _error(422, "DEGENERATE_GEOMETRY", "Corners form a self-intersecting or degenerate polygon.", "corners")
        
        meta = dict(dataset.extracted_metadata or {})
        corners, bounds, width, height = extract_raster_corners_wgs84(
            active_raster, fallback_bounds=meta.get("bounds")
        )
        return RasterTransformResponse(
            data=RasterTransformData(
                dataset_id=dataset.id,
                status="preview",
                corners=request.corners,
                original_corners=RasterCorners(**history["original_corners"]) if history.get("original_corners") else corners,
                bounds=[
                    min(request.corners.top_left.longitude, request.corners.bottom_left.longitude),
                    min(request.corners.bottom_left.latitude, request.corners.bottom_right.latitude),
                    max(request.corners.top_right.longitude, request.corners.bottom_right.longitude),
                    max(request.corners.top_left.latitude, request.corners.top_right.latitude),
                ],
                width=width,
                height=height,
                crs="EPSG:3857",
                rotation_angle=request.rotation_angle,
                lock_aspect_ratio=request.lock_aspect_ratio,
                can_undo=len(history.get("past", [])) > 0,
                can_redo=len(history.get("future", [])) > 0,
                history_length=len(history.get("past", [])),
                message="Preview coordinates validated.",
            )
        )

    # 3. Action: RESET
    if request.action == "reset":
        with db.protect_operation("raster_transform_reset"):
            if orig_tif.is_file():
                shutil.copy2(orig_tif, processed_tif)
            
            # Clear history
            history["past"] = []
            history["future"] = []
            _save_history(db, dataset_id, history)

            # Regenerate tiles
            generate_tiles(
                TileGenerationRequest(
                    dataset_id=dataset.id,
                    min_zoom=dataset.tile_min_zoom or 0,
                    max_zoom=dataset.tile_max_zoom or 18,
                ),
                db,
                force=True,
            )

            now_str = datetime.now(timezone.utc).isoformat()
            meta = dict(dataset.extracted_metadata or {})
            meta["raster_transform"] = {
                "updated_at": now_str,
                "reset": True,
            }
            dataset.extracted_metadata = meta
            dataset.tile_status = "completed"
            db.save_dataset(dataset)
            db.commit()

            cur_corners, bounds, width, height = extract_raster_corners_wgs84(processed_tif)
            return RasterTransformResponse(
                data=RasterTransformData(
                    dataset_id=dataset.id,
                    status="reset",
                    corners=cur_corners,
                    original_corners=cur_corners,
                    bounds=bounds,
                    width=width,
                    height=height,
                    crs="EPSG:3857",
                    can_undo=False,
                    can_redo=False,
                    tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                    updated_at=now_str,
                    message="Raster reset to original transformation.",
                )
            )

    # 4. Action: UNDO / REDO
    if request.action in ("undo", "redo"):
        past = history.get("past", [])
        future = history.get("future", [])

        if request.action == "undo":
            if not past:
                raise _error(400, "CANNOT_UNDO", "No transformation history available to undo.", "action")
            step = past.pop()
            future.append(step)
            backup_step_path = processed_dir / f"step_{step['id']}.tif"
            target_step_path = processed_dir / f"step_{past[-1]['id']}.tif" if past else orig_tif
        else:
            if not future:
                raise _error(400, "CANNOT_REDO", "No transformation history available to redo.", "action")
            step = future.pop()
            past.append(step)
            target_step_path = processed_dir / f"step_{step['id']}.tif"

        with db.protect_operation(f"raster_transform_{request.action}"):
            if target_step_path.is_file():
                shutil.copy2(target_step_path, processed_tif)
            elif orig_tif.is_file():
                shutil.copy2(orig_tif, processed_tif)

            _save_history(db, dataset_id, history)

            generate_tiles(
                TileGenerationRequest(
                    dataset_id=dataset.id,
                    min_zoom=dataset.tile_min_zoom or 0,
                    max_zoom=dataset.tile_max_zoom or 18,
                ),
                db,
                force=True,
            )

            now_str = datetime.now(timezone.utc).isoformat()
            meta = dict(dataset.extracted_metadata or {})
            meta["raster_transform"] = {
                "updated_at": now_str,
            }
            dataset.extracted_metadata = meta
            dataset.tile_status = "completed"
            db.save_dataset(dataset)
            db.commit()

            cur_corners, bounds, width, height = extract_raster_corners_wgs84(processed_tif)
            return RasterTransformResponse(
                data=RasterTransformData(
                    dataset_id=dataset.id,
                    status="undone" if request.action == "undo" else "redone",
                    corners=cur_corners,
                    original_corners=RasterCorners(**history["original_corners"]) if history.get("original_corners") else cur_corners,
                    bounds=bounds,
                    width=width,
                    height=height,
                    crs="EPSG:3857",
                    can_undo=len(past) > 0,
                    can_redo=len(future) > 0,
                    history_length=len(past),
                    tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                    updated_at=now_str,
                    message=f"Raster transform {request.action} successful.",
                )
            )

    # 5. Action: APPLY
    if request.action == "apply":
        if not request.corners:
            raise _error(400, "MISSING_CORNERS", "Corners are required to apply transformation.", "corners")
        if not polygon_is_simple_and_convex(request.corners):
            raise _error(422, "DEGENERATE_GEOMETRY", "Corners form an invalid or self-intersecting polygon.", "corners")

        with db.protect_operation("raster_transform_apply"):
            # Ensure base original backup exists
            if not orig_tif.is_file():
                if processed_tif.is_file():
                    shutil.copy2(processed_tif, orig_tif)
                elif active_raster.is_file():
                    shutil.copy2(active_raster, orig_tif)

            # Record initial corners in history if absent
            if not history.get("original_corners"):
                meta = dict(dataset.extracted_metadata or {})
                init_corners, _, _, _ = extract_raster_corners_wgs84(
                    orig_tif, fallback_bounds=meta.get("bounds")
                )
                history["original_corners"] = init_corners.model_dump()

            step_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            temp_step = processed_dir / f"step_{step_id}.tif"

            # Warp the raster
            try:
                # Warp directly from the currently active processed_tif (or original) to new corners
                warp_source = processed_tif if processed_tif.is_file() else active_raster
                warp_info = warp_raster_to_corners(
                    input_path=warp_source,
                    output_path=temp_step,
                    corners=request.corners,
                    target_crs_str=request.target_crs,
                    resampling_str=request.resampling,
                )
            except Exception as exc:
                temp_step.unlink(missing_ok=True)
                logger.exception("Failed to warp raster.", exc_info=exc)
                raise _error(500, "WARP_FAILED", f"Warping failed: {str(exc)}", "corners") from exc

            # Replace processed_tif safely
            shutil.copy2(temp_step, processed_tif)

            # Append to history stack (max 15 entries)
            history.setdefault("past", []).append({
                "id": step_id,
                "mode": request.mode,
                "corners": request.corners.model_dump(),
                "rotation_angle": request.rotation_angle,
            })
            if len(history["past"]) > 15:
                old = history["past"].pop(0)
                (processed_dir / f"step_{old['id']}.tif").unlink(missing_ok=True)
            history["future"] = []
            _save_history(db, dataset_id, history)

            # Ensure dataset has processed_path pointing to processed_tif
            dataset.processed_path = processed_tif.resolve().as_posix()
            dataset.process_status = "completed"
            db.save_dataset(dataset)
            db.commit()

            # Regenerate tiles from updated processed.tif
            try:
                generate_tiles(
                    TileGenerationRequest(
                        dataset_id=dataset.id,
                        min_zoom=dataset.tile_min_zoom or 0,
                        max_zoom=dataset.tile_max_zoom or 18,
                    ),
                    db,
                    force=True,
                )
            except Exception as exc:
                logger.exception("Failed to regenerate tiles after raster transformation.", exc_info=exc)
                raise _error(500, "TILE_GENERATION_FAILED", "Failed to update map tiles.", "dataset_id") from exc

            now_str = datetime.now(timezone.utc).isoformat()
            meta = dict(dataset.extracted_metadata or {})
            meta["raster_transform"] = {
                "mode": request.mode,
                "corners": request.corners.model_dump(),
                "rotation_angle": request.rotation_angle,
                "lock_aspect_ratio": request.lock_aspect_ratio,
                "updated_at": now_str,
            }
            dataset.extracted_metadata = meta
            dataset.processed_path = processed_tif.resolve().as_posix()
            dataset.process_status = "completed"
            dataset.tile_status = "completed"
            db.save_dataset(dataset)
            db.commit()

            cur_corners, bounds, width, height = extract_raster_corners_wgs84(processed_tif)
            return RasterTransformResponse(
                data=RasterTransformData(
                    dataset_id=dataset.id,
                    status="completed",
                    corners=cur_corners,
                    original_corners=RasterCorners(**history["original_corners"]),
                    bounds=bounds,
                    width=width,
                    height=height,
                    crs="EPSG:3857",
                    rotation_angle=request.rotation_angle,
                    lock_aspect_ratio=request.lock_aspect_ratio,
                    can_undo=len(history["past"]) > 0,
                    can_redo=False,
                    history_length=len(history["past"]),
                    tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                    updated_at=now_str,
                    message="Raster transformed and tiles generated successfully.",
                )
            )

    raise _error(400, "INVALID_ACTION", f"Unsupported action: {request.action}", "action")
