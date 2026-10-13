from __future__ import annotations

import html
import json
import logging
import math
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import UUID

import mercantile
import rasterio
from fastapi.responses import FileResponse
from rasterio.errors import RasterioError
from rasterio.warp import transform_bounds
from starlette.background import BackgroundTask

from config import settings
from storage.session import SessionRepository
from functions.formats.function import MBTilesInfo, inspect_mbtiles
from schemas.error import ApplicationError


logger = logging.getLogger(__name__)
BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
ATTRIBUTION = (
    '<a href="https://www.maptiler.com/engine/">'
    "Rendered with MapTiler Engine</a>"
)
PROJECT_DOCUMENT_VERSION = 1
RASTER_SOURCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _error(status: int, code: str, message: str, details: str) -> ApplicationError:
    return ApplicationError(
        status_code=status,
        code=code,
        message=message,
        details=details,
    )


def _safe_stem(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return normalized[:80] or "map_project"


def _source_asset(dataset: Any) -> tuple[Path, str] | None:
    source = _managed_path(dataset.storage_path)
    if not source.is_file() or source.suffix.lower() not in RASTER_SOURCE_EXTENSIONS:
        return None
    filename = f"{_safe_stem(source.stem)}{source.suffix.lower()}"
    return source, f"assets/source/{filename}"


def _project_document(
    *,
    dataset: Any,
    project: Any,
    control_points: list[Any],
    icon_points: list[Any],
    source_asset_path: str | None,
) -> dict[str, Any]:
    return {
        "format": "mapstudio-folder",
        "version": PROJECT_DOCUMENT_VERSION,
        "project": {
            "name": project.name,
            "configuration": project.configuration,
        },
        "dataset": {
            "filename": dataset.filename,
            "content_type": dataset.content_type,
            "source_asset": source_asset_path,
        },
        "control_points": [
            {
                "image_x": point.image_x,
                "image_y": point.image_y,
                "longitude": point.longitude,
                "latitude": point.latitude,
            }
            for point in control_points
        ],
        "icon_points": [
            {
                "icon_key": point.icon_key,
                "description": point.description,
                "longitude": point.longitude,
                "latitude": point.latitude,
            }
            for point in icon_points
        ],
    }


def _managed_path(stored_path: str) -> Path:
    stored = Path(stored_path)
    candidate = stored.resolve() if stored.is_absolute() else (BACKEND_DIRECTORY / stored_path).resolve()
    sessions_root = Path(settings.session_storage_dir).resolve()
    is_safe = (
        candidate.is_relative_to(BACKEND_DIRECTORY.resolve())
        or candidate.is_relative_to(sessions_root)
        or candidate.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or (candidate.exists() and any(p in ("sessions", "datasets") for p in candidate.parts))
    )
    if not is_safe:
        raise _error(
            500,
            "INVALID_MANAGED_PATH",
            "A managed project file path is invalid.",
            "The stored path resolves outside backend-managed storage.",
        )
    return candidate


def _temporary_response(
    path: Path,
    *,
    filename: str,
    temporary_directory: Path,
) -> FileResponse:
    return FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(shutil.rmtree, temporary_directory, True),
    )


def _validate_bounds(values: Any) -> tuple[float, float, float, float] | None:
    if isinstance(values, dict):
        values = [
            values.get("min_longitude", values.get("min_x")),
            values.get("min_latitude", values.get("min_y")),
            values.get("max_longitude", values.get("max_x")),
            values.get("max_latitude", values.get("max_y")),
        ]
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    try:
        west, south, east, north = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        return None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return None
    return west, south, east, north


