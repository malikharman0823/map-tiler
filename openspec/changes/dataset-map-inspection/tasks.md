## 1. Dataset metadata and API contract

- [x] 1.1 Extract raster nodata, color interpretation, and source color-table legend metadata without assigning semantic labels.
- [x] 1.2 Verify the existing dataset-detail response exposes stored and derived metadata without adding an endpoint or database table.

## 2. Read-only map inspection workspace

- [x] 2.1 Load dataset and stored control points together on the Dataset Map route, with cancellation and scoped optional-data errors.
- [x] 2.2 Refactor the shared MapLibre component so data, selected control points, visibility settings, and opacity update in place.
- [x] 2.3 Add selectable labeled control-point layers, popup details, and map focus behavior using actual returned values.

## 3. Information rail

- [x] 3.1 Add a compact responsive information rail with dataset facts, deterministic legend output, control-point list/detail, and base-map context.
- [x] 3.2 Add independent base-map, dataset, and control-point visibility controls plus the existing dataset opacity control.

## 4. Verification

- [x] 4.1 Add focused backend checks for raster legend metadata and metadata preservation.
- [x] 4.2 Build the frontend and run backend compilation checks.
- [x] 4.3 Validate control-point selection, layer visibility, legend fallback, reload behavior, and mobile layout in the browser.
