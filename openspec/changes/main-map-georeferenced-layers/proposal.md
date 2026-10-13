## Why

Saving a georeference currently creates a GeoTIFF and the frontend then processes and tiles it, but the main map does not receive authoritative geographic bounds from that saved output and can expose point layers before the georeference is completed. The saved result therefore cannot yet be treated as one durable, self-describing geographic layer after reload.

## What Changes

- Expose a completed dataset's saved georeferenced map-layer metadata, including actual raster-derived WGS84 bounds, CRS, tile availability, tile URL, and dynamic dataset name.
- Make Save Georeference complete the existing georeference, processing, and tile-generation pipeline before the UI reports success, then navigate back to refreshed dataset state.
- Load the floor plan and its saved control points on the main map only when the active georeference and geographic output are completed; keep icon points independent.
- Fit from the saved raster extent, never from control points, and keep World Map, Floor Plan, Control Points, and Icon Points independently toggleable in the required render order.
- Return structured application errors for incomplete/missing saved geographic outputs without exposing internal paths or stack traces.
- Add focused backend and frontend/browser validation for save, reload, layer isolation, opacity, fit, and refresh behavior.

## Capabilities

### New Capabilities

- `main-map-georeferenced-layers`: Durable publication and main-map consumption of a saved georeferenced raster, its control points, and independent icon points.

### Modified Capabilities

None. The related capabilities are still in active, unarchived changes and there is no baseline `openspec/specs` capability to modify.

## Impact

- Backend dataset-detail/georeference responses, saved-output validation, raster-bound conversion, and existing pipeline orchestration.
- Frontend georeference save flow, dataset-map state, MapLibre layer lifecycle, layer labels, fit behavior, and structured error display.
- Focused tests for completed-only exposure, real raster bounds, missing outputs, reload, and MapLibre interaction behavior.
- No new map library, database table, machine-specific file path, or duplicate map implementation.
