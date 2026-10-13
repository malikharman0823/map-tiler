## Context

The existing Dataset Map is a single MapLibre instance with optional raster tiles or a bounded PBF GeoJSON preview and a small overlay card. The existing API already returns persisted dataset metadata, and the control-point endpoint returns the complete geographic and source-image coordinates. The feature must remain read-only on this page, must preserve the existing storage and PostgreSQL schema, and must not infer semantic meaning from display colors.

## Goals / Non-Goals

**Goals:**

- Make stored control points visible and inspectable in the Dataset Map without requiring georeferencing mode.
- Keep dataset, control-point, and legend requests bounded to a single parallel load per dataset page entry.
- Add a compact responsive inspection rail containing control points, layer controls, dataset facts, and verified legend context.
- Extract only deterministic raster metadata, including a source color table when one exists.

**Non-Goals:**

- Editing, creating, dragging, or deleting control points from the Dataset Map.
- AI-based, color-only, or heuristic semantic classification.
- A new legend table, legend editing flow, style editor, or a complex layer manager.
- Claiming semantic information for the configured base map, whose raster tile source does not expose layer semantics.

## Decisions

### Keep legends in dataset metadata

The existing JSON metadata field remains the single persistence location for an explicit `legend`. Raster extraction adds `legend` only when Rasterio returns a source color map for a single-band raster; otherwise it leaves semantic meaning unspecified. This avoids schema migration and exposes the value through the existing dataset-detail response.

Alternative considered: a legend table and endpoint. Rejected because legends are dataset-scoped metadata, no authoring workflow is requested, and the detail response already carries metadata.

### Use a MapLibre GeoJSON control-point source

The map receives a control-point FeatureCollection and renders a circle plus a label layer. Selection updates source data, a popup, and map focus. Visibility uses MapLibre layer visibility settings, so layer toggles and selected points do not recreate the MapLibre map.

Alternative considered: HTML markers per point. Rejected because the map already uses layer-based rendering and a single source scales more predictably while retaining click-layer interaction.

### Keep map data and UI state separate

Dataset and control points load with one `Promise.all` effect tied to the route dataset ID and an AbortController cleanup. Panel expansion, visibility toggles, selected point, and opacity remain local UI state. The PBF preview is a separate conditional fetch because it applies only to PBF datasets.

Alternative considered: reload the detail endpoint after each UI interaction. Rejected because the data are read-only on this page and reloading would cause unnecessary requests and map churn.

### Distinguish base-map, dataset, and control-point information

The inspection rail labels each source separately. The base map is described only as a reference map because its configured raster tiles do not expose semantic layer metadata. Dataset legends are sourced exclusively from metadata. Control points are identified as stored georeferencing references and retain their database UUID in the detail view.

## Risks / Trade-offs

- [A raster color table may contain many entries] → cap display to the finite source palette and label values, without pretending the numeric categories have semantic labels.
- [MapLibre source/layer updates can race the initial `load` event] → gate all source and layer mutations behind a map-ready state and clean up the map on unmount.
- [Mobile map space is limited] → use a collapsed inspection panel with individually expandable sections and 44px controls.
- [Optional control-point or legend requests fail] → retain any available dataset map and surface a scoped inline status rather than block the page.