def _dataset_bounds(dataset: Any) -> tuple[float, float, float, float]:
    checked_paths: set[Path] = set()
    for stored_path in (dataset.processed_path, dataset.georeferenced_path):
        if not stored_path:
            continue
        path = _managed_path(stored_path)
        if path in checked_paths or not path.is_file():
            continue
        checked_paths.add(path)
        try:
            with rasterio.open(path) as source:
                if source.crs is None:
                    continue
                bounds = transform_bounds(
                    source.crs,
                    "EPSG:4326",
                    *source.bounds,
                    densify_pts=21,
                )
        except (RasterioError, OSError, TypeError, ValueError):
            continue
        validated = _validate_bounds(bounds)
        if validated is not None:
            return validated

    metadata = dataset.extracted_metadata or {}
    validated = _validate_bounds(metadata.get("bounds"))
    if validated is not None:
        return validated
    raise _error(
        409,
        "BOUNDS_NOT_AVAILABLE",
        "Geographic bounds are not available for export.",
        "Process or georeference the raster before exporting the tile package.",
    )


def _raster_mbtiles(dataset: Any) -> tuple[Path, MBTilesInfo] | None:
    metadata = dataset.extracted_metadata or {}
    if str(metadata.get("format") or "").lower() != "mbtiles":
        return None
    archive_path = _managed_path(dataset.storage_path)
    if not archive_path.is_file():
        raise _error(
            404,
            "TILE_SOURCE_NOT_FOUND",
            "The imported tile archive was not found.",
            "Re-import the raster MBTiles file before exporting.",
        )
    info = inspect_mbtiles(archive_path)
    if info.format != "png":
        raise _error(
            409,
            "UNSUPPORTED_TILE_FORMAT",
            "The imported tile archive cannot be exported as a PNG folder.",
            "Only raster MBTiles whose tile format is PNG can use this export.",
        )
    return archive_path, info


def _mbtiles_bounds(
    archive_path: Path,
    info: MBTilesInfo,
) -> tuple[float, float, float, float]:
    explicit = _validate_bounds(info.bounds)
    if explicit is not None:
        return explicit

    zoom = info.max_zoom
    limit = 1 << zoom
    boxes: list[Any] = []
    try:
        uri = f"file:{archive_path.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            rows = connection.execute(
                "SELECT tile_column, tile_row FROM tiles WHERE zoom_level = ?",
                (zoom,),
            )
            for column, tms_row in rows:
                column = int(column)
                tms_row = int(tms_row)
                if not (0 <= column < limit and 0 <= tms_row < limit):
                    raise ValueError("Tile coordinates are outside the zoom grid.")
                xyz_row = limit - 1 - tms_row
                boxes.append(mercantile.bounds(column, xyz_row, zoom))
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise _error(
            400,
            "INVALID_MBTILES",
            "The imported MBTiles archive is invalid.",
            "The archive tile coordinates could not be read.",
        ) from exc
    if not boxes:
        raise _error(
            409,
            "BOUNDS_NOT_AVAILABLE",
            "Geographic bounds are not available for export.",
            "The highest MBTiles zoom level contains no readable tiles.",
        )
    bounds = (
        min(box.west for box in boxes),
        min(box.south for box in boxes),
        max(box.east for box in boxes),
        max(box.north for box in boxes),
    )
    validated = _validate_bounds(bounds)
    if validated is None:
        raise _error(
            409,
            "BOUNDS_NOT_AVAILABLE",
            "Geographic bounds are not available for export.",
            "The imported MBTiles tile extent is invalid.",
        )
    return validated


