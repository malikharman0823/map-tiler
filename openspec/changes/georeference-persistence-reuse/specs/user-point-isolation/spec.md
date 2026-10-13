## ADDED Requirements

### Requirement: User points persist independently
The system SHALL store user-created geographic points and descriptions in `user_points` linked to a dataset and SHALL keep them separate from control points and georeference configuration records.

#### Scenario: Georeference with user points present
- **WHEN** a dataset has user points and control points and georeferencing is calculated or saved
- **THEN** only control points participate in the transformation and the user points remain unchanged

### Requirement: User points have an independent map layer
The Dataset Map SHALL load user points from PostgreSQL and render them as a separately controllable red layer while control points remain blue.

#### Scenario: Toggle point layers
- **WHEN** a dataset contains both point types and the user toggles either layer
- **THEN** only the selected layer visibility changes and no records are modified

### Requirement: User point CRUD is durable
The system SHALL support creating, listing, updating, and deleting dataset user points through the existing function-based API style.

#### Scenario: Reload a user point
- **WHEN** a user point with a description is created and the application reloads
- **THEN** its coordinates and description are restored from PostgreSQL
