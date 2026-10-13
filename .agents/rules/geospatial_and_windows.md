# Geospatial and Platform Invariants

1. **MapLibre GL Bounds**:
   - `map.addSource('raster', { bounds })` strictly expects `[west, south, east, north]` (a 1D array of length 4).
   - Only `map.fitBounds()` accepts `[[swLng, swLat], [neLng, neLat]]`.
   - Always normalize bounds through a utility that validates coordinate order and lengths.

2. **Windows Storage Cleanup**:
   - Do not rely on plain `shutil.rmtree` on Windows.
   - Use an error handler with `stat.S_IWRITE` permission removal, execute `gc.collect()`, and retry with backoff for OS lock clearance.

3. **Uploaded File Paths**:
   - Files uploaded to system temporary directories must be persisted into permanent local storage before calling `relative_to(PROJECT_ROOT)`.
