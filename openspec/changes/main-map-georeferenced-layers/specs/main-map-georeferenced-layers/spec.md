## ADDED Requirements

### Requirement: Save publishes a complete geographic dataset layer
The system SHALL keep Calculate preview-only and SHALL make Save Georeference generate and persist the managed georeferenced raster, processed raster, and tile source before reporting success.

#### Scenario: Successful save
- **WHEN** a valid calculated georeference is saved
- **THEN** the active configuration, GeoTIFF, processed raster, tile source, and completed dataset statuses are available to the main map without another upload or calculation

#### Scenario: Publication fails
- **WHEN** raster processing or tile generation fails during Save Georeference
- **THEN** the request returns the existing structured error and the dataset is not exposed as a completed main-map floor-plan layer

### Requirement: Dataset detail describes the saved map layer
The system SHALL expose a completed saved map layer with its dynamic dataset name, tile URL and zooms, source CRS, and actual raster-derived WGS84 bounds, and SHALL never derive the floor-plan extent from control points.

#### Scenario: Completed output is loaded after restart
- **WHEN** the same completed dataset is opened after an application reload or restart
- **THEN** dataset detail supplies the persisted layer metadata and the main map loads it without recalculating the georeference

#### Scenario: Raster extent exceeds control-point extent
- **WHEN** saved control points do not cover every raster corner
- **THEN** Fit Dataset uses the transformed raster bounds rather than the control-point envelope

### Requirement: Saved-layer failures use structured errors
The system MUST reject broken completed publications with the existing application error envelope and MUST not expose absolute paths, stack traces, or raw geospatial errors.

#### Scenario: Saved raster is missing
- **WHEN** a completed active configuration references a managed georeferenced raster that is absent
- **THEN** dataset-detail loading fails with `RASTER_OUTPUT_NOT_FOUND`

#### Scenario: Tile source is missing
- **WHEN** a completed active configuration has no valid completed tile directory
- **THEN** dataset-detail loading fails with `TILE_SOURCE_NOT_FOUND`

### Requirement: Main-map layers are isolated and ordered
The main map SHALL use the existing MapLibre instance and SHALL render World Map, the selected dataset's saved floor plan, that dataset's saved control points, and that dataset's icon points as independent layers in that order.

#### Scenario: Dataset is not completed
- **WHEN** the selected dataset has no completed active georeference
- **THEN** the main map does not show a saved floor-plan layer or control-point layer, while its independent icon points remain available

#### Scenario: Completed dataset is selected
- **WHEN** a dataset with a completed saved layer opens
- **THEN** only that dataset's floor plan, control points, and icon points are supplied to their respective sources

### Requirement: Layer controls update the existing map
The main map SHALL independently toggle all four layer groups, SHALL apply floor-plan opacity only to the dataset layer, and SHALL update existing sources and layers without recreating the map or creating duplicates.

#### Scenario: User changes visibility and opacity
- **WHEN** the user toggles the floor plan, control points, or icon points and changes floor-plan opacity
- **THEN** only the chosen layer state changes and all other layers retain their visibility and opacity

#### Scenario: Georeference is saved again
- **WHEN** the active georeference is edited and successfully re-saved
- **THEN** the prior dataset source/layer is replaced or updated, control points are refreshed, and no numbered duplicate floor-plan layer is created

### Requirement: Geographic layers remain aligned
The system SHALL use geographic MapLibre sources for the raster tiles, saved control-point longitude/latitude values, and icon-point longitude/latitude values so all layers remain aligned through pan, zoom, rotation, and resize.

#### Scenario: Map camera changes
- **WHEN** the user pans, zooms, rotates, or resizes the completed dataset map
- **THEN** the floor plan, blue crosshair control points, and icon points retain their saved geographic anchors

#### Scenario: Control point is inspected
- **WHEN** the user selects a saved control point on the main map
- **THEN** its actual ID, latitude, longitude, image X, and image Y are displayed

### Requirement: Dataset fitting does not override manual navigation
The main map SHALL fit once to the selected completed raster's actual bounds and SHALL expose an explicit Fit Dataset action without repeatedly overriding later user pan or zoom.

#### Scenario: Dataset first opens
- **WHEN** a completed dataset is first opened
- **THEN** the map fits once to its saved WGS84 raster bounds

#### Scenario: User navigates manually
- **WHEN** the user pans or zooms after the initial fit
- **THEN** ordinary React state updates do not force another fit
