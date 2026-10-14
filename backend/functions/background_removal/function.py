from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID

from config import settings
from functions.background_removal.algorithm import (
    generate_raster_preview,
    parse_hex_color,
    process_raster_background_removal,
)
from functions.background_removal.request import BackgroundRemovalRequest
from functions.background_removal.response import (
    BackgroundRemovalData,
    BackgroundRemovalResponse,
)
from functions.raster_process.function import process_raster
from functions.raster_process.request import RasterProcessRequest
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
        logger.exception("Failed to load dataset for background removal.", exc_info=exc)
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


def _resolve_source_path(dataset: Dataset, db: SessionRepository) -> Path:
    """Resolve the active raster file to process."""
    candidates = []
    if dataset.processed_path:
        cand = Path(dataset.processed_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())
    if dataset.georeferenced_path:
        cand = Path(dataset.georeferenced_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())
    if dataset.storage_path:
        cand = Path(dataset.storage_path)
        candidates.append(cand if cand.is_absolute() else (BACKEND_DIRECTORY / cand).resolve())

    # Fallback to session dataset directories
    if hasattr(db, "get_processed_dir"):
        processed_file = db.get_processed_dir(dataset.id) / "processed.tif"
        if processed_file.is_file():
            candidates.insert(0, processed_file.resolve())

    for c in candidates:
        if c.is_file():
            return c

    raise _error(
        404,
        "RASTER_NOT_FOUND",
        "The raster file was not found.",
        "Ensure the dataset has a valid uploaded or georeferenced raster.",
        field="dataset_id",
    )


def get_background_removal_status(
    dataset_id: UUID,
    db: SessionRepository,
) -> BackgroundRemovalResponse:
    dataset = _load_dataset(db, dataset_id)
    meta = (dataset.extracted_metadata or {}).get("background_removal", {})
    enabled = bool(meta.get("enabled", False))
    color = meta.get("color", "#ffffff")
    threshold = int(meta.get("threshold", 30))
    softness = int(meta.get("edge_softness", 10))
    updated_at = meta.get("updated_at")

    tile_url = None
    if dataset.tile_path and dataset.tile_status == "completed":
        tile_url = f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png"

    return BackgroundRemovalResponse(
        data=BackgroundRemovalData(
            dataset_id=dataset.id,
            status="completed" if enabled else "not_configured",
            enabled=enabled,
            color=color,
            threshold=threshold,
            edge_softness=softness,
            tile_url_template=tile_url,
            message="Background removal is currently active." if enabled else "Background removal is not active.",
            updated_at=updated_at,
        )
    )


