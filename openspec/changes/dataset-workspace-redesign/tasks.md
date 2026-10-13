## 1. Workspace persistence and APIs

- [x] 1.1 Add the workspace-membership ORM model, constraints, migration/backfill, and database facade methods.
- [x] 1.2 Add typed workspace manifest and record response models with portable managed paths.
- [x] 1.3 Add workspace load, attach, detach, member patch, state patch, and paginated record routes.
- [x] 1.4 Add focused backend tests for backfill, reuse, settings, detach-only behavior, record querying, and validation.

## 2. ZIP raster ingestion

- [x] 2.1 Add bounded ZIP inspection/extraction for exactly one raster plus optional matching world/CRS sidecars.
- [x] 2.2 Add deterministic embedded/sidecar georeference detection and the ZIP import endpoint with `/upload` compatibility.
- [x] 2.3 Add backend tests for valid bundles, unsafe archives, ambiguous rasters, cleanup, and routing metadata.
- [x] 2.4 Replace the upload interface with ZIP-only selection, progress, success routing, and the unreferenced decision dialog.

## 3. Unified workspace frontend

- [x] 3.1 Add stable TanStack Table and dnd-kit dependencies and the shared workspace API client/controller.
- [x] 3.2 Build responsive workspace routing, shell, top actions, layer tree, sheets, and bottom Map/Database navigation.
- [x] 3.3 Extend MapLibre rendering to ordered namespaced members with visibility, opacity, selection, fit, and cleanup.
- [x] 3.4 Build the server-driven database grid, filtering, pinned columns, responsive editor, and curated Save/Cancel flows.
- [x] 3.5 Add secondary ZIP confirmation, attach/detach, georeference routing, autosave feedback, retry, and dirty-navigation protection.

## 4. Georeference redesign

- [x] 4.1 Restyle source and reference markers as matching numbered black/blue pairs with accessible selected states.
- [x] 4.2 Make the paired workspace responsive and implement safe return-to-workspace navigation after Save.
- [x] 4.3 Add or update focused tests for pairing, cancellation, transformation boundaries, save return, and member refresh.

## 5. Validation and handoff

- [x] 5.1 Run backend focused and regression tests plus compilation.
- [x] 5.2 Run the frontend production build and address build/runtime warnings in changed code.
- [x] 5.3 Validate the OpenSpec change strictly and run whitespace/diff checks.
- [ ] 5.4 Exercise upload, workspace, table, multi-layer map, georeference, persistence, detach, error, and responsive flows in a real browser when available.
  - Blocked in this run: the browser runtime reported no connected browser session.
