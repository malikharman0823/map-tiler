import React, { useEffect, useMemo, useState } from "react"
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
import DatasetMetadataOverlay from "../components/DatasetMetadataOverlay"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Layers,
  Save,
  Download,
  Compass,
  Trash2,
  Menu,
  ChevronRight,
  Loader2,
  AlertCircle,
} from "lucide-react"
import EndSessionDialog from "../components/EndSessionDialog"

export default function DatasetPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [dataset, setDataset] = useState(null)
  const [project, setProject] = useState(null)
  const [points, setPoints] = useState([])
  const [iconPoints, setIconPoints] = useState([])
  const [icons, setIcons] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exportState, setExportState] = useState("idle")
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
    setExportState("idle")
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

  const isMbtiles = datasetFormat === "mbtiles" || Boolean(dataset?.metadata?.mbtiles_path)
  const isVectorMbtiles = isMbtiles && ["pbf", "mvt"].includes(dataset?.metadata?.tile_format)
  const tileUrl = useMemo(
    () => isMbtiles
      ? mbtilesTileUrl(id)
      : datasetTileUrl(id, dataset?.map_layer?.tile_url_template),
    [dataset?.map_layer?.tile_url_template, id, isMbtiles],
  )

  async function removeDataset() {
    setDeleting(true)
    setError(null)
    try {
      await deleteDataset(id)
      navigate("/", { replace: true })
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to delete the dataset."))
      setDeleting(false)
      setShowDeleteDialog(false)
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
    } catch (requestError) {
      const readable = readableApiError(requestError, "Unable to save the project.")
      setExportState("error")
      setExportStatus(readable)
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    if (exportState === "exporting") return
    setExportState("exporting")
    setExportStatus({ message: "Preparing MapTiler folder package…", details: "" })
    try {
      const filename = await downloadProjectExport(id, project?.name || dataset?.filename)
      setExportState("success")
      setExportStatus({ message: "Export ready", details: filename })
    } catch (requestError) {
      setExportState("error")
      setExportStatus(readableApiError(requestError, "Unable to export the MapTiler folder package."))
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
      <main className="min-h-screen bg-[#f5f5f7] px-5 py-24 flex items-center justify-center">
        <div className="max-w-md w-full bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-8 text-center shadow-xs" role="alert">
          <div className="w-12 h-12 rounded-full bg-[#ff3b30]/10 text-[#ff3b30] flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="size-6" />
          </div>
          <p className="font-semibold text-[#1d1d1f] text-base">{error?.message || "Dataset unavailable"}</p>
          <p className="mt-2 text-xs text-[#7a7a7a] leading-relaxed">{error?.details}</p>
          <div className="mt-6">
            <Link className="inline-flex min-h-10 items-center justify-center rounded-full bg-[#0066cc] px-6 py-2 text-xs font-normal text-white hover:bg-[#0071e3] transition-colors" to="/">
              Back to datasets
            </Link>
          </div>
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
    <div className="bg-[#f5f5f7] text-[#1d1d1f] font-sans antialiased h-screen overflow-hidden flex flex-col">
      {/* Top App Navigation */}
      <header className="shrink-0 h-14 bg-[#ffffff]/90 backdrop-blur-md border-b border-[#e0e0e0] z-50 flex items-center justify-between px-3 sm:px-6">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/" className="flex items-center gap-2 group shrink-0">
            <div className="size-7 rounded-lg bg-[#0066cc] text-white flex items-center justify-center font-bold shadow-xs transition-transform group-hover:scale-105">
              <Layers className="size-4" />
            </div>
            <span className="text-xs font-semibold tracking-tight text-[#1d1d1f] hidden sm:inline">
              MapTiler Studio
            </span>
          </Link>
          <div className="h-4 w-px bg-[#e0e0e0] hidden sm:block"></div>
          {/* Breadcrumbs */}
          <nav className="flex items-center gap-1.5 text-xs text-[#7a7a7a] min-w-0">
            <Link className="hover:text-[#0066cc] transition-colors shrink-0" to="/">
              Datasets
            </Link>
            <ChevronRight className="size-3 text-[#7a7a7a] shrink-0" />
            <span className="text-[#1d1d1f] font-semibold truncate max-w-[120px] sm:max-w-[240px]">
              {displayName(dataset.filename)}
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#f5f5f7] border border-[#e0e0e0] text-[#7a7a7a] shrink-0 ml-1">
              {metadata.crs || "Unknown"}
            </span>
          </nav>
        </div>

        {/* Right Header Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="pill"
            size="sm"
            onClick={handleSaveProject}
            disabled={saving}
            className="h-8 bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-normal"
          >
            {saving ? (
              <Loader2 className="size-3.5 mr-1 animate-spin" />
            ) : (
              <Save className="size-3.5 mr-1" />
            )}
            <span className="hidden sm:inline">{saving ? "Saving…" : "Save Project"}</span>
            <span className="sm:hidden">Save</span>
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={exportState === "exporting" || saving}
            onClick={handleExport}
            className="h-8 rounded-full border-[#e0e0e0] text-xs text-[#1d1d1f] bg-[#ffffff] hover:bg-[#fafafc]"
          >
            {exportState === "exporting" ? (
              <Loader2 className="size-3.5 mr-1 animate-spin text-[#0066cc]" />
            ) : (
              <Download className="size-3.5 mr-1 text-[#7a7a7a]" />
            )}
            <span className="hidden sm:inline">
              {exportState === "exporting" ? "Exporting…" : "Export"}
            </span>
            <span className="sm:hidden">Export</span>
          </Button>

          {canGeoreference && (
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-8 rounded-full border-[#e0e0e0] text-xs text-[#1d1d1f] bg-[#ffffff] hover:bg-[#fafafc]"
            >
              <Link to={`/datasets/${id}/georeference`}>
                <Compass className="size-3.5 mr-1 text-[#0066cc]" />
                <span className="hidden sm:inline">
                  {dataset.georeference ? "Edit Georef" : "Georeference"}
                </span>
                <span className="sm:hidden">Georef</span>
              </Link>
            </Button>
          )}

          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowDeleteDialog(true)}
            disabled={deleting}
            className="size-8 rounded-full text-[#7a7a7a] hover:text-[#ff3b30] hover:bg-[#ff3b30]/10"
            title="Delete dataset"
          >
            <Trash2 className="size-4" />
          </Button>

          <EndSessionDialog />
        </div>
      </header>

      {exportStatus && (
        <div
          role={exportState === "error" ? "alert" : "status"}
          aria-live="polite"
          className={`absolute right-4 top-14 z-[60] max-w-sm rounded-md border px-4 py-3 text-xs shadow-xl ${exportState === "error" ? "border-red-200 bg-red-50 text-red-600" : "border-hairline bg-white/95 text-ink"}`}
        >
          <p className="font-semibold">{exportStatus.message}</p>
          {exportStatus.details && <p className="mt-1 text-muted">{exportStatus.details}</p>}
          {exportState !== "exporting" && (
            <button type="button" className="mt-2 text-ink underline" onClick={() => { setExportState("idle"); setExportStatus(null) }}>Dismiss</button>
          )}
        </div>
      )}

      {/* Main View Container */}
      <main className="flex-1 flex min-h-0 relative">
        {/* Central Map Canvas */}
        <div className="relative flex-1 h-full overflow-hidden bg-[#e6e8eb]">
          <DatasetMetadataOverlay dataset={dataset} />
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
              className="absolute right-4 top-4 z-10 w-9 h-9 rounded-full bg-white border border-hairline flex items-center justify-center text-ink shadow-sm hover:bg-pearl"
              onClick={() => setPanelOpen(true)}
              title="Open inspector"
            >
              <Menu className="size-4 text-ink" />
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

      <AlertDialog
        open={showDeleteDialog}
        onOpenChange={(open) => !open && setShowDeleteDialog(false)}
      >
        <AlertDialogContent className="rounded-[20px] bg-[#ffffff] border border-[#e0e0e0] text-[#1d1d1f] shadow-lg max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-base font-semibold text-[#1d1d1f]">
              Delete Dataset?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-xs text-[#7a7a7a] mt-1.5">
              Are you sure you want to delete{" "}
              <strong className="text-[#1d1d1f]">
                {displayName(dataset?.filename || "")}
              </strong>
              ? This action will permanently remove all associated spatial tiles, pyramids, and metadata.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-4 gap-2">
            <AlertDialogCancel
              disabled={deleting}
              className="rounded-full border-[#e0e0e0] bg-[#ffffff] hover:bg-[#f5f5f7] text-xs text-[#1d1d1f]"
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={removeDataset}
              disabled={deleting}
              className="rounded-full bg-[#ff3b30] hover:bg-[#e03126] text-white text-xs font-normal"
            >
              {deleting ? (
                <>
                  <Loader2 className="size-3.5 mr-1.5 animate-spin" />
                  <span>Deleting…</span>
                </>
              ) : (
                <span>Delete Permanently</span>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
