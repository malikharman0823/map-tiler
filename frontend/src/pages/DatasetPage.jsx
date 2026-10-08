import React, { useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  createIconPoint,
  datasetTileUrl,
  deleteDataset,
  getDataset,
  getPbfPreview,
  getVectorPreview,
  listControlPoints,
  listIconPoints,
  listIcons,
  readableApiError,
  removeIconPoint,
  updateIconPoint,
  getMapProject,
  updateMapProject,
  downloadProjectExport,
  mbtilesTileUrl,
} from "../api"
import DatasetInspectionPanel from "../components/DatasetInspectionPanel"
import Map from "../components/Map"
import { displayName } from "../components/DatasetCard"

const EXPORT_OPTIONS = [
  { 
    format: "mtmap", 
    label: "FULL PROJECT", 
    detail: ".mtmap",
    description: "Complete editable MapTiler Clone project.",
    contains: ["datasets", "georeferencing", "control points", "user points", "icons", "layers", "map position", "styling", "generated tiles"],
    bestFor: "Reopening and continuing work in MapTiler Clone.",
    canDisplay: ["raster", "vector layers", "georeferenced raster", "user points", "control points", "icons", "generated tiles", "layer configuration", "map camera", "styling"],
    doesNotPreserve: []
  },
  { 
    format: "tif", 
    label: "GEOTIFF", 
    detail: ".tif",
    description: "Georeferenced raster.",
    contains: ["raster pixels", "CRS", "geographic transform", "geographic bounds"],
    bestFor: "Floor plans, scanned maps, imagery and GIS applications.",
    canDisplay: ["raster", "geographic positioning"],
    doesNotPreserve: ["user points", "control-point editing state", "project UI configuration"]
  },
  { 
    format: "mbtiles", 
    label: "CUSTOM TILES", 
    detail: ".mbtiles",
    description: "Generated map tile package.",
    contains: ["generated map tiles", "tile metadata", "zoom information"],
    bestFor: "Using generated custom tiles in compatible mapping/tile applications.",
    canDisplay: ["map tiles"],
    doesNotPreserve: ["complete project", "control-point configuration", "user-point database", "application-specific layer settings"]
  },
]