def _write_mbtiles_pngs(archive: zipfile.ZipFile, archive_path: Path) -> None:
    try:
        uri = f"file:{archive_path.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            rows = connection.execute(
                """
                SELECT zoom_level, tile_column, tile_row, tile_data
                FROM tiles
                ORDER BY zoom_level, tile_column, tile_row DESC
                """
            )
            written = 0
            for zoom, column, tms_row, tile_data in rows:
                zoom = int(zoom)
                column = int(column)
                tms_row = int(tms_row)
                limit = 1 << zoom
                if zoom < 0 or zoom > 30 or not (0 <= column < limit and 0 <= tms_row < limit):
                    raise ValueError("Tile coordinates are outside the zoom grid.")
                xyz_row = limit - 1 - tms_row
                archive.writestr(
                    f"{zoom}/{column}/{xyz_row}.png",
                    bytes(tile_data),
                    compress_type=zipfile.ZIP_STORED,
                )
                written += 1
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise _error(
            400,
            "INVALID_MBTILES",
            "The imported MBTiles archive is invalid.",
            "The PNG tiles could not be extracted from the archive.",
        ) from exc
    if written == 0:
        raise _error(
            409,
            "TILES_NOT_AVAILABLE",
            "The imported MBTiles archive contains no PNG tiles.",
            "Import a non-empty raster PNG MBTiles archive before exporting.",
        )


def _tile_files(
    dataset: Any,
) -> tuple[Path, list[tuple[Path, str]], int, int]:
    if dataset.tile_status != "completed" or not dataset.tile_path:
        raise _error(
            409,
            "TILES_NOT_AVAILABLE",
            "Generated PNG tiles are not available for export.",
            "Complete raster processing and tile generation before exporting.",
        )
    if dataset.tile_min_zoom is None or dataset.tile_max_zoom is None:
        raise _error(
            409,
            "TILES_NOT_AVAILABLE",
            "The generated tile zoom range is unavailable.",
            "Regenerate the PNG tiles before exporting.",
        )

    min_zoom = int(dataset.tile_min_zoom)
    max_zoom = int(dataset.tile_max_zoom)
    if min_zoom < 0 or max_zoom < min_zoom or max_zoom > 22:
        raise _error(
            409,
            "TILES_NOT_AVAILABLE",
            "The generated tile zoom range is invalid.",
            "Regenerate the PNG tiles before exporting.",
        )

    tile_root = _managed_path(dataset.tile_path)
    if not tile_root.is_dir():
        raise _error(
            404,
            "TILE_SOURCE_NOT_FOUND",
            "The generated tile directory was not found.",
            "Regenerate the PNG tiles before exporting.",
        )

    tiles: list[tuple[Path, str]] = []
    zooms: set[int] = set()
    for zoom_directory in tile_root.iterdir():
        if (
            zoom_directory.is_symlink()
            or not zoom_directory.is_dir()
            or not zoom_directory.name.isdecimal()
        ):
            continue
        zoom = int(zoom_directory.name)
        if zoom_directory.name != str(zoom) or not min_zoom <= zoom <= max_zoom:
            continue
        for column_directory in zoom_directory.iterdir():
            if (
                column_directory.is_symlink()
                or not column_directory.is_dir()
                or not column_directory.name.isdecimal()
            ):
                continue
            column = int(column_directory.name)
            if column_directory.name != str(column):
                continue
            for tile_path in column_directory.iterdir():
                if (
                    tile_path.is_symlink()
                    or not tile_path.is_file()
                    or tile_path.suffix.lower() != ".png"
                    or not tile_path.stem.isdecimal()
                ):
                    continue
                row = int(tile_path.stem)
                if tile_path.stem != str(row):
                    continue
                tiles.append((tile_path, f"{zoom}/{column}/{row}.png"))
                zooms.add(zoom)

    expected_zooms = set(range(min_zoom, max_zoom + 1))
    if not tiles or zooms != expected_zooms:
        raise _error(
            409,
            "TILES_NOT_AVAILABLE",
            "The generated PNG tile set is empty or incomplete.",
            "Regenerate every configured zoom level before exporting.",
        )
    tiles.sort(key=lambda item: tuple(int(part.split(".")[0]) for part in item[1].split("/")))
    return tile_root, tiles, min_zoom, max_zoom


def _safe_json(value: Any, *, indent: int | None = None) -> str:
    return (
        json.dumps(value, ensure_ascii=False, indent=indent)
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
    )


