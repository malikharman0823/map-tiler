from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

from functions.raster_transform.request import CoordinatePoint, RasterCorners


RESAMPLING_MAP = {
    "nearest": Resampling.nearest,
    "bilinear": Resampling.bilinear,
    "cubic": Resampling.cubic,
}


def polygon_is_simple_and_convex(corners: RasterCorners) -> bool:
    """Validate that the 4-corner quadrilateral is non-degenerate and convex."""
    pts = [
        (corners.top_left.longitude, corners.top_left.latitude),
        (corners.top_right.longitude, corners.top_right.latitude),
        (corners.bottom_right.longitude, corners.bottom_right.latitude),
        (corners.bottom_left.longitude, corners.bottom_left.latitude),
    ]

    # Check distinct points
    for i in range(4):
        for j in range(i + 1, 4):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                return False

    # Check cross products of consecutive edges for consistent sign (convexity)
    cross_signs = []
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        p3 = pts[(i + 2) % 4]
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        cp = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cp) < 1e-12:
            return False  # Collinear edge
        cross_signs.append(1 if cp > 0 else -1)

    return all(s == cross_signs[0] for s in cross_signs)


from schemas.error import ApplicationError


def extract_raster_corners_wgs84(
    raster_path: Path,
    fallback_bounds: list[float] | None = None,
) -> tuple[RasterCorners, list[float], int, int]:
    """Read georeferenced raster corners in WGS84 (EPSG:4326)."""
    with rasterio.open(raster_path) as src:
        width = src.width
        height = src.height

        if src.crs is None:
            if fallback_bounds and len(fallback_bounds) == 4:
                west, south, east, north = [float(v) for v in fallback_bounds]
                if -180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90:
                    corners = RasterCorners(
                        top_left=CoordinatePoint(longitude=west, latitude=north),
                        top_right=CoordinatePoint(longitude=east, latitude=north),
                        bottom_right=CoordinatePoint(longitude=east, latitude=south),
                        bottom_left=CoordinatePoint(longitude=west, latitude=south),
                    )
                    return corners, [west, south, east, north], width, height
            raise ApplicationError(
                status_code=400,
                code="RASTER_NOT_GEOREFERENCED",
                message="The raster is not georeferenced.",
                details="Georeference the dataset before applying geographic transformations.",
                field="dataset_id",
            )

        src_crs = src.crs

        # Pixel corners
        # Top-left: (0, 0)
        # Top-right: (width, 0)
        # Bottom-right: (width, height)
        # Bottom-left: (0, height)
        tl_x, tl_y = src.transform @ (0, 0)
        tr_x, tr_y = src.transform @ (width, 0)
        br_x, br_y = src.transform @ (width, height)
        bl_x, bl_y = src.transform @ (0, height)

        xs = [tl_x, tr_x, br_x, bl_x]
        ys = [tl_y, tr_y, br_y, bl_y]

        wgs84 = CRS.from_epsg(4326)
        if src_crs != wgs84:
            from rasterio.warp import transform
            lngs, lats = transform(src_crs, wgs84, xs, ys)
        else:
            lngs, lats = xs, ys

        valid_lngs = all(-180 <= float(l) <= 180 for l in lngs)
        valid_lats = all(-90 <= float(l) <= 90 for l in lats)
        if not (valid_lngs and valid_lats):
            if fallback_bounds and len(fallback_bounds) == 4:
                west, south, east, north = [float(v) for v in fallback_bounds]
                corners = RasterCorners(
                    top_left=CoordinatePoint(longitude=west, latitude=north),
                    top_right=CoordinatePoint(longitude=east, latitude=north),
                    bottom_right=CoordinatePoint(longitude=east, latitude=south),
                    bottom_left=CoordinatePoint(longitude=west, latitude=south),
                )
                return corners, [west, south, east, north], width, height
            raise ApplicationError(
                status_code=400,
                code="INVALID_RASTER_COORDINATES",
                message="Raster transformed coordinates are outside valid geographic range.",
                details="Ensure the raster CRS is properly configured.",
                field="dataset_id",
            )

        corners = RasterCorners(
            top_left=CoordinatePoint(longitude=float(lngs[0]), latitude=float(lats[0])),
            top_right=CoordinatePoint(longitude=float(lngs[1]), latitude=float(lats[1])),
            bottom_right=CoordinatePoint(longitude=float(lngs[2]), latitude=float(lats[2])),
            bottom_left=CoordinatePoint(longitude=float(lngs[3]), latitude=float(lats[3])),
        )

        min_lng = min(lngs)
        max_lng = max(lngs)
        min_lat = min(lats)
        max_lat = max(lats)
        bounds = [float(min_lng), float(min_lat), float(max_lng), float(max_lat)]
        return corners, bounds, width, height


