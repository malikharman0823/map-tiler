## ADDED Requirements

### Requirement: Truthful six-format export surface
The project export API SHALL expose `.mtmap`, `.gpkg`, `.geojson`, `.tif`, MapLibre style `.json`, and `.mbtiles` choices and MUST either return a valid artifact or a structured, format-specific unavailable error.

#### Scenario: Missing required source
- **WHEN** a requested export cannot be produced from current project data or completed outputs
- **THEN** the endpoint returns a non-2xx structured error and never returns a mislabeled placeholder file

### Requirement: GeoJSON and GeoPackage vector export
The system SHALL export complete available vector features and attributes as valid GeoJSON or vector-only GeoPackage data using WGS84 geometry unless the preserved original is returned losslessly.

#### Scenario: Export imported GeoPackage
- **WHEN** the dataset source is a valid GeoPackage
- **THEN** GeoPackage export downloads the preserved original package

#### Scenario: Export project points to GeoPackage
- **WHEN** a non-GeoPackage project has control or icon point features
- **THEN** GeoPackage export creates readable vector layers containing those features and attributes

### Requirement: GeoTIFF export
The system SHALL export the current georeferenced raster when present, otherwise a valid GeoTIFF source, and SHALL reject projects without a GeoTIFF artifact.

#### Scenario: Completed georeference
- **WHEN** the project has a completed managed georeferenced output
- **THEN** GeoTIFF export downloads that output with a `.tif` filename and TIFF media type

### Requirement: MapLibre style JSON export
The system SHALL export a valid MapLibre Style Specification v8 document representing the preserved imported style or the current project layer configuration without secrets or machine-local paths.

#### Scenario: Generated project style
- **WHEN** a project has no imported style document
- **THEN** style export produces version 8 JSON referencing only public API templates and the project's current visibility/opacity configuration

### Requirement: MBTiles generation and export
The system MUST create standards-compatible MBTiles from the existing completed tile-generation output, use TMS tile rows, write required metadata, and validate the generated SQLite before download. Imported valid MBTiles MAY be returned directly.

#### Scenario: Directory tiles exported
- **WHEN** raster tile generation completed and managed tile files exist
- **THEN** MBTiles export creates a non-empty SQLite archive with matching zoom range, format, bounds where available, and tile blobs

### Requirement: Download response contract
Every export SHALL set an accurate media type and attachment filename, SHALL stream file content, and SHALL remove temporary generated artifacts after the response completes.

#### Scenario: Generated artifact response
- **WHEN** a generated export succeeds
- **THEN** the response includes `Content-Disposition`, content metadata, and post-response cleanup without deleting managed project sources
