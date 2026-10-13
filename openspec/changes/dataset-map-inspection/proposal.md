## Why

The Dataset Map currently displays the dataset and a minimal status card, but it does not expose stored control points or enough verified context to help users inspect what they are seeing. This makes it difficult to confirm georeferencing references and to distinguish documented dataset meaning from unspecified map styling.

## What Changes

- Add a read-only dataset-map inspection workspace that loads stored control points alongside the dataset detail.
- Display selectable, labeled control-point markers on the existing MapLibre map, with popups and a compact detail/list panel driven by actual database values.
- Add collapsible dataset-information, dataset-legend, and layer-visibility sections without rebuilding the MapLibre map when UI state changes.
- Expose deterministic metadata that can be derived from source datasets, including raster technical properties and explicit raster color tables when present.
- Render only legends supplied by stored dataset metadata or reliably extracted style/classification information; clearly state when a dataset does not specify visual meaning.

## Capabilities

### New Capabilities

- `dataset-map-inspection`: Read-only map workspace behavior for selecting and inspecting stored control points, dataset information, layer visibility, and verified legend context.
- `dataset-legend-metadata`: Deterministic metadata and response behavior for explicit dataset legends and source-provided raster classifications.

### Modified Capabilities

- None.

## Impact

- Frontend: `DatasetPage`, the reusable MapLibre map component, API client, and scoped map-inspection components/styles.
- Backend: dataset metadata extraction and the existing dataset-detail response; no new tables or public endpoints are required.
- Persistence: optional legend data remains in the existing dataset metadata JSON field.
