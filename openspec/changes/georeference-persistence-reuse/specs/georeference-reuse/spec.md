## ADDED Requirements

### Requirement: Saved configuration is loadable
The system SHALL expose the active georeference configuration and include database-backed summary data when loading the dataset or georeferencing route without recalculating it.

#### Scenario: Reload completed dataset
- **WHEN** the application reloads and opens a dataset with a completed active configuration
- **THEN** status, transformation, parameters, control-point count, target CRS, source size, output format, and stored control points are restored from PostgreSQL

### Requirement: Reuse validates source identity
The system MUST compare dataset identity, source file hash, width, and height before declaring a saved configuration reusable.

#### Scenario: Same source is reusable
- **WHEN** the active configuration belongs to the same dataset, hash, width, and height
- **THEN** Reuse Configuration restores its points and transformation parameters for inspection without overwriting data

#### Scenario: Source dimensions differ
- **WHEN** the source dimensions differ from the saved configuration
- **THEN** reuse is blocked with the configured unsafe-reuse message and no geographic output is changed

### Requirement: Saved configuration can be edited safely
The system SHALL allow the user to enter Edit Georeferencing, mutate persisted control points through insert/update/delete, recalculate, preview, and save the updated active configuration.

#### Scenario: Move and resave a control point
- **WHEN** a user moves a saved point, recalculates, and saves
- **THEN** the point row, transformation parameters, timestamps, output, and active configuration reflect the edit

### Requirement: Errors use the application envelope
The system SHALL return structured application errors for invalid points, invalid transformations, failed output, failed saves, invalid configurations, and unsafe reuse without exposing SQL, stack traces, or absolute paths.

#### Scenario: Invalid saved configuration
- **WHEN** persisted configuration data is incomplete or incompatible
- **THEN** the API returns `INVALID_CONFIGURATION` or `CONFIGURATION_NOT_REUSABLE` in the existing error envelope

