## 1. Format foundation

- [x] 1.1 Add normalized validation and metadata extraction for GeoJSON, GeoPackage, MBTiles, and MapLibre style JSON while retaining existing upload safeguards.
- [x] 1.2 Add bounded vector preview and validated MBTiles tile-read services plus API routes.
- [x] 1.3 Connect imported vector, raster MBTiles, vector MBTiles, and style datasets to the existing dataset-detail/MapLibre flow.

## 2. Portable project packages

- [x] 2.1 Replace `.mtmap` export with a versioned manifest, deterministic project document, hashes, and only existing declared assets.
- [x] 2.2 Replace `.mtmap` import with bounded path-safe validation/extraction, hash checks, ID remapping, transaction handling, and filesystem cleanup.
- [x] 2.3 Prove `.mtmap` export/import round-trip equivalence and malicious/corrupt archive rejection in focused tests.

## 3. Single-format exports

- [x] 3.1 Implement lossless/generated GeoJSON and vector-only GeoPackage exports with preserved attributes.
- [x] 3.2 Implement truthful GeoTIFF and MapLibre style JSON exports with structured unavailable errors.
- [x] 3.3 Implement MBTiles passthrough or generation from completed directory tiles, including metadata, TMS rows, validation, and temporary cleanup.

## 4. Frontend import and export experience

- [x] 4.1 Update dataset upload accepted formats/copy while retaining an explicit `.mtmap` Open Project action.
- [x] 4.2 Add Axios Blob downloading, `Content-Disposition` parsing, safe fallback filenames, and structured Blob error decoding.
- [x] 4.3 Implement the closed/open/exporting/success/error dropdown state machine with outside-click/Escape handling and duplicate protection.
- [x] 4.4 Make Save Project persist current configuration and download the resulting `.mtmap` package.

## 5. Verification

- [x] 5.1 Add focused backend tests for the six-format validation/export matrix, cleanup, deduplication, SQLite/ZIP integrity, and tile rows.
- [ ] 5.2 Run backend tests, frontend build, strict OpenSpec validation, and scoped diff review without claiming blocked checks.
- [ ] 5.3 Start/reload the application and validate real browser upload, map display, all six downloads, failure recovery, and `.mtmap` re-import with console/network evidence.