def _viewer_files(
    *,
    name: str,
    bounds: tuple[float, float, float, float],
    min_zoom: int,
    max_zoom: int,
) -> dict[str, str]:
    west, south, east, north = bounds
    center_longitude = (west + east) / 2
    center_latitude = (south + north) / 2
    viewer_zoom = min(min_zoom + 1, max_zoom)
    escaped_title = html.escape(name, quote=True)
    data = {
        "name": name,
        "version": "1.0.0",
        "description": "",
        "type": "overlay",
        "format": "png",
        "minzoom": str(min_zoom),
        "maxzoom": str(max_zoom),
        "bounds": f"{west:.8f},{south:.8f},{east:.8f},{north:.8f}",
        "scale": "1.000000",
        "profile": "mercator",
    }

    index_html = f"""<!DOCTYPE html>
<html>
  <head>
    <title>{escaped_title}</title>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="https://cdn.maptiler.com/tileviewer/v1/index.css" type="text/css"/>
    <script src="https://cdn.maptiler.com/tileviewer/v1/index.js"></script>
  </head>
  <body>
    <script type="text/javascript">
      var GOOGLEMAPS_KEY = '';
      var data = {_safe_json(data, indent=2)};
      tileserver(data);
    </script>
  </body>
</html>
"""

    leaflet_html = f"""<!DOCTYPE html>
<html>
  <head>
    <title>{escaped_title}</title>
    <meta http-equiv="imagetoolbar" content="no">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.css">
    <link rel="stylesheet" href="https://cdn.rawgit.com/ardhi/Leaflet.MousePosition/master/src/L.Control.MousePosition.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.js" type="text/javascript"></script>
    <script src="https://cdn.rawgit.com/ardhi/Leaflet.MousePosition/master/src/L.Control.MousePosition.js" type="text/javascript"></script>
    <style>
      body {{ margin:0; padding:0; width:100%; height:100%; background: #ffffff; }}
      #map {{ position:absolute; top:0; bottom:0; width:100%; z-index: 1; }}
      #slider {{ position: absolute; top: 10px; right: 10px; z-index: 5; }}
    </style>
  </head>
<body>
  <div id="map"></div>
  <input id="slider" type="range" min="0" max="1" step="0.1" value="1" oninput="layer.setOpacity(this.value)">
  <script type="text/javascript">
    var mapExtent = [{west:.8f}, {south:.8f}, {east:.8f}, {north:.8f}];
    var mapMinZoom = {min_zoom};
    var mapMaxZoom = {max_zoom};
    var bounds = new L.LatLngBounds(
      new L.LatLng(mapExtent[1], mapExtent[0]),
      new L.LatLng(mapExtent[3], mapExtent[2]));
    var map = L.map('map').fitBounds(bounds);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
    var layer;
    var options = {{
      minZoom: mapMinZoom,
      maxZoom: mapMaxZoom,
      opacity: 1.0,
      attribution: {_safe_json(ATTRIBUTION)},
      tms: false
    }};
    layer = L.tileLayer('{{z}}/{{x}}/{{y}}.png', options).addTo(map);
    map.setZoom({viewer_zoom});
  </script>
</body>
</html>
"""

    openlayers_html = f"""<!DOCTYPE html>
<html>
<head>
<title>{escaped_title}</title>
<meta http-equiv="imagetoolbar" content="no"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0">
<meta name="apple-mobile-web-app-capable" content="yes">
<style type="text/css">
html, body {{ margin:0; padding: 0; height: 100%; width: 100%; }}
body {{ width:100%; height:100%; background: #ffffff; }}
#map {{ position: absolute; height: 100%; width: 100%; }}
#slider {{ position: absolute; top: 10px; right: 10px; }}
</style>
<link rel="stylesheet" href="https://cdn.maptiler.com/ol/v6.12.0/ol.css" type="text/css">
<script src="https://cdn.polyfill.io/v2/polyfill.min.js?features=requestAnimationFrame,Element.prototype.classList,URL,fetch,Function.prototype.bind,es5&flags=always,gated&unknown=polyfill" type="text/javascript"></script>
<script src="https://cdn.maptiler.com/ol/v6.12.0/ol.js" type="text/javascript"></script>
</head>
<body>
<div id="map"></div>
<input id="slider" type="range" min="0" max="1" step="0.1" value="1" oninput="layer.setOpacity(parseFloat(this.value))">
<script type="text/javascript">
var mapExtent = ol.proj.transformExtent([{west:.8f}, {south:.8f}, {east:.8f}, {north:.8f}], 'EPSG:4326', 'EPSG:3857');
var mapMinZoom = {min_zoom};
var mapMaxZoom = {max_zoom};
var layer = new ol.layer.Tile({{
  extent: mapExtent,
  source: new ol.source.XYZ({{
    attributions: {_safe_json(ATTRIBUTION)},
    url: "{{z}}/{{x}}/{{y}}.png",
    tilePixelRatio: 1.00000000,
    minZoom: mapMinZoom,
    maxZoom: mapMaxZoom
  }})
}});
var mapLayer = new ol.layer.Tile({{ source: new ol.source.OSM() }});
var map = new ol.Map({{
  target: 'map',
  layers: [mapLayer, layer],
  view: new ol.View({{
    center: ol.proj.fromLonLat([{center_longitude:.8f}, {center_latitude:.8f}]),
    zoom: {viewer_zoom}
  }})
}});
</script>
</body>
</html>
"""

    googlemaps_html = f"""<!DOCTYPE html>
<html>
<head>
<title>{escaped_title}</title>
<meta name="viewport" content="initial-scale=1.0, user-scalable=no" />
<style type="text/css">
html {{ overflow: hidden; }}
body {{ overflow: hidden; padding: 0; margin: 0; width: 100%; height: 100%; font-family: Trebuchet MS, Trebuchet, Arial, sans-serif; background: #f4f4f4; }}
#map {{ position: absolute; top: 10px; left: 10px; right: 10px; bottom: 15px; overflow: auto; border: 1px solid #ccc; box-shadow: 0 1px 3px #CCC; background-color: #DEDCD7; }}
#footer {{ position: absolute; bottom: 0; left: 0; width:100%; height: 12px; overflow: hidden; text-align:center; font-size:9px; color:#606060; }}
@media screen and (max-width: 600px) {{ #map {{ top:0; left:0; width:100%; height:100%; }} }}
</style>
<script type="text/javascript" src="https://maps.google.com/maps/api/js?key=&sensor=false"></script>
<script type="text/javascript">
var map;
var mapBounds = new google.maps.LatLngBounds(
    new google.maps.LatLng({south:.8f}, {west:.8f}),
    new google.maps.LatLng({north:.8f}, {east:.8f}));
var mapMinZoom = {min_zoom};
var mapMaxZoom = {max_zoom};
var maptiler = new google.maps.ImageMapType({{
    getTileUrl: function(coord, zoom) {{
        var proj = map.getProjection();
        var z2 = Math.pow(2, zoom);
        var tileXSize = 256 / z2;
        var tileYSize = 256 / z2;
        var tileBounds = new google.maps.LatLngBounds(
            proj.fromPointToLatLng(new google.maps.Point(coord.x * tileXSize, (coord.y + 1) * tileYSize)),
            proj.fromPointToLatLng(new google.maps.Point((coord.x + 1) * tileXSize, coord.y * tileYSize))
        );
        var x = coord.x >= 0 ? coord.x : z2 + coord.x;
        var y = coord.y;
        if (mapBounds.intersects(tileBounds) && (mapMinZoom <= zoom) && (zoom <= mapMaxZoom))
            return zoom + "/" + x + "/" + y + ".png";
        return "https://www.maptiler.com/img/none.png";
    }},
    tileSize: new google.maps.Size(256, 256),
    isPng: true,
    name: "Rendered with MapTiler Engine <https://www.maptiler.com/engine/>",
    alt: "Rendered with MapTiler Engine",
    opacity: 1.0
}});
function init() {{
    var opts = {{
        tilt: 0,
        streetViewControl: false,
        center: new google.maps.LatLng({center_latitude:.8f}, {center_longitude:.8f}),
        zoom: {min_zoom}
    }};
    map = new google.maps.Map(document.getElementById("map"), opts);
    map.setMapTypeId('satellite');
    map.overlayMapTypes.insertAt(0, maptiler);
}}
</script>
</head>
<body onload="init()">
<div id="footer"><a href="https://www.maptiler.com/engine/">Rendered with MapTiler Engine</a></div>
<div id="map"></div>
</body>
</html>
"""

    return {
        "index.html": index_html,
        "leaflet.html": leaflet_html,
        "openlayers.html": openlayers_html,
        "googlemaps.html": googlemaps_html,
    }


