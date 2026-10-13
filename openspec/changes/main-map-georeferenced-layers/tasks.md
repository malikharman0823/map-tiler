## 1. Backend publication contract

- [x] 1.1 Add raster-derived WGS84 bounds and completed tile-source metadata to the existing dataset-detail response.
- [x] 1.2 Validate completed managed outputs with `RASTER_OUTPUT_NOT_FOUND` and `TILE_SOURCE_NOT_FOUND` application errors.
- [x] 1.3 Make `action=save` run the existing georeference, raster-processing, and tile-generation pipeline before returning success, and mark partial publication failed.

## 2. Main-map consumption

- [x] 2.1 Gate floor-plan and control-point map data on the completed `map_layer` contract while keeping icon points independent.
- [x] 2.2 Use the dynamic dataset name, saved raster bounds, independent toggles, and floor-plan-only opacity in the existing inspection workspace.
- [x] 2.3 Update the existing MapLibre raster source/layer without duplicates and fit automatically only once per completed dataset.
- [x] 2.4 Simplify Save Georeference to one publication request and navigate to refreshed main-map state after success.

## 3. Verification

- [x] 3.1 Add focused backend tests for completed layer metadata, bounds, missing outputs, publication failure, and dataset isolation.
- [x] 3.2 Run backend checks where the environment permits, frontend build, strict OpenSpec validation, and review the scoped diff.
- [ ] 3.3 Validate save/reload, raster alignment, point alignment, layer toggles, opacity, Fit Dataset, pan/zoom/resize, console health, and responsive layout in a real browser.
