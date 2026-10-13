## Why

The application currently exposes several incompatible export artifacts, while the required delivery format is the MapTiler folder layout represented by the supplied `New Adam` package. Export must have one predictable contract that includes usable PNG tiles, metadata, and browser viewers.

## What Changes

- **BREAKING** Replace `.mtmap`, `.gpkg`, `.geojson`, `.tif`, MapLibre style `.json`, and `.mbtiles` export choices with one MapTiler-compatible folder-package export.
- Download the folder package as a `.zip` containing `metadata.json`, `index.html`, `leaflet.html`, `openlayers.html`, `googlemaps.html`, and `{z}/{x}/{y}.png` raster tiles.
- Derive the package name, geographic bounds, zoom range, and tile paths from completed generated tiles or an imported raster PNG MBTiles source.
- Extract imported raster PNG MBTiles into XYZ PNG paths inside the ZIP; never return the `.mbtiles` container itself.
- Reject export with a structured error when usable PNG tiles are unavailable.
- Keep existing import and in-application preview behavior outside this export-only change.

## Capabilities

### New Capabilities

- `folder-tile-export`: Single downloadable MapTiler-style raster tile folder package and its availability/error contract.

### Modified Capabilities


## Impact

- Replaces the format parameter and six-format branching in the dataset export API.
- Simplifies the dataset export UI and browser download naming to one `.zip` artifact.
- Retires export-only builders and tests for `.mtmap`, GeoPackage, GeoJSON, GeoTIFF, style JSON, and MBTiles while leaving imports and preview routes unchanged.
- Uses existing generated XYZ PNG tiles or existing raster PNG MBTiles data and does not introduce a new geospatial dependency.
