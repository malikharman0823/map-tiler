## Context

The existing application stores one primary source file per dataset, derives raster/tile paths, stores flexible extracted metadata as JSON, and associates one map project plus control/icon points with the dataset. Uploads are streamed and deduplicated by SHA-256, but project import bypasses those services, extracts ZIPs unsafely, invents metadata and hashes, and commits incomplete records. Export currently serializes only a small subset of project state and supports no GeoPackage or MBTiles generation. The frontend uses direct anchor navigation, so export failures cannot enter a recoverable UI state.

The implementation must remain in the current FastAPI/SQLAlchemy/PostgreSQL and React/Vite/MapLibre application. Existing raster, georeference, directory-tile, PBF-preview, and project-editing behavior must continue to work. The repository has substantial uncommitted work, so changes must be additive and avoid unrelated cleanup.

## Goals / Non-Goals

**Goals:**

- Give all six required formats an explicit, testable import and export contract.
- Treat `.mtmap` files as untrusted, versioned portable projects with bounded extraction and transactional restoration.
- Preserve original source artifacts where that is the most faithful export and generate standards-compatible derivatives from current database/storage state where required.
- Make imported vector, raster, style, and MBTiles sources viewable through the existing dataset map.
- Make every export an Axios Blob workflow with deterministic filenames and an explicit recoverable UI state.
- Reuse the existing hash, storage, project, point, raster, and tile-generation models without introducing Supabase or a parallel application.

**Non-Goals:**

- A general-purpose desktop GIS conversion engine or arbitrary styling editor.
- Raster layers inside GeoPackage; GeoPackage support is vector-only.
- Rebuilding arbitrary remote resources referenced by imported MapLibre styles.
- Persisting generated export caches as database entities; exports are derived artifacts.
- Multi-file batch export UI in this change.

## Decisions

### Use one normalized format descriptor in dataset metadata

`metadata.format`, `metadata.category`, and format-specific fields will drive preview and export eligibility. This uses the existing JSON metadata column and avoids a risky schema migration while keeping the database the source of truth. Alternatives considered were new format/layer tables or filename-only branching; the former is disproportionate for the current one-source dataset model and the latter cannot reliably distinguish `.json` structures or MBTiles tile types.

### Keep dataset upload and project import distinct

The existing `/upload` route will accept individual data/style formats. `/map-projects/import` will remain the explicit `.mtmap` project operation and will return the restored project. This preserves the current UI distinction and prevents an archive from silently entering the simpler dataset pipeline.

### Build format operations behind reusable service functions

Metadata validation, vector conversion, MBTiles inspection/read/write, manifest creation, safe archive extraction, and download response construction will live in backend function modules and be called by the existing routes. No second API or application layer will be created.

### Use original sources for lossless same-format export

Imported GeoPackage, GeoJSON, MapLibre style JSON, GeoTIFF, and MBTiles sources will be returned directly when valid and current. For other projects, GeoJSON and GeoPackage are generated from the available project vector features, GeoTIFF uses the current georeferenced/source raster, and MBTiles is generated from the existing completed directory-tile output. This avoids claiming conversions that the current project cannot perform faithfully.

### Use pyogrio/GDAL for GeoPackage and a small WKB bridge

`pyogrio.list_layers`, `read_info`, and low-level OGR read/write APIs will inspect and convert vector layers. A bounded WKB-to/from-GeoJSON bridge keeps the dependency footprint aligned with the installed stack instead of adding GeoPandas. Coordinate transformation to WGS84 will use PyProj when the input CRS requires it.

### Treat MBTiles as validated SQLite, not as a ZIP

Import validates the SQLite header, `metadata` and `tiles` tables, at least one tile row, zoom range, format, and optional bounds/vector-layer metadata. Tile reads convert XYZ `y` to the MBTiles TMS row. Export writes metadata plus existing generated tiles in a transaction and validates the resulting archive before download.

### Define `.mtmap` version 1 as a deterministic package

The root contains `manifest.json` and `project.json`; optional existing assets use `style/`, `data/`, `raster/`, `tiles/`, `icons/`, and `metadata/`. The manifest records schema version, logical roles, paths, byte sizes, and SHA-256 hashes. Import rejects absolute/traversal paths, links, duplicate names, encrypted entries, excessive entry count, oversized members, excessive expanded size/compression ratios, unsupported versions, missing declared files, and hash mismatches. It extracts only validated regular files to a temporary directory, creates new IDs, stages managed files, inserts all database rows in one transaction, and removes staged files on failure.

### Keep generated-file lifetime tied to the response

FastAPI `FileResponse` will supply media type and `Content-Disposition`; temporary generated artifacts will be removed with a response background task after streaming. Original managed sources are never removed by export cleanup.

### Use an explicit frontend state machine

The export control has `closed`, `open`, `exporting`, `success`, and `error` states. Format selection closes the menu, starts one Axios Blob request, disables duplicate requests, parses `Content-Disposition`, uses a sanitized project-name fallback, revokes the object URL, and leaves an accessible success/error message. Outside click and Escape close only the open menu; failures always return to an actionable control.

## Risks / Trade-offs

- [Large GeoJSON or GeoPackage previews can exhaust browser memory] → Bound preview feature count and response size while preserving the complete stored source and export.
- [Arbitrary CRS conversion may be unavailable until PyProj is installed] → Declare PyProj in backend requirements and return a structured unsupported-CRS error instead of drawing wrong coordinates.
- [Imported MapLibre styles can reference unavailable remote resources] → Validate the style structure, preserve it exactly, and surface MapLibre resource errors without rewriting URLs or embedding secrets.
- [Filesystem operations cannot share the database transaction] → Stage in a temporary directory, move only validated files into a new dataset directory, commit once, and remove that directory on rollback.
- [Vector MBTiles need source-layer information to render] → Read standard `json.vector_layers` metadata and return a structured preview limitation when it is absent rather than fabricating layer names.
- [Generated MBTiles can be large] → Stream directory traversal into SQLite, avoid loading tile blobs together, and clean the temporary file after the response.
- [The running backend may not auto-reload] → Validate modules in an isolated test runtime and explicitly report if the user-started listener still serves stale code.

## Migration Plan

1. Add normalized metadata extraction and preview/tile services without changing existing records.
2. Route new uploads through the existing streaming/hash pipeline; old records continue to use filename fallbacks.
3. Replace project archive import/export with versioned services while retaining legacy `project.json` import compatibility only when it is otherwise safe.
4. Add new exports and frontend controls; existing endpoint paths remain stable.
5. Run unit/integration tests, inspect generated SQLite/ZIP artifacts, build the frontend, then validate real browser downloads and re-imports.

Rollback consists of reverting these service, route, frontend, requirement, test, and OpenSpec files. No database migration is required; uploaded source records remain compatible with the previous schema.

## Open Questions

- None blocking. For MapLibre style sources that require credentials or inaccessible remote hosts, successful structural import is guaranteed but external resource availability remains outside this application.
