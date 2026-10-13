## ADDED Requirements

### Requirement: Dataset detail preserves explicit legend metadata
The dataset-detail response SHALL expose an explicit `metadata.legend` object when it exists in stored dataset metadata and SHALL not create a legend from color values alone.

#### Scenario: Dataset has an explicit stored legend
- **WHEN** a dataset detail request retrieves metadata containing a valid legend object
- **THEN** the response includes that object unchanged for the Dataset Map to render

#### Scenario: Dataset has no explicit or extracted legend
- **WHEN** a dataset detail request retrieves metadata without a legend
- **THEN** the Dataset Map states that visual meaning is not specified by the dataset rather than inventing a semantic legend

### Requirement: Raster color tables are exposed deterministically
Raster metadata extraction SHALL include a compact `metadata.legend` only when the source raster provides a readable color map. Every derived item SHALL retain its source value and color and SHALL use a non-semantic value label unless the source metadata provides a label.

#### Scenario: Raster has a source color map
- **WHEN** a supported single-band raster contains a readable Rasterio color map
- **THEN** its metadata includes a raster legend with the exact source value and color mapping

#### Scenario: Raster has no source color map
- **WHEN** a raster does not provide a readable color map
- **THEN** metadata does not assign labels such as water, roads, vegetation, heat, or risk based on rendered colors

### Requirement: Dataset facts only render known values
The Dataset Map SHALL show filename, file type, file size, CRS, bounds, dimensions, bands, georeferencing status, processing status, and tile status only when the dataset response supplies those values.

#### Scenario: Dataset has partial metadata
- **WHEN** a dataset omits optional metadata such as CRS, bounds, or bands
- **THEN** the information panel omits those fields instead of displaying a fabricated default

### Requirement: Base map semantics are not fabricated
The Dataset Map SHALL identify the configured base map as a reference map unless its selected style provides usable semantic metadata.

#### Scenario: Configured raster base map has no semantic metadata
- **WHEN** the Dataset Map uses the existing raster base-map configuration
- **THEN** the information panel does not label base-map colors or lines as specific real-world features
