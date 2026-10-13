## ADDED Requirements

### Requirement: Single export surface
The system SHALL expose one dataset export operation and SHALL NOT present or route `.mtmap`, `.gpkg`, `.geojson`, `.tif`, MapLibre style `.json`, or `.mbtiles` export choices.

#### Scenario: User exports a dataset
- **WHEN** the user activates Export for a dataset with completed generated raster tiles
- **THEN** the browser makes one formatless export request and downloads one `.zip` package

#### Scenario: Legacy format route is requested
- **WHEN** a client requests a former format-specific export URL
- **THEN** the API does not dispatch a legacy export builder

### Requirement: MapTiler folder package
The exported ZIP SHALL contain `metadata.json`, `index.html`, `leaflet.html`, `openlayers.html`, `googlemaps.html`, and every eligible generated PNG tile at `<z>/<x>/<y>.png`.

#### Scenario: Completed tiles are packaged
- **WHEN** export runs for a dataset whose managed XYZ tile directory contains PNG tiles
- **THEN** the archive preserves each tile's relative zoom, column, and row path and includes no MBTiles or MTMap artifact

#### Scenario: Imported raster MBTiles is packaged
- **WHEN** export runs for an imported MBTiles dataset whose tile format is PNG
- **THEN** the archive extracts each tile to its XYZ `<z>/<x>/<y>.png` path, converts stored TMS rows to XYZ rows, and includes no `.mbtiles` artifact

#### Scenario: Package configuration is generated
- **WHEN** the archive is created
- **THEN** its metadata and viewers use the project name, WGS84 bounds, center, PNG format, Web Mercator profile, XYZ scheme, and completed minimum and maximum zoom values

### Requirement: Truthful availability errors
The exporter MUST reject datasets that cannot produce a usable raster folder package and MUST return a structured error without downloading an empty archive.

#### Scenario: Tile generation is incomplete
- **WHEN** export is requested before generated tiles are completed
- **THEN** the API returns a `409` error explaining that raster processing and tile generation must be completed

#### Scenario: Tile directory is missing or empty
- **WHEN** completed tile state points to a missing directory or contains no valid PNG XYZ tile
- **THEN** the API returns a structured missing-tile error and removes any temporary export data

#### Scenario: Imported tile encoding is incompatible
- **WHEN** an imported MBTiles dataset uses a tile format other than PNG
- **THEN** the API returns a structured unsupported-format error instead of exporting a legacy artifact

### Requirement: Download lifecycle
The exporter SHALL return an `application/zip` attachment with a filesystem-safe project-based filename and SHALL remove temporary generated artifacts after the response completes.

#### Scenario: Export response succeeds
- **WHEN** a valid folder package is built
- **THEN** the response streams a non-empty `.zip` attachment and schedules its temporary directory for cleanup