def handle_background_removal(
    dataset_id: UUID,
    request: BackgroundRemovalRequest,
    db: SessionRepository,
) -> BackgroundRemovalResponse:
    dataset = _load_dataset(db, dataset_id)
    target_rgb = parse_hex_color(request.color)
    source_path = _resolve_source_path(dataset, db)

    # 1. Status action
    if request.action == "status":
        return get_background_removal_status(dataset_id, db)

    # 2. Preview action
    if request.action == "preview":
        try:
            orig_url, prev_url = generate_raster_preview(
                source_path,
                target_color=target_rgb,
                threshold=request.threshold,
                edge_softness=request.edge_softness,
                max_dimension=600,
            )
            return BackgroundRemovalResponse(
                data=BackgroundRemovalData(
                    dataset_id=dataset.id,
                    status="preview",
                    enabled=False,
                    color=request.color,
                    threshold=request.threshold,
                    edge_softness=request.edge_softness,
                    preview_data_url=prev_url,
                    original_data_url=orig_url,
                    message="Preview generated successfully.",
                )
            )
        except Exception as exc:
            logger.exception("Failed to generate background removal preview.", exc_info=exc)
            raise _error(
                500,
                "PREVIEW_GENERATION_FAILED",
                "Failed to generate background removal preview.",
                str(exc),
                field="color",
            ) from exc

    # Determine processed GeoTIFF location
    if hasattr(db, "get_processed_dir"):
        processed_dir = db.get_processed_dir(dataset.id)
    else:
        processed_dir = BACKEND_DIRECTORY / "storage" / "processed" / str(dataset.id)
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_tif = processed_dir / "processed.tif"
    backup_tif = processed_dir / "processed_original.tif"

    # Determine tile location
    if hasattr(db, "get_tiles_dir"):
        tiles_dir = db.get_tiles_dir(dataset.id)
    else:
        tiles_dir = BACKEND_DIRECTORY / "storage" / "tiles" / str(dataset.id)
    backup_tiles_dir = processed_dir / "tiles_original"

    # 3. Reset action
    if request.action == "reset":
        with db.protect_operation("background_removal_reset"):
            # Restore original processed.tif if backup exists
            if backup_tif.is_file():
                shutil.copy2(backup_tif, processed_tif)
                backup_tif.unlink(missing_ok=True)
            
            # Restore original tiles if backup exists
            if backup_tiles_dir.is_dir():
                if tiles_dir.exists():
                    shutil.rmtree(tiles_dir, ignore_errors=True)
                shutil.copytree(backup_tiles_dir, tiles_dir)
                shutil.rmtree(backup_tiles_dir, ignore_errors=True)
            elif processed_tif.is_file():
                # Regenerate tiles from original raster
                generate_tiles(
                    TileGenerationRequest(
                        dataset_id=dataset.id,
                        min_zoom=dataset.tile_min_zoom or 0,
                        max_zoom=dataset.tile_max_zoom or 18,
                    ),
                    db,
                )

            # Update metadata
            meta = dict(dataset.extracted_metadata or {})
            meta["background_removal"] = {
                "enabled": False,
                "color": request.color,
                "threshold": request.threshold,
                "edge_softness": request.edge_softness,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            dataset.extracted_metadata = meta
            try:
                db.save_dataset(dataset)
                db.commit()
            except RepositoryError as exc:
                db.rollback()
                raise _error(500, "DATABASE_ERROR", "Failed to update dataset metadata.", str(exc)) from exc

            return BackgroundRemovalResponse(
                data=BackgroundRemovalData(
                    dataset_id=dataset.id,
                    status="reset",
                    enabled=False,
                    color=request.color,
                    threshold=request.threshold,
                    edge_softness=request.edge_softness,
                    tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                    message="Background removal reset; original raster restored.",
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            )

    # 4. Apply action
    meta = dict(dataset.extracted_metadata or {})
    current_bg = meta.get("background_removal", {})

    # Check for identical duplicate request
    has_tiles = tiles_dir.is_dir() and any(tiles_dir.iterdir())
    if (
        current_bg.get("enabled")
        and current_bg.get("color") == request.color
        and current_bg.get("threshold") == request.threshold
        and current_bg.get("edge_softness") == request.edge_softness
        and processed_tif.is_file()
        and has_tiles
    ):
        return BackgroundRemovalResponse(
            data=BackgroundRemovalData(
                dataset_id=dataset.id,
                status="completed",
                enabled=True,
                color=request.color,
                threshold=request.threshold,
                edge_softness=request.edge_softness,
                tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                message="Background removal already applied with identical settings.",
                updated_at=current_bg.get("updated_at"),
            )
        )

    # Ensure dataset is in Web Mercator if georeferenced
    if not processed_tif.is_file():
        if dataset.georeferenced_path:
            process_raster(
                RasterProcessRequest(
                    dataset_id=dataset.id,
                    target_crs="EPSG:3857",
                    resampling="bilinear",
                ),
                db,
            )
        elif source_path.suffix.lower() in {".tif", ".tiff"}:
            shutil.copy2(source_path, processed_tif)
        else:
            raise _error(
                400,
                "GEOREFERENCE_REQUIRED",
                "Dataset must be georeferenced before applying background removal.",
                "Complete georeferencing for this layer first.",
                field="dataset_id",
            )

    with db.protect_operation("background_removal_apply"):
        # Create backups if not existing yet
        if not backup_tif.is_file() and processed_tif.is_file():
            shutil.copy2(processed_tif, backup_tif)
        if not backup_tiles_dir.is_dir() and tiles_dir.is_dir():
            shutil.copytree(tiles_dir, backup_tiles_dir)

        # Process the raster from backup_tif (to always apply from the clean original)
        base_source = backup_tif if backup_tif.is_file() else processed_tif
        try:
            process_raster_background_removal(
                input_path=base_source,
                output_path=processed_tif,
                target_color=target_rgb,
                threshold=request.threshold,
                edge_softness=request.edge_softness,
            )
        except Exception as exc:
            logger.exception("Failed to process raster background removal.", exc_info=exc)
            # Restore backup if failed
            if backup_tif.is_file():
                shutil.copy2(backup_tif, processed_tif)
            raise _error(
                500,
                "PROCESSING_FAILED",
                "Raster background removal processing failed.",
                str(exc),
                field="threshold",
            ) from exc

        rel_processed = (
            processed_tif.relative_to(BACKEND_DIRECTORY).as_posix()
            if processed_tif.is_relative_to(BACKEND_DIRECTORY)
            else processed_tif.as_posix()
        )
        dataset.processed_path = rel_processed
        dataset.process_status = "completed"
        try:
            db.save_dataset(dataset)
            db.commit()
        except RepositoryError:
            pass

        # Regenerate map tiles from the new transparent RGBA GeoTIFF
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
            logger.exception("Failed to regenerate tiles after background removal.", exc_info=exc)
            # Rollback to original backup
            if backup_tif.is_file():
                shutil.copy2(backup_tif, processed_tif)
            if backup_tiles_dir.is_dir() and tiles_dir.exists():
                shutil.rmtree(tiles_dir, ignore_errors=True)
                shutil.copytree(backup_tiles_dir, tiles_dir)
            raise _error(
                500,
                "TILE_GENERATION_FAILED",
                "Failed to regenerate map tiles for transparent raster.",
                str(exc),
                field="dataset_id",
            ) from exc

        # Generate thumbnail preview
        try:
            _, prev_url = generate_raster_preview(
                processed_tif,
                target_color=target_rgb,
                threshold=request.threshold,
                edge_softness=request.edge_softness,
                max_dimension=400,
            )
        except Exception:
            prev_url = None

        now_str = datetime.now(timezone.utc).isoformat()
        meta["background_removal"] = {
            "enabled": True,
            "color": request.color,
            "threshold": request.threshold,
            "edge_softness": request.edge_softness,
            "updated_at": now_str,
        }
        dataset.extracted_metadata = meta

        try:
            db.save_dataset(dataset)
            db.commit()
        except RepositoryError as exc:
            db.rollback()
            raise _error(500, "DATABASE_ERROR", "Failed to update dataset metadata.", str(exc)) from exc

        return BackgroundRemovalResponse(
            data=BackgroundRemovalData(
                dataset_id=dataset.id,
                status="completed",
                enabled=True,
                color=request.color,
                threshold=request.threshold,
                edge_softness=request.edge_softness,
                preview_data_url=prev_url,
                tile_url_template=f"/datasets/{dataset.id}/tiles/{{z}}/{{x}}/{{y}}.png",
                message="Background removal applied successfully.",
                updated_at=now_str,
            )
        )
