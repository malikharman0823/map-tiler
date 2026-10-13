## ADDED Requirements

### Requirement: Typed portable workspace records
The workspace records API SHALL return discriminated Raster, Control Point, and User Icon records with raw numeric spatial values and managed relative paths, and SHALL NOT expose resolved machine-specific paths.

#### Scenario: Records are loaded
- **WHEN** the Database view requests workspace records
- **THEN** each result identifies its record kind and dataset and supplies kind-appropriate raw fields

### Requirement: Server-driven data grid
The Database view SHALL support search, dataset/type/status filters, sorting, pagination, column visibility, and pinned Name and Status columns using server-returned row and filtered-total values.

#### Scenario: Filter changes
- **WHEN** a user changes search or filters
- **THEN** pagination resets to the first page and the server returns matching records plus the filtered total

#### Scenario: Grid is used on a phone
- **WHEN** the table exceeds the viewport width
- **THEN** pinned columns remain visible, the remaining columns scroll horizontally, and record editing uses a bottom sheet

### Requirement: Collection-based table filtering
Selecting a dataset parent SHALL show all its records and selecting a sublayer SHALL filter the grid to that record kind.

#### Scenario: Control Points collection selected
- **WHEN** the user selects a member's Control Points sublayer
- **THEN** the grid shows only control-point records belonging to that member dataset

### Requirement: Curated editing boundaries
The table SHALL permit explicit editing of dataset aliases, user-icon type, and user-icon description, while identifiers, paths, CRS, bounds, status, and control-point coordinates remain read-only.

#### Scenario: User icon description is saved
- **WHEN** a user edits the description and chooses Save
- **THEN** the existing icon-point record is updated and the editor exits dirty state

#### Scenario: Read-only spatial metadata is selected
- **WHEN** a user inspects CRS, bounds, path, status, or a control-point coordinate
- **THEN** the value is displayed without an editable input

### Requirement: Map and table selection synchronization
Selecting a spatial record in either workspace view SHALL update the shared selection so the corresponding table row and map feature are highlighted and focusable.

#### Scenario: Table point selected
- **WHEN** the user selects a control-point or icon-point row
- **THEN** Map view can focus and highlight the corresponding geographic feature without recreating the map

### Requirement: Map-driven point placement
Creation or repositioning of geographic point records SHALL use explicit map-placement modes and SHALL NOT require typed latitude or longitude.

#### Scenario: Placement is cancelled
- **WHEN** a user cancels an incomplete point placement
- **THEN** no persistent point record is created or changed

