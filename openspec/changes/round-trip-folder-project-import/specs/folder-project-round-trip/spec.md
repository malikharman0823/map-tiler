## ADDED Requirements

### Requirement: Exported folder contains Map Studio state
The system SHALL add a versioned Map Studio project document to the folder export and SHALL preserve project configuration, control points, user-created icon points, dataset map metadata, and an optional managed raster source.

#### Scenario: Editable project state is exported
- **WHEN** a user exports a saved project
- **THEN** `mapstudio.json` contains the project settings and point data while the folder retains `metadata.json`, all viewer pages, and XYZ PNG tiles

#### Scenario: Managed raster source is available
- **WHEN** the exported dataset has a managed JPG, PNG, or TIFF source
- **THEN** the source is included under `assets/source/` and referenced by a safe relative path in `mapstudio.json`

#### Scenario: Source is a tile archive
- **WHEN** the exported dataset originates from MBTiles or another non-raster source
- **THEN** the original container is not included and the exported XYZ PNG layer remains sufficient to reopen the map

### Requirement: Extracted folder can be opened
Map Studio SHALL let the user select an extracted exported directory and SHALL submit its files with explicit relative paths to one folder-import operation.

#### Scenario: User opens an exported directory
- **WHEN** the user chooses a directory containing a valid Map Studio folder package
- **THEN** the application imports it and navigates directly to the newly restored dataset project

#### Scenario: User uploads an ordinary file
- **WHEN** the user chooses a supported non-folder dataset file
- **THEN** the existing single-file upload behavior remains available

### Requirement: Folder restoration is complete and transactional
The folder importer MUST restore the project under fresh identifiers, copy assets only into dataset-scoped managed storage, validate all state, and commit the database records atomically.

#### Scenario: Valid project folder is restored
- **WHEN** a folder has valid metadata, state, and PNG XYZ tiles
- **THEN** the restored project contains the saved configuration, control points, icon points, zoom range, bounds, optional source raster, and completed tile layer

#### Scenario: Folder validation fails
- **WHEN** a folder contains traversal paths, duplicate paths, invalid state, unsupported assets, invalid tile coordinates, or exceeds import limits
- **THEN** the API returns a structured error, rolls back database changes, and removes all staged files

### Requirement: Restored raster map works without regeneration
The system SHALL expose imported folder tiles through the normal dataset tile route and SHALL produce a raster map-layer response from the restored WGS84 bounds and zoom range.

#### Scenario: Imported project is opened in Map Studio
- **WHEN** the restored dataset page loads
- **THEN** the saved layer visibility and opacity are applied, the raster XYZ layer is displayed, and saved control and icon points are loaded on the map
