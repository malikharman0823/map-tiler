## Context

The georeferencer already persists control points and produces a GeoTIFF, but the database layer is currently a `psycopg` wrapper over dataclasses despite the requested SQLAlchemy architecture. The generated affine metadata and the frontend preview both currently use positive image Y, while the required convention is `(image_x, -image_y) -> (longitude, latitude)`. No saved configuration or user-point table is available in the active checkout.

## Goals / Non-Goals

**Goals:**

- Make PostgreSQL through SQLAlchemy the persistence boundary while preserving the existing `DatabaseSession` methods used by the function modules.
- Persist enough information to inspect and reproduce the exact transformation after reload.
- Keep calculation/preview separate from the explicit transactional save action.
- Make current configurations safe to reuse and edit without creating duplicate active rows.
- Keep user points independent from transformation control points.

**Non-Goals:**

- Full configuration history UI or restoration of inactive versions.
- Background processing, distributed queues, or a second ORM/database.
- Manual coefficient entry or semantic inference from raster content.

## Decisions

### Preserve the database facade while replacing its implementation

`DatabaseSession` remains the interface consumed by existing function modules, but it is backed by a SQLAlchemy 2.x synchronous `Session`. SQLAlchemy declarative records represent datasets, control points, georeference configurations, and user points. This avoids a repository-wide service rewrite while making the requested transaction boundary real. Keeping raw `psycopg` alongside an ORM was rejected because a single atomic save could not span both connections safely.

### Additive schema with one active row enforced by PostgreSQL

`georeference_configs` stores source identity (`dataset_id` plus source file hash), dimensions, CRS values, coordinate convention JSON, actual transformation parameters JSON, output metadata, status, timestamps, and `is_active`. A partial unique index on `dataset_id WHERE is_active` enforces one active row while allowing inactive history later. Saving updates the current active row for the MVP. `user_points` has its own foreign key and never joins the transformation query.

### Separate calculate from save on the existing endpoint

`POST /datasets/{id}/georeference` accepts an `action` of `calculate` or `save`. Calculate validates points, calculates actual parameters, and writes a replaceable preview GeoTIFF without persisting a completed configuration. Save repeats server-side validation/calculation, generates the managed final GeoTIFF, upserts the active configuration, updates the dataset, and commits. Recalculation during Save avoids trusting browser-supplied coefficients.

### Persist mathematical parameters in the required convention

Both similarity and affine solvers use source coordinates `[image_x, -image_y, 1]` and target coordinates `[longitude, latitude]`. Stored parameters are `{a,b,c,d,e,f}` for the equations in the brief. Rasterio receives the equivalent row-down transform `Affine(a, -b, c, d, -e, f)`. The frontend preview applies the persisted/source convention instead of independently using positive Y.

### Reuse is read-only until the user chooses Edit

`GET /datasets/{id}/georeference` returns the active configuration plus `reusable` and an optional reason. Reuse is permitted only when dataset ID, file hash, width, and height match. Reuse restores the saved parameters and points for inspection; Edit unlocks point changes. A point mutation marks the active configuration pending/stale so it cannot be silently reused until saved again.

### File and transaction consistency

Output is written to a temporary sibling and atomically replaced. On database failure after replacement, a newly written final file is removed when safe and the SQLAlchemy session is rolled back. Output paths stored in PostgreSQL are project-relative. Existing completed output is not deleted before the replacement has been generated successfully.

## Risks / Trade-offs

- **Database layer migration could affect existing functions** -> preserve method signatures and run focused CRUD plus compile/API tests against the new facade.
- **File replacement cannot be part of a PostgreSQL transaction** -> write atomically, retain the prior file until replacement, and clean a newly produced output on rollback.
- **Editing control points makes existing coefficients stale** -> mark the configuration pending and disable reuse until a successful save recalculates it.
- **SQLite tests differ from PostgreSQL JSONB/index behavior** -> use portable JSON with a PostgreSQL JSONB variant and include an explicit additive PostgreSQL migration.

## Migration Plan

1. Add SQLAlchemy to backend dependencies and map the existing tables without dropping or rewriting data.
2. Apply the additive migration that creates `georeference_configs`, `user_points`, indexes, and foreign keys only when absent.
3. Deploy backend API/model changes, then frontend reuse/edit controls.
4. Existing datasets remain `not_started` until newly saved; existing GeoTIFF-only outputs are not fabricated into configurations.
5. Rollback removes application use of the new tables; existing dataset/control-point data remains intact. The migration does not include destructive down SQL.

## Open Questions

None. Target CRS remains configurable in the saved record and defaults to `EPSG:4326` for the current longitude/latitude workflow.
