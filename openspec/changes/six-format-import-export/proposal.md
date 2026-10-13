## Why

The application currently has separate upload, project-import, and export paths with inconsistent format support, incomplete project packages, and no reliable download state handling. A single six-format subsystem is needed so users can move complete projects and geospatial data into and out of the existing workspace without losing data or trusting unsafe archives.

## What Changes

- Unify detection, validation, persistence, and structured errors for `.mtmap`, `.gpkg`, `.geojson`, `.tif`/`.tiff`, MapLibre style `.json`, and `.mbtiles` imports while preserving the existing raster and OSM upload formats.
- Replace permissive `.mtmap` ZIP extraction with a versioned manifest, bounded archive validation, path-safe extraction, transactional ID remapping, file hashes, and deterministic cleanup.
- Export complete `.mtmap` packages and truthful single-format GeoPackage, GeoJSON, GeoTIFF, MapLibre style JSON, and MBTiles artifacts using only existing project data and generated outputs.
- Add GeoPackage vector inspection/conversion, GeoJSON validation/preview, MapLibre style validation, and MBTiles metadata/tile access integrated with the existing dataset and MapLibre paths.
- Update upload/open-project affordances and implement an explicit export dropdown state machine with Axios Blob downloads, filename handling, duplicate-click prevention, recovery, and accessible status feedback.
- Add a round-trip format matrix covering valid, corrupt, unsupported, missing-artifact, deduplicated, and browser download/import workflows.

## Capabilities

### New Capabilities

- `format-import`: Safe detection, validation, persistence, and map-ready import behavior for all six required formats.
- `format-export`: Truthful, downloadable exports for complete projects, vector data, raster data, styles, and generated tile archives.
- `portable-map-project`: Versioned and secure `.mtmap` package creation and transactional round-trip restoration.
- `import-export-interface`: Upload/open-project guidance and a resilient export state machine in the existing React workspace.

### Modified Capabilities

None. There is no baseline `openspec/specs` directory, and related capabilities are still represented only by unarchived change artifacts.

## Impact

- Backend upload validation and metadata extraction, dataset/project persistence, import/export services, tile reads, and API routes.
- Local managed storage for source files, generated exports, and imported project assets; PostgreSQL remains the source of truth.
- Existing React/Vite API helpers, upload/home views, dataset toolbar, and MapLibre data selection.
- Existing Python geospatial dependencies (`rasterio`, `pyogrio`/GDAL) and browser Axios downloads; no Supabase or replacement application is introduced.
- Focused backend tests, frontend build checks, package inspection, format round trips, and real browser validation.
