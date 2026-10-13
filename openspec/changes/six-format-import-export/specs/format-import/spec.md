## ADDED Requirements

### Requirement: Six-format dataset detection
The system SHALL accept `.gpkg`, `.geojson`, `.tif`/`.tiff`, `.mbtiles`, and `.json` through the existing dataset upload flow and SHALL reserve `.mtmap` for the explicit project-import flow. JSON content MUST be classified by structure rather than extension alone.

#### Scenario: Valid MapLibre style JSON
- **WHEN** a JSON object contains MapLibre style version 8, a sources object, and a layers array
- **THEN** the system stores it as a style dataset with its exact parsed configuration

#### Scenario: Unsupported JSON structure
- **WHEN** an uploaded `.json` is neither a GeoJSON object nor a valid MapLibre style
- **THEN** the system rejects it with a structured `UNSUPPORTED_JSON_STRUCTURE` error

### Requirement: GeoJSON validation and preview
The system MUST validate GeoJSON type, geometry, coordinates, and feature properties, preserve valid attributes, and expose bounded WGS84 GeoJSON for the existing MapLibre viewer.

#### Scenario: Feature collection upload
- **WHEN** a valid GeoJSON FeatureCollection is uploaded
- **THEN** its complete source is stored and its features are available in the dataset map with their properties

#### Scenario: Malformed coordinates
- **WHEN** GeoJSON contains non-finite or structurally invalid coordinates
- **THEN** the upload fails without creating a dataset or leaving managed files

### Requirement: Vector GeoPackage import
The system SHALL inspect GeoPackage layers with GDAL/OGR, accept readable vector layers, preserve the original package, and expose their supported geometries and attributes as bounded WGS84 preview data.

#### Scenario: Multi-layer GeoPackage
- **WHEN** a GeoPackage contains multiple readable vector layers
- **THEN** metadata lists each layer and the map preview includes bounded features with their source layer identity

#### Scenario: GeoPackage without vector layers
- **WHEN** a GeoPackage has no readable vector layer
- **THEN** the system rejects it with a structured format error

### Requirement: Georeferenced raster import
The system SHALL recognize CRS, transform, bounds, resolution, bands, data type, nodata, and color information from readable GeoTIFF sources using Rasterio.

#### Scenario: Existing georeferenced GeoTIFF
- **WHEN** a GeoTIFF already has a CRS and spatial transform
- **THEN** its geographic metadata is persisted without requiring manual control points

### Requirement: MBTiles import and tile access
The system MUST validate imported MBTiles as SQLite with standard metadata and non-empty tiles, record zoom/format/bounds/vector-layer information, and serve tiles using XYZ-to-TMS row conversion with truthful media and encoding headers.

#### Scenario: Raster MBTiles map load
- **WHEN** a valid raster MBTiles dataset is opened
- **THEN** MapLibre requests its tile endpoint and displays the archive as the dataset layer

#### Scenario: Vector MBTiles map load
- **WHEN** valid PBF MBTiles includes vector-layer metadata
- **THEN** MapLibre receives PBF tiles and renders selectable generic layers for the declared source layers

#### Scenario: Invalid MBTiles schema
- **WHEN** an SQLite file lacks required metadata or tile data
- **THEN** import fails with a structured `INVALID_MBTILES` error

### Requirement: Upload integrity and deduplication
All individual-format uploads SHALL retain bounded streaming, SHA-256 deduplication, sanitized filenames, transactional database writes, and cleanup on validation or persistence failure.

#### Scenario: Duplicate source upload
- **WHEN** the same source bytes are uploaded again
- **THEN** the existing dataset is returned and no duplicate managed file or database record is created
