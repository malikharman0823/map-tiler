## 1. Backend export contract

- [x] 1.1 Replace format-specific export builders with the validated MapTiler folder ZIP builder
- [x] 1.2 Replace the format-parameter API route with the single dataset export route
- [x] 1.3 Add focused tests for package contents, generated configuration, missing tiles, and removed legacy routes
- [x] 1.4 Extract imported raster PNG MBTiles into the same XYZ folder-package contract and add regression coverage

## 2. Frontend export experience

- [x] 2.1 Replace format-aware download handling with the single ZIP download contract
- [x] 2.2 Replace the export-choice modal with one direct folder-package export action and stop Save Project from downloading MTMap

## 3. Verification

- [x] 3.1 Run focused backend tests and inspect a generated ZIP structure and metadata
- [x] 3.2 Run the frontend production build and strict OpenSpec validation
