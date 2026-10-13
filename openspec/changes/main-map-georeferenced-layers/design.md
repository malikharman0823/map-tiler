## Context

The current checkout already has one MapLibre map, persisted georeference configurations, separate control-point and icon-point tables, raster reprojection, XYZ tile generation, and independent layer toggles. Gemini also chained Save Georeference to the process and tile endpoints in the browser. The missing contract is that the backend save endpoint can report success before tiles exist, dataset detail exposes no raster-derived geographic extent, the map falls back to control-point bounds, and points can be displayed before a completed saved georeference exists. `PRD.md` and `tech stack.md` are not present in this checkout, so the repository code, README, package manifests, existing OpenSpec changes, and attached objective are the available sources of truth.

## Goals / Non-Goals

**Goals:**

- Make a successful Save Georeference response mean that the managed GeoTIFF, Web Mercator processed raster, and XYZ tiles are all ready for the main map.
- Extend dataset detail with a small, self-describing completed map-layer contract whose bounds come from the saved raster and are normalized to WGS84 for MapLibre camera use.
- Gate the saved floor-plan and control-point layers on a completed active georeference while keeping icon points independent.
- Preserve one MapLibre instance and update existing sources/layers in place, with the required ordering, toggles, opacity, refresh, and fit behavior.
- Use existing structured application errors and portable relative paths.

**Non-Goals:**

- A new mapping library, map page, tile service, database table, job queue, georeference history UI, or arbitrary browser-side GeoTIFF renderer.
- Replacing the existing synchronous MVP pipeline with background jobs.
- Changing the stored control-point or icon-point schemas.

## Decisions

### Treat the existing save route as the publication boundary

For `action=save`, the FastAPI route will call the existing georeference writer, raster processor, and tile generator in sequence and return success only after all three finish. Calculate remains preview-only. If publication fails after the configuration was written, the dataset and active configuration are marked failed so the main map cannot expose a partial result. The browser will stop making separate process/tile calls and will refresh by navigating through React routing after the successful response.

Alternative considered: retain three browser calls. Rejected because a dropped browser request can leave a configuration marked completed with no map layer, and direct API callers would receive a misleading save success.

### Derive map bounds from the managed georeferenced output

Dataset detail will validate the active completed configuration and managed files, open the saved georeferenced raster, and transform its exact bounds from the stored raster CRS to EPSG:4326 with Rasterio. The response will expose `min_longitude`, `min_latitude`, `max_longitude`, and `max_latitude`, plus tile URL/zoom metadata and the dataset display name. MapLibre camera fitting will use only these bounds for the saved raster; control points will no longer define the floor-plan extent.

Alternative considered: store new bound columns. Rejected because the GeoTIFF is already the authoritative persisted output and the MVP can derive four values cheaply without a migration.

### Keep availability explicit and failures structured

Datasets with no completed active configuration receive no `map_layer` object, so ordinary uploads remain inspectable. A completed configuration whose managed raster or tiles are missing fails dataset-detail loading with `RASTER_OUTPUT_NOT_FOUND` or `TILE_SOURCE_NOT_FOUND`. Tile access also distinguishes incomplete georeferences. Internal absolute paths and raw Rasterio/filesystem errors remain hidden.

Alternative considered: silently omit a broken completed layer. Rejected because it would make a corrupt saved state indistinguishable from an unfinished dataset.

### Preserve and update the existing MapLibre layer architecture

The existing raster source/layer remains between the base map and both point types. GeoJSON sources use `setData`; layer visibility and raster opacity use MapLibre style setters. If the raster URL or availability changes, the existing dataset layer/source is removed in dependency order and replaced, preventing duplicate layers. A per-dataset ref makes automatic fit happen once, while the explicit Fit Dataset action remains repeatable.

Alternative considered: add an image/CSS overlay or create a second map. Rejected because it would not remain geographically anchored and would duplicate the current architecture.

## Risks / Trade-offs

- [Synchronous tile generation can make Save slow] -> retain the existing ten-minute frontend timeout and bounded generated tile workflow; background jobs remain out of scope.
- [A failure after the GeoTIFF commit cannot roll back filesystem and database state atomically] -> mark the active publication failed, keep paths portable, clean partial tile output through existing helpers, and allow a later Save to replace it.
- [Reading raster metadata on dataset detail adds file I/O] -> read headers only; no raster pixels are loaded.
- [The checked-in Python venv is not executable in the current environment] -> add focused tests and run them when a usable interpreter is available; still run frontend build, OpenSpec validation, and browser checks against any available runtime.

## Migration Plan

1. Deploy backend response/orchestration changes; no schema migration is required.
2. Deploy the frontend to consume `map_layer`, gate control points, and use a single save request.
3. Existing completed datasets with intact outputs/tiles become available immediately; incomplete or broken outputs remain hidden or return a structured error until re-saved.
4. Rollback restores the previous three-call frontend flow and ignores the additive response field.

## Open Questions

None. Saved georeferences remain EPSG:4326 in the current workflow and are reprojected to EPSG:3857 by the existing tile pipeline; the map-layer contract always publishes WGS84 camera bounds.
