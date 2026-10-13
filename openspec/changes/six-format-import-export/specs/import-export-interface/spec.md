## ADDED Requirements

### Requirement: Clear import affordances
The interface SHALL distinguish opening a portable `.mtmap` project from uploading an individual dataset and SHALL list the six supported interchange formats accurately.

#### Scenario: Open project picker
- **WHEN** the user chooses Open Project
- **THEN** the picker accepts `.mtmap`, reports import progress/errors, and navigates to the newly restored dataset on success

#### Scenario: Dataset upload picker
- **WHEN** the user chooses Upload Dataset
- **THEN** the picker accepts GeoPackage, GeoJSON, GeoTIFF, MBTiles, and MapLibre style JSON in addition to preserved legacy formats

### Requirement: Export menu state machine
The export control MUST implement `closed`, `open`, `exporting`, `success`, and `error` states, close on selection/outside click/Escape, disable duplicate requests while exporting, and recover after success or failure.

#### Scenario: Successful Blob download
- **WHEN** the user selects an available format
- **THEN** the menu closes, one Axios Blob request runs, the browser downloads the response filename, and an accessible success state is shown

#### Scenario: Failed export
- **WHEN** the export API returns a structured error
- **THEN** no file is downloaded, the error is displayed, and the user can reopen the menu and retry

### Requirement: Safe download filenames
The frontend SHALL prefer a valid `Content-Disposition` filename and otherwise derive a sanitized filename from the current project name and selected extension.

#### Scenario: Missing response filename
- **WHEN** an export response omits `Content-Disposition`
- **THEN** the downloaded file uses a filesystem-safe project-name fallback with the correct extension

### Requirement: Save Project portable output
Saving a project SHALL persist current configuration and then generate the portable `.mtmap` download through the same export state handling.

#### Scenario: Save current project
- **WHEN** the user activates Save Project
- **THEN** current opacity/visibility state is saved before a versioned `.mtmap` file is downloaded
