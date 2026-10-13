## ADDED Requirements

### Requirement: Responsive paired georeference workspace
The georeference page SHALL show the source image and world map side by side when space permits and SHALL stack them with accessible controls on smaller viewports.

#### Scenario: Georeference page opens on a narrow screen
- **WHEN** the viewport cannot display both panes at a usable width
- **THEN** both panes remain available in a stacked workflow without losing the current draft pair

### Requirement: Minimal numbered paired markers
Persisted and draft source-image points SHALL use minimal numbered black markers and matching world-map points SHALL use numbered blue markers with a shared pair number and a distinct non-color-only selected state.

#### Scenario: Pair is created
- **WHEN** the user selects a source-image position and then its world-map position
- **THEN** both markers display the same next pair number and the complete pair is persisted

### Requirement: Explicit pairing lifecycle
The page SHALL require explicit Add Control Point mode, source-first pairing, and cancellation of incomplete pairs, and SHALL enforce a maximum of ten complete points.

#### Scenario: World map is clicked without a source draft
- **WHEN** Add Control Point mode has no selected source position
- **THEN** no point is persisted and the interface instructs the user to select the source image first

#### Scenario: Draft is cancelled
- **WHEN** the user cancels after selecting only the source position
- **THEN** the draft marker is removed and no database record is created

### Requirement: Existing transformation and publication contract
The page SHALL use two complete points for a similarity transform, three through ten for affine least squares, source coordinates `(image_x, -image_y)`, preview-only Calculate, and transactional Save publication.

#### Scenario: Calculate succeeds
- **WHEN** at least two complete points are available and the user chooses Calculate
- **THEN** a preview result is shown without marking the dataset publication completed

#### Scenario: Save succeeds
- **WHEN** calculation inputs remain valid and the user chooses Save
- **THEN** the final managed raster and tiles are published with the completed configuration and dataset state

### Requirement: Return to workspace records
The georeference route SHALL accept a validated in-application return destination and SHALL return to the originating workspace Database view after successful save.

#### Scenario: Return destination is absent or unsafe
- **WHEN** the route has no valid internal workspace destination
- **THEN** successful save returns to the georeferenced dataset's own Database view