export default function DatasetPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const exportMenuRef = useRef(null)
  const [dataset, setDataset] = useState(null)
  const [project, setProject] = useState(null)
  const [points, setPoints] = useState([])
  const [iconPoints, setIconPoints] = useState([])
  const [icons, setIcons] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exportState, setExportState] = useState("closed")
  const [exportStatus, setExportStatus] = useState(null)
  const [error, setError] = useState(null)
  const [controlPointsError, setControlPointsError] = useState(null)
  const [iconPointsError, setIconPointsError] = useState(null)
  const [opacity, setOpacity] = useState(0.65)
  const [pbfPreview, setPbfPreview] = useState(null)
  const [pbfLoading, setPbfLoading] = useState(false)
  const [pbfError, setPbfError] = useState(null)
  const [selectedPointId, setSelectedPointId] = useState(null)
  const [selectedIconPointId, setSelectedIconPointId] = useState(null)
  const [selectedFeature, setSelectedFeature] = useState(null)
  const [iconPointDraft, setIconPointDraft] = useState(null)
  const [controlPointDraft, setControlPointDraft] = useState(null)
  const [mapMode, setMapMode] = useState("normal")
  const [panelOpen, setPanelOpen] = useState(() => (
    typeof window === "undefined" || window.matchMedia("(min-width: 736px)").matches
  ))
  const [layerVisibility, setLayerVisibility] = useState({
    basemap: true,
    dataset: true,
    controlPoints: true,
    iconPoints: true,
  })

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setDataset(null)
    setPoints([])
    setIconPoints([])
    setSelectedPointId(null)
    setSelectedIconPointId(null)
    setSelectedFeature(null)
    setIconPointDraft(null)
    setControlPointDraft(null)
    setMapMode("normal")
    setError(null)
    setControlPointsError(null)
    setIconPointsError(null)
    setPbfPreview(null)
    setPbfError(null)
    setExportState("closed")
    setExportStatus(null)
    setPanelOpen(window.matchMedia("(min-width: 736px)").matches)

    Promise.allSettled([
      getDataset(id, controller.signal),
      listControlPoints(id, controller.signal),
      listIconPoints(id, controller.signal),
      listIcons(controller.signal),
      getMapProject(id, controller.signal),
    ]).then(([datasetResult, pointsResult, iconPointsResult, iconsResult, projectResult]) => {
      if (!active) return
      if (datasetResult.status === "fulfilled") {
        setDataset(datasetResult.value)
      } else if (datasetResult.reason?.code !== "ERR_CANCELED") {
        setError(readableApiError(datasetResult.reason, "Unable to load the dataset."))
      }

      if (pointsResult.status === "fulfilled") {
        setPoints(pointsResult.value)
      } else if (pointsResult.reason?.code !== "ERR_CANCELED") {
        setControlPointsError(readableApiError(pointsResult.reason, "Unable to load control points.").message)
      }

      if (iconPointsResult.status === "fulfilled") {
        setIconPoints(iconPointsResult.value)
      } else if (iconPointsResult.reason?.code !== "ERR_CANCELED") {
        setIconPointsError(readableApiError(iconPointsResult.reason, "Unable to load icon points.").message)
      }

      if (iconsResult.status === "fulfilled") {
        setIcons(iconsResult.value)
      }

      if (projectResult.status === "fulfilled" && projectResult.value) {
        setProject(projectResult.value)
        const config = projectResult.value.configuration || {}
        if (config.opacity !== undefined) setOpacity(config.opacity)
        if (config.layerVisibility) setLayerVisibility(config.layerVisibility)
      }
    }).finally(() => {
      if (active) setLoading(false)
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [id])

  const datasetFormat = String(dataset?.metadata?.format || "").toLowerCase()
  const isPbf = Boolean(dataset?.filename?.toLowerCase().endsWith(".pbf"))
  const isVectorSource = datasetFormat === "geojson" || datasetFormat === "geopackage"

  useEffect(() => {
    if (!isPbf && !isVectorSource) return undefined

    const controller = new AbortController()
    let active = true
    setPbfLoading(true)
    setPbfError(null)
    const previewRequest = isPbf
      ? getPbfPreview(id, controller.signal)
      : getVectorPreview(id, controller.signal)
    previewRequest
      .then((preview) => {
        if (active) setPbfPreview(preview)
      })
      .catch((requestError) => {
        if (active && requestError.code !== "ERR_CANCELED") {
          setPbfError(readableApiError(requestError, "Unable to display the vector preview."))
        }
      })
      .finally(() => {
        if (active) setPbfLoading(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [id, isPbf, isVectorSource])

  useEffect(() => {
    if (exportState !== "open") return undefined
    function closeOnOutsideClick(event) {
      if (!exportMenuRef.current?.contains(event.target)) setExportState("closed")
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setExportState("closed")
    }
    document.addEventListener("pointerdown", closeOnOutsideClick)
    document.addEventListener("keydown", closeOnEscape)
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick)
      document.removeEventListener("keydown", closeOnEscape)
    }
  }, [exportState])

  const isMbtiles = datasetFormat === "mbtiles" || Boolean(dataset?.metadata?.mbtiles_path)
  const isVectorMbtiles = isMbtiles && ["pbf", "mvt"].includes(dataset?.metadata?.tile_format)
  const tileUrl = useMemo(
    () => isMbtiles
      ? mbtilesTileUrl(id)
      : datasetTileUrl(id, dataset?.map_layer?.tile_url_template),
    [dataset?.map_layer?.tile_url_template, id, isMbtiles],
  )

  async function removeDataset() {
    if (!window.confirm("Delete this dataset and all of its stored files?")) return
    setDeleting(true)
    setError(null)
    try {
      await deleteDataset(id)
      navigate("/", { replace: true })
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to delete the dataset."))
      setDeleting(false)
    }
  }

  async function handleSaveProject() {
    if (saving || exportState === "exporting") return
    setSaving(true)
    try {
      const config = {
        opacity,
        layerVisibility,
      }
      const updated = await updateMapProject(id, project?.name || dataset?.filename || "Map Project", config)
      setProject(updated)
      await handleExport("mtmap", updated.name)
    } catch (requestError) {
      const readable = readableApiError(requestError, "Unable to save the project.")
      setExportState("error")
      setExportStatus(readable)
    } finally {
      setSaving(false)
    }
  }

  async function handleExport(format, projectName = project?.name || dataset?.filename) {
    if (exportState === "exporting") return
    setExportState("exporting")
    setExportStatus({ message: `Preparing ${format.toUpperCase()} export…`, details: "" })
    try {
      const filename = await downloadProjectExport(id, format, projectName)
      setExportState("success")
      setExportStatus({ message: "Export ready", details: filename })
    } catch (requestError) {
      setExportState("error")
      setExportStatus(readableApiError(requestError, `Unable to export ${format.toUpperCase()}.`))
    }
  }

  function selectPoint(pointId) {
    setSelectedPointId(pointId)
    setSelectedIconPointId(null)
    setSelectedFeature(null)
    setLayerVisibility((current) => ({ ...current, controlPoints: true }))
    setPanelOpen(true)
  }

  function selectIconPoint(pointId) {
    setSelectedIconPointId(pointId)
    setSelectedPointId(null)
    setSelectedFeature(null)
    setLayerVisibility((current) => ({ ...current, iconPoints: true }))
    setPanelOpen(true)
  }

  function selectFeature(feature) {
    setSelectedFeature(feature)
    setSelectedPointId(null)
    setSelectedIconPointId(null)
    setPanelOpen(true)
  }

  function startIconPointPlacement() {
    setSelectedFeature(null)
    setIconPointDraft(null)
    setMapMode("add-icon-point")
    setPanelOpen(true)
  }

  function startControlPointPlacement() {
    setSelectedFeature(null)
    setControlPointDraft(null)
    setMapMode("add-control-point")
    setPanelOpen(true)
  }

  function receiveIconPointCoordinate(coordinate) {
    setIconPointDraft(coordinate)
    setMapMode("normal")
    setPanelOpen(true)
  }

  async function receiveControlPointCoordinate(coordinate) {
    if (!dataset?.georeference?.transformation_parameters) {
      setControlPointsError("Cannot add control points to an ungeoreferenced image from the main map.")
      setMapMode("normal")
      return
    }
    const params = dataset.georeference.transformation_parameters
    const { a, b, c, d, e, f } = params
    const det = b * d - a * e
    if (Math.abs(det) < 1e-10) {
      setControlPointsError("Invalid georeferencing transformation.")
      setMapMode("normal")
      return
    }
    
    // Invert the affine transformation to find the original image_x, image_y
    const image_x = (-e * (coordinate.longitude - c) + b * (coordinate.latitude - f)) / det
    const image_y = (-d * (coordinate.longitude - c) + a * (coordinate.latitude - f)) / det

    setMapMode("normal")
    setControlPointsError(null)
    try {
      const created = await createControlPoint(id, {
        longitude: coordinate.longitude,
        latitude: coordinate.latitude,
        image_x: Math.round(image_x),
        image_y: Math.round(image_y),
      })
      setPoints((current) => [...current, created])
      selectPoint(created.id)
    } catch (requestError) {
      setControlPointsError(readableApiError(requestError, "Unable to add control point.").message)
    }
  }

  function cancelIconPointPlacement() {
    setIconPointDraft(null)
    setMapMode("normal")
  }

  function cancelControlPointPlacement() {
    setControlPointDraft(null)
    setMapMode("normal")
  }

  async function addIconPoint(data) {
    if (!iconPointDraft) return
    setIconPointsError(null)
    try {
      const created = await createIconPoint(id, { ...iconPointDraft, ...data })
      setIconPoints((current) => [...current, created])
      setIconPointDraft(null)
      setMapMode("normal")
      selectIconPoint(created.id)
    } catch (requestError) {
      setIconPointsError(readableApiError(requestError, "Unable to add the icon point.").message)
      throw requestError
    }
  }

  async function editIconPoint(point, data) {
    setIconPointsError(null)
    try {
      const updated = await updateIconPoint(point.id, {
        latitude: point.latitude,
        longitude: point.longitude,
        ...data,
      })
      setIconPoints((current) => current.map((currentPoint) => (
        currentPoint.id === updated.id ? updated : currentPoint
      )))
    } catch (requestError) {
      setIconPointsError(readableApiError(requestError, "Unable to update the icon point.").message)
      throw requestError
    }
  }

  async function deleteIconPoint(pointId) {
    setIconPointsError(null)
    try {
      await removeIconPoint(pointId)
      setIconPoints((current) => current.filter((point) => point.id !== pointId))
      setSelectedIconPointId(null)
    } catch (requestError) {
      setIconPointsError(readableApiError(requestError, "Unable to delete the icon point.").message)
    }
  }

  async function deleteControlPoint(pointId) {
    setControlPointsError(null)
    try {
      await removeControlPoint(pointId)
      setPoints((current) => current.filter((point) => point.id !== pointId))
      setSelectedPointId(null)
    } catch (requestError) {
      setControlPointsError(readableApiError(requestError, "Unable to delete the control point.").message)
    }
  }

  function updateLayerVisibility(layer, visible) {
    setLayerVisibility((current) => ({ ...current, [layer]: visible }))
  }

  if (loading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-parchment text-muted">
        Loading dataset…
      </div>
    )
  }

  if (!dataset) {
    return (
      <main className="min-h-screen bg-parchment px-5 py-20">
        <div className="mx-auto max-w-2xl bg-white border border-red-200 rounded-lg p-6 text-center" role="alert">
          <p className="font-semibold text-ink">{error?.message || "Dataset unavailable"}</p>
          <p className="mt-2 text-sm text-muted">{error?.details}</p>
          <Link className="inline-block mt-5 text-ink hover:text-ink/80" to="/">Back to datasets</Link>
        </div>
      </main>
    )
  }

  const metadata = dataset.metadata || {}
  const canGeoreference = /\.(jpe?g|png|tiff?)$/i.test(dataset.filename) && (!metadata.crs || dataset.georeference)
  const savedMapLayer = dataset.map_layer
  const nativeTilesReady = !dataset.georeference
    && dataset.tile_status === "completed"
    && Boolean(dataset.tile_path)
  const rasterMbtilesReady = isMbtiles && !isVectorMbtiles
  const tilesReady = Boolean(savedMapLayer) || nativeTilesReady || rasterMbtilesReady
  const vectorReady = (isPbf || isVectorSource) && Boolean(pbfPreview?.geojson)
  const vectorTileReady = isVectorMbtiles && metadata.vector_layers?.length > 0
  const styleDocument = datasetFormat === "maplibre_style" ? metadata.style : null
  const datasetLayerAvailable = tilesReady || vectorReady || vectorTileReady || Boolean(styleDocument)
  const mapBounds = savedMapLayer?.bounds || pbfPreview?.bounds || metadata.bounds || null
  const mapCrs = savedMapLayer?.bounds_crs || (vectorReady || isMbtiles ? "EPSG:4326" : metadata.crs)
  const mappedControlPoints = savedMapLayer ? points : []
  const datasetLayerName = displayName(savedMapLayer?.name || dataset.filename)

  return (
    <div className="bg-parchment text-ink font-sans antialiased h-screen overflow-hidden flex flex-col">
      {/* Top App Navigation */}
      <header className="shrink-0 h-12 bg-white/90 backdrop-blur border-b border-hairline z-50 flex items-center justify-between px-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 pr-3 border-r border-hairline">
            <span className="material-symbols-outlined text-ink text-[18px]">layers</span>
            <span className="text-xs font-semibold tracking-tight text-ink">MapTiler Studio</span>
            <span className="text-[10px] px-1.5 py-0.5 bg-pearl text-muted rounded font-mono">MVP</span>
          </div>
          {/* Breadcrumbs */}
          <nav className="flex items-center gap-1.5 text-xs text-muted">
            <Link className="hover:text-ink transition-colors" to="/">Datasets</Link>
            <span className="text-muted/60">/</span>
            <span className="text-ink font-medium truncate max-w-[200px]">{displayName(dataset.filename)}</span>
            <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-pearl border border-hairline text-muted ml-1">{metadata.crs || "Unknown"}</span>
          </nav>
        </div>

        {/* Right Header Actions */}
        <div className="flex items-center gap-1.5">
          <button 
            onClick={handleSaveProject} 
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-600 hover:text-blue-700 transition-colors"
          >
            <span className="material-symbols-outlined text-[15px]">save</span>
            <span>{saving ? "Saving..." : "Save Project"}</span>
          </button>
          
          <button
            type="button"
            disabled={exportState === "exporting" || saving}
            onClick={() => setExportState("open")}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-white hover:bg-pearl border border-hairline text-ink hover:text-ink/80 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[15px]">download</span>
            <span>{exportState === "exporting" ? "Exporting…" : "Export"}</span>
          </button>
          
          {canGeoreference && (
            <Link to={`/datasets/${id}/georeference`} className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-white hover:bg-pearl border border-hairline text-ink hover:text-ink/80 transition-colors ml-2 border-l border-hairline pl-3">
              <span className="material-symbols-outlined text-[15px]">satellite_alt</span>
              <span>{dataset.georeference ? "Edit Georef" : "Georeference"}</span>
            </Link>
          )}
          <button 
            onClick={removeDataset} 
            disabled={deleting}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-red-50 hover:bg-red-100 border border-red-200 text-red-600 hover:text-red-700 transition-colors ml-1"
          >
            <span className="material-symbols-outlined text-[15px]">delete</span>
            <span>{deleting ? "Deleting..." : "Delete"}</span>
          </button>
        </div>
      </header>

      {exportStatus && exportState !== "closed" && exportState !== "open" && (
        <div
          role={exportState === "error" ? "alert" : "status"}
          aria-live="polite"
          className={`absolute right-4 top-14 z-[60] max-w-sm rounded-md border px-4 py-3 text-xs shadow-xl ${exportState === "error" ? "border-red-200 bg-red-50 text-red-600" : "border-hairline bg-white/95 text-ink"}`}
        >
          <p className="font-semibold">{exportStatus.message}</p>
          {exportStatus.details && <p className="mt-1 text-muted">{exportStatus.details}</p>}
          {exportState !== "exporting" && (
            <button type="button" className="mt-2 text-ink underline" onClick={() => { setExportState("closed"); setExportStatus(null) }}>Dismiss</button>
          )}
        </div>
      )}

      {/* Main View Container */}
      <main className="flex-1 flex min-h-0 relative">
        {/* Central Map Canvas */}
        <div className="relative flex-1 h-full overflow-hidden bg-[#e6e8eb]">
          <Map
            key={id}
            tileUrl={tileUrl}
            tilesReady={tilesReady}
            minZoom={dataset.tile_min_zoom ?? metadata.min_zoom}
            maxZoom={dataset.tile_max_zoom ?? metadata.max_zoom}
            bounds={mapBounds}
            crs={mapCrs}
            fitKey={id}
            opacity={opacity}
            vectorData={pbfPreview?.geojson}
            vectorReady={vectorReady}
            vectorTileUrl={isVectorMbtiles ? tileUrl : null}
            vectorTileLayers={isVectorMbtiles ? metadata.vector_layers : []}
            styleDocument={styleDocument}
            controlPoints={mappedControlPoints}
            iconPoints={iconPoints}
            icons={icons}
            selectedControlPointId={selectedPointId}
            selectedIconPointId={selectedIconPointId}
            onSelectControlPoint={selectPoint}
            onSelectIconPoint={selectIconPoint}
            onSelectFeature={selectFeature}
            interactionMode={mapMode}
            onPlaceCoordinate={(coordinate) => {
              if (mapMode === "add-icon-point") receiveIconPointCoordinate(coordinate)
              else if (mapMode === "add-control-point") receiveControlPointCoordinate(coordinate)
            }}
            showBasemap={layerVisibility.basemap}
            showDataset={layerVisibility.dataset}
            showControlPoints={layerVisibility.controlPoints}
            showIconPoints={layerVisibility.iconPoints}
            layoutRevision={panelOpen}
          />
          {mapMode === "add-icon-point" && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-blue-600/90 backdrop-blur text-white px-5 py-2.5 rounded-full text-sm font-medium shadow-lg flex items-center gap-3 z-40">
              <span>Click anywhere on the map to place a new icon point</span>
              <button onClick={cancelIconPointPlacement} className="px-2.5 py-1 bg-white/20 hover:bg-white/30 rounded text-xs transition-colors">Cancel</button>
            </div>
          )}
          {mapMode === "add-control-point" && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-blue-600/90 backdrop-blur text-white px-5 py-2.5 rounded-full text-sm font-medium shadow-lg flex items-center gap-3 z-40">
              <span>Click the map to reverse-calculate and add a control point</span>
              <button onClick={cancelControlPointPlacement} className="px-2.5 py-1 bg-white/20 hover:bg-white/30 rounded text-xs transition-colors">Cancel</button>
            </div>
          )}

          {!panelOpen && (
            <button 
              type="button" 
              className="absolute right-4 top-4 z-10 w-8 h-8 rounded-md bg-white border border-hairline flex items-center justify-center text-ink shadow-sm hover:bg-pearl" 
              onClick={() => setPanelOpen(true)}
            >
              <span className="material-symbols-outlined text-[18px]">menu_open</span>
            </button>
          )}

          {(pbfLoading || pbfError || controlPointsError || iconPointsError) && (
            <div className="absolute bottom-4 left-4 z-10 max-w-xs rounded-md border border-hairline bg-white/90 backdrop-blur px-4 py-3 text-xs text-ink shadow-sm">
              {pbfLoading && <p>Preparing the vector map preview…</p>}
              {pbfError && <p className="text-red-600">{pbfError.message}</p>}
              {controlPointsError && <p className={pbfLoading || pbfError ? "mt-1" : ""}>Control points unavailable.</p>}
              {iconPointsError && <p className="mt-1">{iconPointsError}</p>}
            </div>
          )}
        </div>

        {/* Right Inspector Panel */}
        <DatasetInspectionPanel
          dataset={dataset}
          points={mappedControlPoints}
          iconPoints={iconPoints}
          icons={icons}
          selectedPointId={selectedPointId}
          selectedIconPointId={selectedIconPointId}
          selectedFeature={selectedFeature}
          onSelectPoint={selectPoint}
          onSelectIconPoint={selectIconPoint}
          onCreateIconPoint={addIconPoint}
          onUpdateIconPoint={editIconPoint}
          onDeleteIconPoint={deleteIconPoint}
          onDeleteControlPoint={deleteControlPoint}
          iconPointDraft={iconPointDraft}
          placingIconPoint={mapMode === "add-icon-point"}
          placingControlPoint={mapMode === "add-control-point"}
          onStartIconPoint={startIconPointPlacement}
          onCancelIconPoint={cancelIconPointPlacement}
          onStartControlPoint={startControlPointPlacement}
          onCancelControlPoint={cancelControlPointPlacement}
          panelOpen={panelOpen}
          onClose={() => setPanelOpen(false)}
          layerVisibility={layerVisibility}
          onLayerVisibilityChange={updateLayerVisibility}
          opacity={opacity}
          onOpacityChange={setOpacity}
          datasetLayerAvailable={datasetLayerAvailable}
          datasetLayerName={datasetLayerName}
          georeferencedLayerAvailable={Boolean(savedMapLayer)}
          controlPointsError={controlPointsError}
          iconPointsError={iconPointsError}
        />
      </main>

      {/* Export Modal */}
      {exportState === "open" && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 overflow-y-auto">
          <div 
            ref={exportMenuRef}
            className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-hairline">
              <div>
                <h2 className="text-lg font-semibold text-ink">Export Map</h2>
                <p className="text-sm text-muted mt-1">Choose the format based on what you want to preserve or use outside the application.</p>
              </div>
              <button 
                onClick={() => setExportState("closed")}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-pearl text-muted hover:text-ink transition-colors"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {EXPORT_OPTIONS.filter((option) => {
                  if (option.format === "tif") {
                    return dataset.georeferenced_path || dataset.processed_path || /\.tiff?$/i.test(dataset.filename);
                  }
                  if (option.format === "mbtiles") {
                    return dataset.tile_status === "completed" || dataset.metadata?.format === "mbtiles" || Boolean(dataset.metadata?.mbtiles_path);
                  }
                  return true;
                }).map((option) => (
                  <div key={option.format} className="flex flex-col border border-hairline rounded-lg overflow-hidden bg-pearl/30">
                    <div className="p-5 flex-1 flex flex-col">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-bold text-ink">{option.label}</h3>
                        <span className="font-mono text-xs text-muted bg-white px-1.5 py-0.5 rounded border border-hairline">{option.detail}</span>
                      </div>
                      
                      <p className="text-sm font-medium text-ink mb-4">{option.description}</p>
                      
                      {option.contains?.length > 0 && (
                        <div className="mb-4">
                          <h4 className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">Contains</h4>
                          <ul className="text-xs text-ink space-y-1">
                            {option.contains.map(item => (
                              <li key={item} className="flex items-start gap-1.5">
                                <span className="w-1 h-1 rounded-full bg-ink/30 mt-1.5 shrink-0"></span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      
                      <div className="mb-4">
                        <h4 className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">Best for</h4>
                        <p className="text-xs text-ink">{option.bestFor}</p>
                      </div>
                      
                      {option.canDisplay?.length > 0 && (
                        <div className="mb-4">
                          <h4 className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">Can display</h4>
                          <ul className="text-xs text-green-700 space-y-1">
                            {option.canDisplay.map(item => (
                              <li key={item} className="flex items-start gap-1.5">
                                <span className="material-symbols-outlined text-[14px]">check</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      
                      {option.doesNotPreserve?.length > 0 && (
                        <div className="mb-4">
                          <h4 className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">Does not preserve</h4>
                          <ul className="text-xs text-red-600 space-y-1">
                            {option.doesNotPreserve.map(item => (
                              <li key={item} className="flex items-start gap-1.5">
                                <span className="material-symbols-outlined text-[14px]">close</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    
                    <div className="p-4 border-t border-hairline bg-white mt-auto">
                      <button
                        onClick={() => {
                          setExportState("closed") // close popup on export action 
                          handleExport(option.format)
                        }}
                        disabled={exportState === "exporting"}
                        className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md shadow-sm transition-colors text-sm flex items-center justify-center gap-2"
                      >
                        <span className="material-symbols-outlined text-[16px]">download</span>
                        Export {option.detail}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
