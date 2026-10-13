## Context

The single folder export currently contains web viewers, metadata, and XYZ PNG tiles. It deliberately excludes the former `.mtmap` container, but that also means the extracted folder has no machine-readable Map Studio state and the UI can only upload one file. Existing project-import code already demonstrates transactional restoration and point validation, while the normal dataset page already renders managed XYZ directories.

## Goals / Non-Goals

**Goals:**

- Keep one folder-based export while making it a complete Map Studio round-trip package.
- Restore project configuration, control points, user-created icon points, XYZ tiles, and an available source raster under fresh IDs.
- Open the imported project immediately as a normal dataset with a working raster overlay.
- Validate all client-supplied relative paths and clean staged files on failure.

**Non-Goals:**

- Reintroducing `.mtmap`, `.mbtiles`, or format-choice export routes.
- Importing arbitrary folders that were not produced by Map Studio.
- Restoring database record IDs from another installation.
- Making the CDN-based standalone viewers offline.

## Decisions

### Add `mapstudio.json` beside the existing reference files

The export root will retain the supplied `metadata.json` and HTML viewers, and add one versioned `mapstudio.json`. That document stores project name/configuration, dataset display metadata, control points, icon points, and an optional source-asset path. A separate document avoids changing the MapTiler-compatible `metadata.json` fields and gives Map Studio an explicit schema boundary.

### Preserve the source raster as an internal folder asset when possible

If the dataset source is a managed JPG, PNG, or TIFF raster, it will be copied to `assets/source/<safe-name>`. It is not a second export choice; it is project data needed to reopen the source image and keep control-point pixel coordinates meaningful. Tile-only sources such as MBTiles remain excluded and reopen from the exported XYZ PNG layer.

### Import directories through multipart files plus explicit relative paths

The React folder picker will submit every selected file and its `webkitRelativePath` to a new formatless folder-import endpoint. The server will pair files and paths, remove one common selected root, reject absolute/traversal/duplicate paths, cap file count and total size, and accept only the declared Map Studio structure. Explicit paths are used because multipart upload filenames are not a reliable cross-browser directory-path contract.

### Restore into managed storage under fresh IDs

Import creates a new dataset ID, copies PNG tiles to `storage/tiles/<id>/<z>/<x>/<y>.png`, copies an optional source raster to `storage/uploads/<id>/`, creates a new map project, and inserts validated point records in one database transaction. Original IDs are informational only and are never trusted or reused.

### Make folder-backed tiles a first-class raster layer

Imported folder datasets use format `mapstudio_folder`, completed tile state, metadata bounds, and a managed XYZ tile path. Dataset detail will construct the normal raster map-layer response from those bounds without requiring a generated GeoTIFF or active georeference record. Existing tile serving and MapLibre rendering remain unchanged.

## Risks / Trade-offs

- Large directories create large multipart requests and many file parts. → Apply the existing upload-size limit, a bounded file count, streaming copies, and cleanup on any failure.
- A user can modify extracted files before import. → Strictly validate project schema, relative paths, tile coordinates/extensions, bounds, and point values; never trust stored IDs or paths.
- Tile-only exports cannot recreate an original source image. → Restore the working raster tile layer and map; source-image editing is available only when the optional source asset exists.
- Browser folder selection uses the non-standard but broadly implemented `webkitdirectory` attribute. → Keep ordinary single-file upload intact and expose folder opening as a separate explicit action.
