## ADDED Requirements

### Requirement: Completed georeference is persisted
The system SHALL persist the active dataset georeference through SQLAlchemy with its actual transformation, parameters, source coordinate convention, source identity and dimensions, CRS values, control-point count, managed output path and format, status, and timestamps.

#### Scenario: Save a valid affine georeference
- **WHEN** a dataset with three to ten valid control points is calculated and the user saves it
- **THEN** PostgreSQL contains one active completed configuration with the actual affine coefficients and the control points remain queryable

#### Scenario: Save a valid similarity georeference
- **WHEN** a dataset with exactly two valid control points is calculated and saved
- **THEN** the active configuration records `similarity` and sufficient actual parameters to reproduce the result

### Requirement: Required coordinate convention
The system MUST calculate and persist source coordinates as `x = image_x`, `y = -image_y` and target coordinates as `x = longitude`, `y = latitude`.

#### Scenario: Known point transformation
- **WHEN** a known raster and known point correspondences are calculated
- **THEN** the stored parameters and GeoTIFF transform/bounds reflect the required negative-image-Y convention

### Requirement: Transactional save and managed output
The system SHALL generate the final GeoTIFF before committing the completed configuration and dataset status, SHALL store a project-relative path, and SHALL roll back database changes and remove a newly orphaned output when persistence fails.

#### Scenario: Database persistence fails after output generation
- **WHEN** final output generation succeeds but the configuration transaction fails
- **THEN** the transaction is rolled back, the dataset is not marked completed, and the new untracked output is removed when safe

#### Scenario: Output generation fails
- **WHEN** Rasterio cannot generate a valid output
- **THEN** no completed configuration is saved and raw geospatial or filesystem errors are not exposed

### Requirement: One current configuration
The system SHALL update the existing active configuration for a dataset and SHALL allow at most one active configuration while retaining a schema that can support inactive history later.

#### Scenario: Save after editing
- **WHEN** a user edits persisted control points, recalculates, and saves again
- **THEN** the existing active configuration and point records contain the new values without a duplicate active configuration

### Requirement: Calculate and save remain distinct
The system SHALL provide a calculation/preview stage that does not persist a completed configuration and a Save Georeference stage enabled only after a valid output calculation.

#### Scenario: Calculate without saving
- **WHEN** the user calculates a valid transformation and leaves the page without saving
- **THEN** no completed configuration is created in PostgreSQL

