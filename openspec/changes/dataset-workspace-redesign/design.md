## Context

The checkout already has FastAPI and SQLAlchemy persistence for datasets, map projects, control points, icon points, and georeference configurations. It also has a single-dataset MapLibre workspace and a flat workspace-record endpoint, but no persisted many-dataset workspace, no database-editor page, and no ZIP-only raster-bundle workflow. The worktree contains active uncommitted changes, so the redesign must be additive and preserve current files, database rows, generated rasters, and export contracts.

## Goals / Non-Goals

**Goals:**

- Make a dataset's map project the persistent container for a primary dataset plus reusable attached datasets.
- Provide synchronized, responsive Map and Database views with collection-level layer controls.
- Accept a secure ZIP containing one raster and optional georeference sidecars, then route deterministically from extracted metadata.
- Preserve the current georeference mathematics and publication transaction while replacing its presentation and navigation.
- Keep public responses portable by exposing managed relative paths instead of resolved machine paths.

**Non-Goals:**

- Supabase hosting, authentication, organizations, collaboration, or concurrent editing.
- Physical merging of source datasets, arbitrary multi-raster archives, vector-bundle ingestion, advanced raster styling, or background jobs.
- Direct database-grid editing of identifiers, paths, CRS, bounds, processing status, or control-point coordinates.

## Decisions

### Normalize workspace membership

Add a `workspace_members` association from `map_projects` to `datasets`. The map project's existing `dataset_id` remains the primary dataset; every project also receives a membership row for that dataset. Membership rows store alias, sort order, parent and child visibility, and raster opacity with a unique `(map_project_id, dataset_id)` constraint. This provides referential integrity and allows one dataset to be reused in multiple workspaces.

Alternative considered: store dataset IDs and settings only in `map_projects.configuration`. Rejected because stale IDs, duplicate attachments, ordering updates, and detach behavior would depend on unchecked JSON.

### Keep workspace UI state separate from member state

Active Map/Database view and the latest map camera remain in `map_projects.configuration`. Member settings use typed columns and autosave independently. Curated record fields keep explicit Save/Cancel behavior so partially edited text is never persisted by navigation.

### Import a raster bundle through a dedicated bounded service

`POST /datasets/import-zip` accepts only ZIP input and securely enumerates regular files before extraction. A bundle must resolve to exactly one supported raster; matching world and CRS sidecars are optional. Embedded or sidecar metadata count as georeferenced only when both a usable CRS and affine transform exist. The existing `/upload` route remains as a compatibility alias but the redesigned UI does not expose individual-file inputs.

Alternative considered: reuse the portable map-project archive importer. Rejected because a source raster bundle has a different trust model and does not contain the application's manifest or saved records.

### Return an aggregate workspace manifest and typed record union

Workspace loading returns the project, ordered member summaries, per-sublayer counts/settings, and dataset map-layer contracts. A separate paginated records endpoint returns discriminated raster, control-point, or icon-point objects with raw numeric coordinates and relative paths. The frontend formats display strings.

Alternative considered: retain the current flat record response with formatted strings and absolute paths. Rejected because it is not safely sortable/filterable, is not portable, and mixes presentation with data.

### Use one shared frontend workspace controller

One route-level controller owns manifest loading, selection, filters, map camera, autosave sequencing, dirty curated edits, and scoped refreshes. Map and Database are sibling views over that state. TanStack Table provides controlled server-side grid state; dnd-kit provides handle-based pointer, touch, and keyboard ordering. Dependencies are pinned to current stable releases in the lockfile.

Alternative considered: keep independent page effects and component-local copies. Rejected because table/map selection and autosave would race or duplicate requests.

### Namespace MapLibre resources per member

Each member uses deterministic source and layer IDs based on its dataset ID. Visibility changes use layout properties, raster opacity uses paint properties, point updates use GeoJSON source data updates, and reordering uses layer moves while keeping point groups above their raster. Detach removes layers before sources.

### Preserve georeference persistence semantics

The georeference page retains source-first pairing, explicit placement/cancel modes, two-point similarity, three-to-ten-point affine fitting, `(image_x, -image_y)`, Calculate versus Save, and transactional publication. A `returnTo` query value controls the post-save workspace destination; it never changes backend persistence.

## Risks / Trade-offs

- [A large workspace can cause N+1 queries] -> aggregate members and their point counts/records in bounded batch queries and paginate table rows.
- [Autosave responses can arrive out of order] -> serialize member/state mutations per resource and retain failed values for explicit retry.
- [ZIP extraction can exhaust disk or traverse paths] -> reuse bounded archive limits, reject links and traversal, stage extraction, and clean staged files on failure.
- [Mobile layer dragging can block scrolling] -> use a dedicated drag handle with touch behavior limited to the handle and retain keyboard move controls.
- [Existing project configuration varies] -> perform an idempotent additive backfill and preserve unknown configuration keys.
- [Browser success is not proven by builds] -> validate actual MapLibre network requests, console output, selection, and responsive interactions in a connected browser.

## Migration Plan

1. Add `workspace_members`, indexes, checks, ORM methods, and an idempotent migration/backfill without deleting existing data.
2. Deploy aggregate workspace and record APIs while retaining current dataset/project routes.
3. Add the new workspace route and keep `/datasets/:id` as a temporary compatibility entry before making it a redirect.
4. Enable ZIP-only UI ingestion and georeference routing after the new workspace route is available.
5. Rollback removes application use of membership rows and restores the old route; the additive table and imported datasets can remain safely unused.

## Open Questions

None. The approved defaults are a single-user local application, logical rather than physical merging, collection-level point toggles, relative managed paths, and a fully responsive interface.
