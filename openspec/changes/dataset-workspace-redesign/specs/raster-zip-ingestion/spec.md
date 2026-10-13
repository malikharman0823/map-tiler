## ADDED Requirements

### Requirement: ZIP-only raster bundle input
The redesigned upload interface SHALL accept one ZIP archive representing one raster dataset and SHALL NOT expose individual raster, vector, tile, project-folder, or style-file selectors.

#### Scenario: Valid raster bundle selected
- **WHEN** a user selects a ZIP containing exactly one supported raster and optional matching sidecars
- **THEN** the system validates and imports that raster as one dataset

#### Scenario: Non-ZIP input selected
- **WHEN** the selected file is not a ZIP archive
- **THEN** the interface rejects it before upload with a ZIP-only explanation

### Requirement: Secure unambiguous archive parsing
The importer MUST reject traversal paths, links, encrypted or excessive archives, unsupported contents, missing rasters, and archives containing multiple candidate rasters, and MUST clean staged files on failure.

#### Scenario: Archive contains multiple rasters
- **WHEN** validation finds more than one supported raster candidate
- **THEN** import fails without creating a dataset or leaving staged files

#### Scenario: Archive contains an unsafe entry
- **WHEN** an entry escapes the extraction root or is not a permitted regular file
- **THEN** import fails before that entry is written

### Requirement: Deterministic georeference detection
The importer SHALL mark a raster georeferenced only when metadata supplies both a usable CRS and affine transform, from embedded metadata or matching sidecars, and SHALL never guess a missing CRS.

#### Scenario: Embedded GeoTIFF metadata is complete
- **WHEN** a GeoTIFF contains a usable CRS and transform
- **THEN** the imported dataset is marked georeferenced

#### Scenario: Spatial metadata is incomplete
- **WHEN** either the CRS or affine transform is absent or unusable
- **THEN** the imported dataset is marked as needing georeferencing

### Requirement: Post-upload routing
The interface SHALL open georeferenced primary uploads in Map view and SHALL offer Georeference Now or Open Database for unreferenced primary uploads.

#### Scenario: Georeferenced primary upload completes
- **WHEN** import succeeds with complete spatial metadata
- **THEN** the dataset workspace opens in Map view fitted to the raster

#### Scenario: Unreferenced primary upload completes
- **WHEN** import succeeds without complete spatial metadata
- **THEN** a decision dialog offers the georeference page or the workspace Database view

