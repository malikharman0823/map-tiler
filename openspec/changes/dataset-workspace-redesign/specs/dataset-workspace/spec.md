## ADDED Requirements

### Requirement: Persistent dataset-centered membership
Each dataset workspace SHALL have one primary dataset and SHALL persist zero or more reusable attached datasets without copying or merging their source records or managed files.

#### Scenario: Secondary dataset is attached
- **WHEN** a user confirms adding an imported dataset to the current workspace
- **THEN** the membership, alias, order, visibility, and opacity are persisted for reload

#### Scenario: Dataset is reused
- **WHEN** the same dataset is attached to another workspace
- **THEN** both workspaces reference the original dataset through independent membership settings

### Requirement: Detach without deletion
Removing a secondary dataset from a workspace SHALL delete only that membership and SHALL leave its dataset, points, and managed files available in the library.

#### Scenario: Secondary dataset is detached
- **WHEN** the user confirms removal from the layer tree
- **THEN** the member disappears from that workspace but remains independently openable

### Requirement: Hierarchical layer controls
The workspace SHALL represent each member as a parent with Raster, Control Points, and User Icons collection sublayers when present, and SHALL persist parent order, parent visibility, child visibility, and raster opacity.

#### Scenario: Parent is hidden and restored
- **WHEN** the user hides and later shows a dataset parent
- **THEN** all children are temporarily hidden and their previous individual visibility choices are restored

#### Scenario: Dataset parents are reordered
- **WHEN** the user reorders datasets by pointer, touch handle, or keyboard controls
- **THEN** the saved order is reflected in both the layer tree and MapLibre rendering after reload

### Requirement: Unified responsive workspace
The workspace SHALL provide synchronized Map and Database views selected through bottom navigation and SHALL remain usable on desktop, tablet, and phone layouts.

#### Scenario: View is switched
- **WHEN** the user selects Map or Database
- **THEN** the route, shared selection, filters, and last active view stay synchronized without reloading the workspace

#### Scenario: Workspace opens on a phone
- **WHEN** the viewport cannot show persistent side panels
- **THEN** layers and record details remain available through responsive sheets while bottom navigation stays operable

### Requirement: Hybrid persistence feedback
Layer settings and workspace view/camera state SHALL autosave with Saved, Failed, and Retry feedback, while curated record fields SHALL require Save or Cancel.

#### Scenario: Autosave fails
- **WHEN** a layer or workspace-state update fails
- **THEN** the attempted value remains visible, is marked failed, and can be retried

#### Scenario: User navigates with a dirty record edit
- **WHEN** an explicit record edit has unsaved changes
- **THEN** the interface warns before discarding those changes

### Requirement: Secondary georeference return flow
An unreferenced secondary upload SHALL remain attached as pending, open the separate georeference page, and return to the originating workspace after a successful save.

#### Scenario: Secondary georeference is saved
- **WHEN** publication completes from an originating workspace
- **THEN** the Database view opens and refreshes that member's raster and control-point records

#### Scenario: Secondary georeference is cancelled
- **WHEN** the user leaves without saving
- **THEN** the attached dataset remains marked Needs georeferencing

