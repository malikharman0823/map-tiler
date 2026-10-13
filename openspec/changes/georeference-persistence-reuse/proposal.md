## Why

The existing georeferencer writes a raster and updates dataset status, but it does not persist the calculated transformation, coordinate convention, source-image identity, or reusable configuration. A completed operation therefore cannot be reliably inspected, reproduced, or edited after the application reloads.

## What Changes

- Persist each dataset's current georeference configuration in PostgreSQL through SQLAlchemy, including actual transformation coefficients, source dimensions and identity, CRS values, coordinate convention, output information, status, and timestamps.
- Preserve control points as independent database records and update the active configuration instead of creating duplicate active rows.
- Separate transformation calculation/preview from the transactional Save Georeference operation and clean up newly generated files when persistence fails.
- Add a read API and dataset detail data for the active configuration, with safe reuse validation against dataset identity and source dimensions.
- Restore saved control points and configuration on the georeferencing page, with View, Reuse Configuration, and Edit Georeferencing states.
- Keep user points in their own PostgreSQL table and map layer so they never participate in georeferencing calculations.
- Correct the transformation convention to `(image_x, -image_y) -> (longitude, latitude)` in both calculation and preview.

## Capabilities

### New Capabilities

- `georeference-persistence`: Transactional storage of the current georeference configuration and generated-output metadata through SQLAlchemy.
- `georeference-reuse`: Loading, validating, inspecting, reusing, and editing a saved configuration without recalculation on read.
- `user-point-isolation`: Independent persistence and map display of user-created geographic points outside the control-point transformation set.

### Modified Capabilities

None. This repository has no baseline OpenSpec capabilities yet.

## Impact

- Backend database setup, models, georeference functions, dataset detail responses, API routes, and dependencies.
- A safe additive PostgreSQL migration for `georeference_configs` and `user_points`.
- Frontend API helpers, georeferencing workflow, dataset information panel, and map layers.
- Focused persistence, transformation, reuse, edit, isolation, and output-consistency tests.
