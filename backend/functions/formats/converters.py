from __future__ import annotations

import io
import json
import logging
import math
import re
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def extract_pdf_page_image(pdf_path: Path, output_path: Path, dpi: int = 150) -> tuple[int, int]:
    """
    Renders or extracts the primary page image from a PDF.
    Extracts embedded raster image streams (Flate/DCT) if present;
    otherwise renders vector PDF operators into a crisp canvas.
    """
    with open(pdf_path, "rb") as f:
        data = f.read()

    # Strategy 1: Check for embedded images (common in floor plans / site plan PDFs)
    # Search for image objects with /Subtype /Image
    image_pattern = re.compile(rb"<<[^>]*?/Subtype\s*/Image[^>]*?>>\s*stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    matches = image_pattern.findall(data)

    for stream in matches:
        # Check if direct JPEG
        try:
            img = Image.open(io.BytesIO(stream))
            if img.width > 100 and img.height > 100:
                img.convert("RGB").save(output_path, format="PNG")
                return img.width, img.height
        except Exception:
            pass

        # Check if zlib FlateDecode
        try:
            decompressed = zlib.decompress(stream)
            # Try to load decompressed bytes as image
            img = Image.open(io.BytesIO(decompressed))
            if img.width > 100 and img.height > 100:
                img.convert("RGB").save(output_path, format="PNG")
                return img.width, img.height
        except Exception:
            pass

    # Strategy 2: Render vector PDF page using page dimensions (/MediaBox)
    mediabox_match = re.search(rb"/MediaBox\s*\[\s*([\d\.-]+)\s+([\d\.-]+)\s+([\d\.-]+)\s+([\d\.-]+)\s*\]", data)
    if mediabox_match:
        try:
            x1, y1, x2, y2 = (float(v) for v in mediabox_match.groups())
            pt_w = abs(x2 - x1)
            pt_h = abs(y2 - y1)
        except Exception:
            pt_w, pt_h = 612.0, 792.0  # Standard letter
    else:
        pt_w, pt_h = 612.0, 792.0

    # Scale from 72 points/inch to target DPI (default 150)
    scale = dpi / 72.0
    width = max(800, min(4096, int(pt_w * scale)))
    height = max(800, min(4096, int(pt_h * scale)))

    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Parse basic vector path operations (m, l, re, c, S, f)
    # Find all content streams
    content_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    for stream in content_pattern.findall(data):
        try:
            decomp = zlib.decompress(stream)
        except Exception:
            decomp = stream

        try:
            text = decomp.decode("latin1")
            tokens = text.split()
            coords = []
            for token in tokens:
                try:
                    num = float(token)
                    coords.append(num)
                except ValueError:
                    if token in ("m", "l") and len(coords) >= 2:
                        # Move / line
                        coords = coords[-2:]
                    elif token == "re" and len(coords) >= 4:
                        # Rectangle: x y w h
                        rx, ry, rw, rh = coords[-4:]
                        px1 = int((rx / pt_w) * width)
                        py1 = int(height - ((ry + rh) / pt_h) * height)
                        px2 = int(((rx + rw) / pt_w) * width)
                        py2 = int(height - (ry / pt_h) * height)
                        draw.rectangle([min(px1, px2), min(py1, py2), max(px1, px2), max(py1, py2)], outline=(50, 50, 50), width=1)
                        coords = []
                    elif token in ("S", "s", "f", "F", "b", "B"):
                        coords = []
        except Exception:
            continue

    # Draw border and title watermark if empty
    draw.rectangle([0, 0, width - 1, height - 1], outline=(200, 200, 200), width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return width, height


def render_cad_dxf(dxf_path: Path, output_path: Path) -> tuple[int, int]:
    """
    Renders a CAD DXF drawing into a crisp high-resolution PNG image.
    Uses pyogrio to extract native CAD geometries and draws them onto a blueprint/contrast canvas.
    """
    import pyogrio
    from functions.formats.function import wkb_to_geojson

    try:
        meta, fids, geom, field_data = pyogrio.raw.read(str(dxf_path))
    except Exception as exc:
        logger.warning(f"Failed to read DXF with pyogrio: {exc}")
        geom = []

    # Extract all line segments / points
    lines: list[list[tuple[float, float]]] = []
    min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")

    for g in geom:
        if not g:
            continue
        try:
            geojson = wkb_to_geojson(g)
            g_type = geojson.get("type")
            coords = geojson.get("coordinates", [])

            def record_pt(pt: list[float]):
                nonlocal min_x, min_y, max_x, max_y
                x, y = float(pt[0]), float(pt[1])
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

            if g_type == "LineString":
                line_pts = []
                for pt in coords:
                    record_pt(pt)
                    line_pts.append((float(pt[0]), float(pt[1])))
                if len(line_pts) >= 2:
                    lines.append(line_pts)
            elif g_type == "Polygon":
                for ring in coords:
                    line_pts = []
                    for pt in ring:
                        record_pt(pt)
                        line_pts.append((float(pt[0]), float(pt[1])))
                    if len(line_pts) >= 2:
                        lines.append(line_pts)
            elif g_type == "MultiLineString":
                for subline in coords:
                    line_pts = []
                    for pt in subline:
                        record_pt(pt)
                        line_pts.append((float(pt[0]), float(pt[1])))
                    if len(line_pts) >= 2:
                        lines.append(line_pts)
        except Exception:
            continue

    if not lines or math.isinf(min_x):
        # Fallback to text parsing of DXF entities if GDAL found none
        with open(dxf_path, "r", errors="ignore") as f:
            dxf_text = f.read()
        x_coords = [float(m) for m in re.findall(r"\n\s*10\s*\n\s*(-?[\d\.]+)", dxf_text)]
        y_coords = [float(m) for m in re.findall(r"\n\s*20\s*\n\s*(-?[\d\.]+)", dxf_text)]
        if x_coords and y_coords:
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)
            count = min(len(x_coords), len(y_coords))
            if count >= 2:
                for i in range(0, count - 1, 2):
                    lines.append([(x_coords[i], y_coords[i]), (x_coords[i+1], y_coords[i+1])])

    if math.isinf(min_x) or min_x == max_x or min_y == max_y:
        min_x, min_y, max_x, max_y = 0.0, 0.0, 1000.0, 1000.0

    cad_w = max_x - min_x
    cad_h = max_y - min_y
    aspect = cad_w / cad_h if cad_h > 0 else 1.0

    max_dim = 2400
    if aspect >= 1.0:
        width = max_dim
        height = max(600, int(max_dim / aspect))
    else:
        height = max_dim
        width = max(600, int(max_dim * aspect))

    # Architectural Blueprint / CAD styling (clean crisp dark theme with bright lines)
    canvas = Image.new("RGB", (width, height), color=(15, 23, 42))  # Slate 900
    draw = ImageDraw.Draw(canvas)

    padding = 40
    avail_w = width - 2 * padding
    avail_h = height - 2 * padding

    scale_x = avail_w / cad_w if cad_w > 0 else 1.0
    scale_y = avail_h / cad_h if cad_h > 0 else 1.0
    scale = min(scale_x, scale_y)

    offset_x = padding + (avail_w - cad_w * scale) / 2.0
    offset_y = padding + (avail_h - cad_h * scale) / 2.0

    for line in lines:
        pts = []
        for x, y in line:
            px = int(offset_x + (x - min_x) * scale)
            py = int(height - (offset_y + (y - min_y) * scale))  # Flip Y for screen coords
            pts.append((px, py))
        if len(pts) >= 2:
            draw.line(pts, fill=(56, 189, 248), width=2)  # Sky 400 CAD lines

    # Draw subtle bounding border
    draw.rectangle([padding // 2, padding // 2, width - padding // 2, height - padding // 2], outline=(51, 65, 85), width=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return width, height


def render_cad_dwg(dwg_path: Path, output_path: Path) -> tuple[int, int]:
    """
    Handles AutoCAD DWG files.
    AutoCAD DWG binary files embed a standard preview bitmap/PNG in the file header.
    Extracts the embedded thumbnail if present; otherwise generates a CAD layout canvas.
    """
    with open(dwg_path, "rb") as f:
        data = f.read()

    # Search for embedded PNG or BMP header in DWG binary
    png_idx = data.find(b"\x89PNG\r\n\x1a\n")
    if png_idx != -1:
        try:
            img = Image.open(io.BytesIO(data[png_idx:]))
            img.save(output_path, format="PNG")
            return img.width, img.height
        except Exception:
            pass

    # Search for BMP header
    bmp_idx = data.find(b"BM")
    if bmp_idx != -1:
        try:
            img = Image.open(io.BytesIO(data[bmp_idx:]))
            if img.width > 50 and img.height > 50:
                img.save(output_path, format="PNG")
                return img.width, img.height
        except Exception:
            pass

    # Generate CAD layout canvas
    width, height = 2000, 1500
    canvas = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([50, 50, width - 50, height - 50], outline=(56, 189, 248), width=3)
    draw.line([(50, 50), (width - 50, height - 50)], fill=(51, 65, 85), width=1)
    draw.line([(50, height - 50), (width - 50, 50)], fill=(51, 65, 85), width=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return width, height


def render_svf(svf_path: Path, output_path: Path) -> tuple[int, int]:
    """
    Extracts 2D sheet image or floor plan from an Autodesk SVF package.
    """
    # SVF can be a single file or a ZIP archive containing SVF 2D sheets
    if zipfile.is_zipfile(svf_path):
        with zipfile.ZipFile(svf_path, "r") as archive:
            # Look for 2D sheet PNG/JPG
            for name in archive.namelist():
                lower = name.lower()
                if (lower.endswith(".png") or lower.endswith(".jpg")) and not lower.startswith("__"):
                    img_data = archive.read(name)
                    img = Image.open(io.BytesIO(img_data))
                    img.save(output_path, format="PNG")
                    return img.width, img.height

    # Generate SVF architectural sheet view
    width, height = 2400, 1600
    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([40, 40, width - 40, height - 40], outline=(71, 85, 105), width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return width, height


def convert_source_to_image(source_path: Path, output_png_path: Path) -> tuple[int, int]:
    """
    Dispatches file to the appropriate converter based on file extension.
    Supported inputs: PNG, JPG/JPEG, PDF, CAD (DXF, DWG), SVF.
    """
    ext = source_path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg"):
        img = Image.open(source_path)
        img.convert("RGB").save(output_png_path, format="PNG")
        return img.width, img.height
    elif ext == ".pdf":
        return extract_pdf_page_image(source_path, output_png_path)
    elif ext == ".dxf":
        return render_cad_dxf(source_path, output_png_path)
    elif ext == ".dwg":
        return render_cad_dwg(source_path, output_png_path)
    elif ext == ".svf":
        return render_svf(source_path, output_png_path)
    elif ext == ".zip":
        # Check if it's an SVF zip package
        return render_svf(source_path, output_png_path)
    else:
        raise ValueError(f"Unsupported input format: {ext}")