def warp_raster_to_corners(
    input_path: Path,
    output_path: Path,
    corners: RasterCorners,
    target_crs_str: str = "EPSG:3857",
    resampling_str: str = "bilinear",
) -> dict[str, Any]:
    """Warp source raster to the designated 4 target corner coordinates."""
    resampling = RESAMPLING_MAP.get(resampling_str, Resampling.bilinear)
    target_crs = CRS.from_user_input(target_crs_str)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_gcp = output_path.with_name(f"{output_path.stem}.gcp_tmp.tif")
    temp_output = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")

    try:
        with rasterio.open(input_path) as src:
            width = src.width
            height = src.height
            count = src.count
            profile = src.profile.copy()
            data = src.read()

        # Define 4 corner GCPs from pixel coordinates to target coordinates in EPSG:4326
        gcps = [
            GroundControlPoint(row=0.0, col=0.0, x=corners.top_left.longitude, y=corners.top_left.latitude),
            GroundControlPoint(row=0.0, col=float(width), x=corners.top_right.longitude, y=corners.top_right.latitude),
            GroundControlPoint(row=float(height), col=float(width), x=corners.bottom_right.longitude, y=corners.bottom_right.latitude),
            GroundControlPoint(row=float(height), col=0.0, x=corners.bottom_left.longitude, y=corners.bottom_left.latitude),
        ]
        gcp_crs = CRS.from_epsg(4326)

        gcp_profile = profile.copy()
        gcp_profile.pop("transform", None)
        gcp_profile.pop("crs", None)
        for k in ("blockxsize", "blockysize", "compress", "photometric"):
            gcp_profile.pop(k, None)

        temp_gcp.unlink(missing_ok=True)
        with rasterio.open(temp_gcp, "w", **gcp_profile, crs=gcp_crs, gcps=gcps) as gcp_dst:
            gcp_dst.write(data)

        with rasterio.open(temp_gcp) as gcp_src:
            dst_transform, dst_w, dst_h = calculate_default_transform(
                gcp_src.gcps[1],
                target_crs,
                gcp_src.width,
                gcp_src.height,
                gcps=gcp_src.gcps[0],
            )

            if dst_w <= 0 or dst_h <= 0:
                raise ValueError(f"Invalid calculated destination dimensions: {dst_w}x{dst_h}")

            out_profile = profile.copy()
            for k in ("blockxsize", "blockysize", "compress", "photometric", "transform", "crs"):
                out_profile.pop(k, None)

            out_profile.update(
                driver="GTiff",
                crs=target_crs,
                transform=dst_transform,
                width=dst_w,
                height=dst_h,
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate",
                BIGTIFF="IF_SAFER",
            )

            temp_output.unlink(missing_ok=True)
            with rasterio.open(temp_output, "w", **out_profile) as dst:
                for band_idx in range(1, count + 1):
                    reproject(
                        source=rasterio.band(gcp_src, band_idx),
                        destination=rasterio.band(dst, band_idx),
                        src_crs=gcp_src.gcps[1],
                        src_gcps=gcp_src.gcps[0],
                        dst_transform=dst_transform,
                        dst_crs=target_crs,
                        resampling=resampling,
                        warp_mem_limit=64,
                    )

            temp_output.replace(output_path)
    finally:
        temp_gcp.unlink(missing_ok=True)
        temp_output.unlink(missing_ok=True)

    # Calculate final WGS84 bounds of output
    with rasterio.open(output_path) as final_src:
        out_bounds = transform_bounds(final_src.crs, CRS.from_epsg(4326), *final_src.bounds)
        return {
            "width": final_src.width,
            "height": final_src.height,
            "bounds": list(out_bounds),
            "crs": final_src.crs.to_string(),
        }
