## 1. Exported project state

- [x] 1.1 Serialize versioned Map Studio project state, control points, icon points, and the optional raster source into the folder ZIP
- [x] 1.2 Add backend tests proving folder exports contain restorable state without legacy project or tile containers

## 2. Folder import backend

- [x] 2.1 Add secure multipart folder validation and transactional restoration into managed source and XYZ tile storage
- [x] 2.2 Expose one folder-import API and make restored folder tiles available as a normal raster map layer
- [x] 2.3 Add round-trip and invalid-folder tests covering project settings, points, tiles, source assets, and cleanup behavior

## 3. Map Studio folder-opening UI

- [x] 3.1 Add a directory picker and folder multipart client using explicit relative paths
- [x] 3.2 Open the restored dataset directly and preserve ordinary single-file uploads

## 4. Verification

- [x] 4.1 Run focused backend tests, the frontend production build, and strict OpenSpec validation
- [x] 4.2 Restart the local backend and verify the live folder-export contract and folder-import route