def _build_folder_package(
    *,
    dataset: Any,
    project: Any,
    control_points: list[Any],
    icon_points: list[Any],
    temporary_directory: Path,
) -> Path:
    mbtiles = _raster_mbtiles(dataset)
    if mbtiles is None:
        _, tiles, min_zoom, max_zoom = _tile_files(dataset)
        bounds = _dataset_bounds(dataset)
        mbtiles_path = None
    else:
        mbtiles_path, info = mbtiles
        tiles = []
        min_zoom = info.min_zoom
        max_zoom = info.max_zoom
        bounds = _mbtiles_bounds(mbtiles_path, info)
    metadata = {
        "name": project.name,
        "version": "1.1.0",
        "description": "",
        "attribution": ATTRIBUTION,
        "type": "overlay",
        "format": "png",
        "minzoom": str(min_zoom),
        "maxzoom": str(max_zoom),
        "scale": "1.000000",
        "bounds": list(bounds),
        "profile": "mercator",
    }
    source_asset = _source_asset(dataset)
    source_asset_path = None if source_asset is None else source_asset[1]
    project_document = _project_document(
        dataset=dataset,
        project=project,
        control_points=control_points,
        icon_points=icon_points,
        source_asset_path=source_asset_path,
    )
    output_path = temporary_directory / f"{_safe_stem(project.name)}.zip"
    with zipfile.ZipFile(output_path, "w", allowZip64=True) as archive:
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "mapstudio.json",
            json.dumps(project_document, ensure_ascii=False, indent=2) + "\n",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for filename, contents in _viewer_files(
            name=project.name,
            bounds=bounds,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
        ).items():
            archive.writestr(
                filename,
                contents,
                compress_type=zipfile.ZIP_DEFLATED,
            )
        if mbtiles_path is None:
            for source, archive_name in tiles:
                archive.write(
                    source,
                    archive_name,
                    compress_type=zipfile.ZIP_STORED,
                )
        else:
            _write_mbtiles_pngs(archive, mbtiles_path)
        if source_asset is not None:
            archive.write(
                source_asset[0],
                source_asset[1],
                compress_type=zipfile.ZIP_STORED,
            )
    return output_path


def export_project(dataset_id: UUID, db: SessionRepository) -> FileResponse:
    project = db.get_map_project_by_dataset_id(dataset_id)
    dataset = db.get_dataset(dataset_id)
    if project is None or dataset is None:
        raise _error(
            404,
            "MAP_PROJECT_NOT_FOUND",
            "The map project was not found.",
            "Open and save the dataset project before exporting it.",
        )

    temporary_directory = Path(tempfile.mkdtemp(prefix="maptiler-export-"))
    try:
        output = _build_folder_package(
            dataset=dataset,
            project=project,
            control_points=db.list_control_points(dataset.id),
            icon_points=db.list_icon_points(dataset.id),
            temporary_directory=temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    return _temporary_response(
        output,
        filename=output.name,
        temporary_directory=temporary_directory,
    )
