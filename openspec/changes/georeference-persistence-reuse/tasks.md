## 1. SQLAlchemy persistence foundation

- [x] 1.1 Add SQLAlchemy and declarative records for existing datasets/control points plus georeference configurations and user points.
- [x] 1.2 Replace the raw psycopg implementation behind `DatabaseSession` while preserving existing function-facing methods and transaction behavior.
- [x] 1.3 Add an additive PostgreSQL migration with one-active-config enforcement and no destructive statements.

## 2. Georeference calculation and persistence

- [x] 2.1 Calculate similarity and affine parameters with `(image_x, -image_y)` and produce the equivalent Rasterio transform.
- [x] 2.2 Separate calculate/preview from transactional Save Georeference and persist actual configuration/output values.
- [x] 2.3 Add safe failure rollback/output cleanup and invalidate stale configurations after control-point edits.
- [x] 2.4 Add the current-configuration GET contract, reuse compatibility result, and dataset-detail summary.

## 3. User-point isolation

- [x] 3.1 Add independent user-point CRUD functions, request/response schemas, and API routes.
- [x] 3.2 Load and render user points as a separately controlled red Dataset Map layer without including them in georeferencing.

## 4. Frontend saved workflow

- [x] 4.1 Restore saved configuration and control points on route load with race-safe parallel requests.
- [x] 4.2 Add distinct Calculate and Save Georeference controls plus database-backed status details.
- [x] 4.3 Add inspect-only Reuse Configuration and Edit Georeferencing states with compatibility warnings.
- [x] 4.4 Display saved georeferencing values in Dataset Map information without hardcoding.

## 5. Verification

- [x] 5.1 Add focused persistence, coordinate-convention, reload/reuse, edit/delete, user-point isolation, and rollback tests.
- [x] 5.2 Run backend tests/compilation, frontend build, strict OpenSpec validation, and diff checks.
- [x] 5.3 Validate calculate/save/reload/reuse/edit and point-layer behavior in the browser with console and screenshot evidence.
