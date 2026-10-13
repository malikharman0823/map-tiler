## Why

The application currently treats each dataset as an isolated map and spreads upload, inspection, layer controls, and georeferencing across disconnected pages. The redesign creates one coherent dataset-centered studio where users can ingest a raster bundle, resolve missing georeferencing, combine datasets logically, inspect database-backed records, and manage map layers without losing context.

## What Changes

- **BREAKING** Replace the visible individual-format upload flow with ZIP-only raster-bundle ingestion containing exactly one raster plus optional world-file and CRS sidecars.
- Route georeferenced uploads directly to a unified workspace; route unreferenced uploads through a Georeference-or-Database decision.
- Add persistent dataset workspaces that attach multiple datasets without physically merging their database rows or files.
- Add Photoshop-style parent/sublayer ordering, visibility, and raster opacity with synchronized Map and Database views.
- Add a Supabase-style, server-driven database grid for raster, control-point, and user-icon records with curated editing only.
- Redesign the georeference page with numbered black source-image points, matching blue world-map points, responsive layout, and return-to-workspace behavior.
- Preserve the current FastAPI, SQLAlchemy, MapLibre, raster publication, point persistence, export, and managed-storage architecture.

## Capabilities

### New Capabilities

- `raster-zip-ingestion`: Secure ZIP-only raster bundle validation, metadata extraction, georeference detection, and post-upload routing.
- `dataset-workspace`: Persistent primary-dataset workspaces with reusable attached datasets, layer state, map state, and Map/Database navigation.
- `workspace-table-editor`: Typed, paginated workspace records with synchronized selection and curated record editing.
- `responsive-georeference-workflow`: Responsive source/map pairing, numbered marker presentation, calculate/save separation, and workspace return flow.

### Modified Capabilities

None. The repository has no promoted base specifications; existing change specifications remain historical inputs and are not rewritten by this change.

## Impact

- Backend SQLAlchemy models, additive migration, workspace aggregation services, ZIP validation/import, and FastAPI routes.
- Frontend routing, upload page, dataset workspace, MapLibre layer orchestration, table/editor components, and georeference presentation.
- New headless table and accessible sortable-list dependencies, pinned at implementation time to current stable releases.
- Existing datasets and saved georeferences require additive backfill only; no destructive data migration is permitted.
