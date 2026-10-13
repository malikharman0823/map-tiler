from __future__ import annotations

import base64
import gc
import io
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
from rasterio.errors import RasterioError

logger = logging.getLogger(__name__)


def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    """Parse a hex color string like '#ffffff' or 'fff' into an RGB tuple (r, g, b)."""
    cleaned = hex_str.strip()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        raise ValueError(f"Invalid hex color string: {hex_str}")
    r = int(cleaned[0:2], 16)
    g = int(cleaned[2:4], 16)
    b = int(cleaned[4:6], 16)
    return (r, g, b)


def _normalize_to_uint8(band: np.ndarray, nodata_val: Any = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Normalize a 2D band to uint8 [0, 255] and return a nodata boolean mask if present."""
    nodata_mask = None
    if nodata_val is not None:
        if np.isnan(nodata_val):
            nodata_mask = np.isnan(band)
        else:
            nodata_mask = (band == nodata_val)

    if band.dtype == np.uint8:
        return band.copy(), nodata_mask

    if np.issubdtype(band.dtype, np.bool_):
        return (band.astype(np.uint8) * 255), nodata_mask

    if np.issubdtype(band.dtype, np.integer):
        info = np.iinfo(band.dtype)
        # Avoid division by zero
        denom = max(1, info.max - info.min)
        scaled = ((band.astype(np.float32) - info.min) * 255.0 / denom)
        scaled_uint8 = np.clip(scaled, 0, 255).astype(np.uint8)
        return scaled_uint8, nodata_mask

    # Floating point
    finite = np.nan_to_num(band.astype(np.float32), nan=0.0, posinf=255.0, neginf=0.0)
    b_min, b_max = finite.min(), finite.max()
    if b_max <= 1.0 and b_min >= 0.0:
        scaled_uint8 = np.clip(finite * 255.0, 0, 255).astype(np.uint8)
    elif b_max > b_min:
        scaled_uint8 = np.clip((finite - b_min) * 255.0 / (b_max - b_min), 0, 255).astype(np.uint8)
    else:
        scaled_uint8 = np.clip(finite, 0, 255).astype(np.uint8)

    return scaled_uint8, nodata_mask


def remove_background_array(
    bands: list[np.ndarray],
    target_color: tuple[int, int, int],
    threshold: float,
    edge_softness: float = 10.0,
    existing_alpha: np.ndarray | None = None,
    nodata_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Execute OpenCV background removal on multi-band raster data.
    
    Args:
        bands: List of 2D arrays (e.g. [gray] or [r, g, b] or [r, g, b, a]) in uint8.
        target_color: (R, G, B) background color in [0, 255].
        threshold: Distance tolerance [0, 255].
        edge_softness: Transition width [1, 100] for antialiasing.
        existing_alpha: Optional 2D uint8 array with prior alpha mask.
        nodata_mask: Optional 2D boolean mask where True indicates nodata.
        
    Returns:
        4-band RGBA array of shape (4, height, width) with dtype uint8.
    """
    count = len(bands)
    height, width = bands[0].shape
    t_r, t_g, t_b = target_color
    softness = max(1.0, float(edge_softness))
    thresh = max(0.0, float(threshold))

    if count == 1 or count == 2:
        gray = bands[0]
        # Target in grayscale luminance
        target_gray = 0.299 * t_r + 0.587 * t_g + 0.114 * t_b
        dist = np.abs(gray.astype(np.float32) - target_gray)
        # Replicate gray to RGB
        r = gray.copy()
        g = gray.copy()
        b = gray.copy()
        if count == 2 and existing_alpha is None:
            existing_alpha = bands[1]
    else:
        r = bands[0]
        g = bands[1]
        b = bands[2]
        if count >= 4 and existing_alpha is None:
            existing_alpha = bands[3]

        diff_r = r.astype(np.float32) - float(t_r)
        diff_g = g.astype(np.float32) - float(t_g)
        diff_b = b.astype(np.float32) - float(t_b)
        dist = np.sqrt((diff_r ** 2 + diff_g ** 2 + diff_b ** 2) / 3.0)

    # Compute alpha mask
    alpha = np.zeros((height, width), dtype=np.uint8)
    bg_mask = dist <= thresh
    fg_mask = dist >= (thresh + softness)
    trans_mask = ~bg_mask & ~fg_mask

    alpha[fg_mask] = 255
    if np.any(trans_mask):
        trans_alpha = 255.0 * (dist[trans_mask] - thresh) / softness
        alpha[trans_mask] = np.clip(trans_alpha, 0, 255).astype(np.uint8)

    # Defringe antialiased pixels: remove the target background color cast
    # from semi-transparent edge pixels to prevent white haloes on dark backgrounds.
    if np.any(trans_mask):
        norm_a = alpha[trans_mask].astype(np.float32) / 255.0
        # Prevent division by zero with small epsilon
        norm_a = np.maximum(norm_a, 0.05)
        r_f = np.clip((r[trans_mask].astype(np.float32) - (1.0 - norm_a) * t_r) / norm_a, 0, 255).astype(np.uint8)
        g_f = np.clip((g[trans_mask].astype(np.float32) - (1.0 - norm_a) * t_g) / norm_a, 0, 255).astype(np.uint8)
        b_f = np.clip((b[trans_mask].astype(np.float32) - (1.0 - norm_a) * t_b) / norm_a, 0, 255).astype(np.uint8)
        r[trans_mask] = r_f
        g[trans_mask] = g_f
        b[trans_mask] = b_f

    # Preserve existing alpha
    if existing_alpha is not None:
        alpha = np.minimum(alpha, existing_alpha)

    # Preserve nodata
    if nodata_mask is not None:
        alpha[nodata_mask] = 0

    return np.stack([r, g, b, alpha], axis=0)


def process_raster_background_removal(
    input_path: Path,
    output_path: Path,
    target_color: tuple[int, int, int],
    threshold: float,
    edge_softness: float = 10.0,
) -> dict[str, Any]:
    """Process a georeferenced raster file, removing the background and writing an RGBA GeoTIFF.
    
    Preserves original CRS, affine transform, dimensions, geographic bounds, and alignment.
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"Input raster file not found: {input_path}")

    temp_output: Path | None = None
    try:
        with rasterio.open(input_path) as src:
            src_crs = src.crs
            src_transform = src.transform
            src_width = src.width
            src_height = src.height
            src_count = src.count
            src_bounds = src.bounds
            src_nodata = src.nodata
            profile = src.profile.copy()

            # Identify if existing alpha channel is present
            has_existing_alpha = (
                src_count in {2, 4}
                and len(src.colorinterp) >= src_count
                and src.colorinterp[src_count - 1] == ColorInterp.alpha
            )

            # Determine whether to read full or chunked
            pixel_count = src_width * src_height
            use_chunking = pixel_count > 16_000_000

            output_profile = profile.copy()
            for key in ("photometric", "compress", "nodata", "blockxsize", "blockysize"):
                output_profile.pop(key, None)

            output_profile.update(
                driver="GTiff",
                count=4,
                dtype="uint8",
                nodata=None,
                crs=src_crs,
                transform=src_transform,
                width=src_width,
                height=src_height,
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate",
                photometric="RGB",
                BIGTIFF="IF_SAFER",
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            temp_output = output_path.with_name(f"{output_path.stem}.tmp.{output_path.suffix}")
            temp_output.unlink(missing_ok=True)

            with rasterio.open(temp_output, "w", **output_profile) as dst:
                dst.colorinterp = (
                    ColorInterp.red,
                    ColorInterp.green,
                    ColorInterp.blue,
                    ColorInterp.alpha,
                )

                if not use_chunking:
                    raw_data = src.read()
                    bands_uint8 = []
                    combined_nodata_mask = None
                    for b_idx in range(raw_data.shape[0]):
                        b_u8, n_mask = _normalize_to_uint8(raw_data[b_idx], src_nodata)
                        bands_uint8.append(b_u8)
                        if n_mask is not None:
                            combined_nodata_mask = (
                                n_mask if combined_nodata_mask is None else (combined_nodata_mask | n_mask)
                            )

                    existing_alpha = bands_uint8[src_count - 1] if has_existing_alpha else None
                    rgba = remove_background_array(
                        bands_uint8,
                        target_color=target_color,
                        threshold=threshold,
                        edge_softness=edge_softness,
                        existing_alpha=existing_alpha,
                        nodata_mask=combined_nodata_mask,
                    )
                    dst.write(rgba)
                else:
                    # Windowed processing for large files
                    for _, window in src.block_windows(1):
                        window_data = src.read(window=window)
                        bands_uint8 = []
                        combined_nodata_mask = None
                        for b_idx in range(window_data.shape[0]):
                            b_u8, n_mask = _normalize_to_uint8(window_data[b_idx], src_nodata)
                            bands_uint8.append(b_u8)
                            if n_mask is not None:
                                combined_nodata_mask = (
                                    n_mask if combined_nodata_mask is None else (combined_nodata_mask | n_mask)
                                )

                        existing_alpha = bands_uint8[src_count - 1] if has_existing_alpha else None
                        rgba_window = remove_background_array(
                            bands_uint8,
                            target_color=target_color,
                            threshold=threshold,
                            edge_softness=edge_softness,
                            existing_alpha=existing_alpha,
                            nodata_mask=combined_nodata_mask,
                        )
                        dst.write(rgba_window, window=window)

        # Atomically replace destination
        temp_output.replace(output_path)
        gc.collect()

        # Validate the output
        with rasterio.open(output_path) as verify_src:
            if verify_src.count != 4 or verify_src.width != src_width or verify_src.height != src_height:
                raise ValueError("Generated RGBA raster failed validation dimensions check.")

        return {
            "width": src_width,
            "height": src_height,
            "crs": src_crs.to_string() if src_crs else None,
            "bounds": [src_bounds.left, src_bounds.bottom, src_bounds.right, src_bounds.top],
            "bands": 4,
        }

    except Exception as exc:
        logger.exception("Failed during raster background removal.", exc_info=exc)
        if temp_output is not None and temp_output.exists():
            temp_output.unlink(missing_ok=True)
        raise


def generate_raster_preview(
    input_path: Path,
    target_color: tuple[int, int, int],
    threshold: float,
    edge_softness: float = 10.0,
    max_dimension: int = 600,
) -> tuple[str, str]:
    """Generate base64 data URLs for both the original preview and the background-removed preview.
    
    Downsamples the input image so computation is instant (< 50ms) and intermediate memory is small.
    Returns:
        (original_data_url, preview_data_url)
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"Source file not found: {input_path}")

    # Use PIL or rasterio to read preview image
    try:
        with Image.open(input_path) as pil_img:
            pil_img.draft("RGB", (max_dimension, max_dimension))
            pil_img.thumbnail((max_dimension, max_dimension), Image.Resampling.BILINEAR)
            converted = pil_img.convert("RGBA")
            img_np = np.array(converted)
    except Exception:
        # Fallback to rasterio for specialized geospatial formats
        with rasterio.open(input_path) as src:
            scale = min(max_dimension / max(src.width, src.height), 1.0)
            out_w = max(1, int(src.width * scale))
            out_h = max(1, int(src.height * scale))
            from rasterio.enums import Resampling
            data = src.read(
                out_shape=(src.count, out_h, out_w),
                resampling=Resampling.bilinear,
            )
            bands_u8 = [_normalize_to_uint8(data[i], src.nodata)[0] for i in range(data.shape[0])]
            if len(bands_u8) == 1:
                img_np = cv2.cvtColor(bands_u8[0], cv2.COLOR_GRAY2RGBA)
            elif len(bands_u8) >= 4:
                img_np = np.dstack([bands_u8[0], bands_u8[1], bands_u8[2], bands_u8[3]])
            else:
                alpha = np.full(bands_u8[0].shape, 255, dtype=np.uint8)
                img_np = np.dstack([bands_u8[0], bands_u8[1], bands_u8[2], alpha])

    h, w, c = img_np.shape
    r = img_np[:, :, 0]
    g = img_np[:, :, 1]
    b = img_np[:, :, 2]
    existing_alpha = img_np[:, :, 3] if c >= 4 else None

    # Original thumbnail base64
    orig_buf = io.BytesIO()
    Image.fromarray(img_np, mode="RGBA").save(orig_buf, format="PNG")
    original_data_url = f"data:image/png;base64,{base64.b64encode(orig_buf.getvalue()).decode('ascii')}"

    # Processed thumbnail
    rgba_4ch = remove_background_array(
        [r, g, b],
        target_color=target_color,
        threshold=threshold,
        edge_softness=edge_softness,
        existing_alpha=existing_alpha,
    )
    # Transpose to (H, W, 4) for PIL
    processed_np = np.transpose(rgba_4ch, (1, 2, 0))

    prev_buf = io.BytesIO()
    Image.fromarray(processed_np, mode="RGBA").save(prev_buf, format="PNG")
    preview_data_url = f"data:image/png;base64,{base64.b64encode(prev_buf.getvalue()).decode('ascii')}"

    return original_data_url, preview_data_url
