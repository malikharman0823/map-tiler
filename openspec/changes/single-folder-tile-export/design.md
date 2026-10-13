## Context

The current export service branches across six output formats and the dataset page presents multiple export choices. Raster tiles can exist either on disk in XYZ layout as `storage/tiles/<dataset-id>/<z>/<x>/<y>.png` or inside an imported PNG MBTiles archive. The supplied `New Adam` reference uses XYZ PNG tiles together with MapTiler metadata and four browser viewer pages.

The browser must download one file, so the on-disk folder layout will be delivered as a ZIP archive. Extracting the archive produces the reference layout at the extraction root.

## Goals / Non-Goals

**Goals:**

- Expose one export action and one export endpoint.
- Produce a MapTiler-compatible folder package containing real XYZ PNG tiles, `metadata.json`, and the four supplied viewer variants.
- Populate name, bounds, zoom range, and viewer configuration from the current project/dataset.
- Preserve bounded temporary-file cleanup and structured API errors.
- Remove obsolete export-only branches and UI choices.

**Non-Goals:**

- Removing support for importing or previewing MBTiles, MTMap, or other source formats.
- Generating tiles during export.
- Making the supplied CDN-based HTML viewers fully offline.
- Embedding a Google Maps API key.

## Decisions

### Use a formatless dataset export endpoint

`GET /datasets/{dataset_id}/export` will replace the format-parameter route. The response will always be `application/zip` with a filesystem-safe `.zip` filename. This makes unsupported legacy formats unreachable instead of retaining aliases that imply continued support.

### Build the archive from XYZ PNG output

For generated output, the exporter will require `tile_status == "completed"`, a managed tile directory, a valid zoom range, and at least one conforming `<z>/<x>/<y>.png` file. For an imported raster PNG MBTiles dataset, it will stream tile blobs into the ZIP while converting MBTiles TMS rows to XYZ rows. The original `.mbtiles` container is never included. The exporter will not synthesize empty zoom folders or silently package an empty structure.

### Derive geographic configuration from the processed raster

Bounds will be transformed from the processed raster CRS to EPSG:4326, matching the supplied metadata contract. A validated WGS84 metadata bound is a fallback. For imported raster MBTiles without bounds metadata, bounds are calculated from tiles at the highest zoom. Zoom values come from completed tile-generation state or the imported MBTiles metadata.

### Reproduce the supplied viewer package

The archive root will contain `metadata.json`, `index.html`, `leaflet.html`, `openlayers.html`, and `googlemaps.html`. Each viewer will use relative `{z}/{x}/{y}.png` URLs and the project-specific bounds/center/zoom configuration. The Google viewer will retain an empty API key rather than exporting a secret.

### Keep imports and previews outside the removal boundary

MBTiles tile reads, format inspection, source imports, and MTMap project import remain because the request changes how files are exported. Only export builders, export route branching, export UI choices, and export tests are retired.

## Risks / Trade-offs

- Large tile sets can create large archives and take time to package. → Write the ZIP to a temporary file, store already-compressed PNGs without redundant compression, stream it with `FileResponse`, and delete the temporary directory after the response.
- CDN-hosted viewers require internet access, and Google Maps requires a key. → Match the supplied package faithfully and document that limitation in viewer markup/metadata rather than exporting credentials.
- A dataset without usable generated or imported raster PNG tiles cannot be represented in this format. → Return a structured error directing the user to provide or generate compatible PNG tiles.
- Removing format-specific routes is a breaking API change. → Update the frontend in the same change and test that legacy format paths return `404`.
