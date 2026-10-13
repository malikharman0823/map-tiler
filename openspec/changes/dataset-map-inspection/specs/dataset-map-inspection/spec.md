## ADDED Requirements

### Requirement: Stored control points are visible on the Dataset Map
The Dataset Map SHALL load stored control points from `GET /datasets/{dataset_id}/control-points` when the dataset workspace opens and SHALL render every returned point as a distinct, labeled map marker without modifying it.

#### Scenario: Dataset has multiple control points
- **WHEN** a dataset workspace loads with multiple stored control points
- **THEN** the map displays each returned latitude and longitude as a labeled marker and the inspection rail lists each point once

#### Scenario: Dataset has no control points
- **WHEN** a dataset workspace loads with no stored control points
- **THEN** the map remains usable and the inspection rail states that no stored control points are available

### Requirement: Control-point selection is synchronized
The Dataset Map SHALL allow selecting a control point from either its map marker or inspection list, SHALL visibly highlight the selected point, SHALL focus the map on it without reinitializing the map, and SHALL expose its actual database ID, latitude, longitude, image X, and image Y values.

#### Scenario: User selects a marker
- **WHEN** a user clicks a control-point marker
- **THEN** the point becomes selected, its popup displays its stored values, and the information panel shows the same point

#### Scenario: User selects a control point from the list
- **WHEN** a user selects a point in the control-point list
- **THEN** the corresponding map marker is selected and the map focuses that stored geographic location

### Requirement: Dataset Map remains read-only for control points
The Dataset Map SHALL not create, update, drag, or delete control points through ordinary map clicks or marker interaction.

#### Scenario: User clicks elsewhere on the map
- **WHEN** a user clicks a location that is not a control-point marker
- **THEN** no control point is created or modified

### Requirement: Information rail is compact and responsive
The Dataset Map SHALL provide collapsible dataset information, legend, control-point, and layer sections. On small screens, the rail SHALL not occupy the map permanently and all interactive controls SHALL have a minimum 44px target.

#### Scenario: User collapses the information rail on desktop
- **WHEN** the user collapses the information rail
- **THEN** the map gains the available horizontal space without reloading its data

#### Scenario: User opens information on mobile
- **WHEN** a user opens the mobile map information panel
- **THEN** its dataset, legend, control-point, and layer sections can be expanded without horizontal overflow

### Requirement: Layer visibility is independently controlled
The Dataset Map SHALL provide independent show or hide controls for the base map, visible dataset layer, and control-point layer without recreating the MapLibre instance or refetching unchanged data.

#### Scenario: User hides control points
- **WHEN** the user disables the Control Points layer
- **THEN** control-point markers disappear while the base map and dataset layer retain their current state

#### Scenario: User hides the dataset layer
- **WHEN** the user disables the Dataset layer
- **THEN** the dataset raster or vector preview is hidden while other enabled layers remain visible
