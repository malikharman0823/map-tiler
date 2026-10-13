import React, { useEffect, useRef, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Database,
  Download,
  Layers,
  Loader2,
  Map as MapIcon,
  Menu,
  Plus,
  RefreshCw,
  Upload,
  FolderOpen,
  X,
} from "lucide-react"

import {
  importDatasetZip,
  importMapProject,
  downloadProjectExport,
  uploadDataset,
  listIcons,
  readableApiError,
} from "../api"
import WorkspaceTable from "../components/WorkspaceTable"
import WorkspaceLayerPanel from "../components/WorkspaceLayerPanel"
import WorkspaceMap from "../components/WorkspaceMap"
import useWorkspace from "../hooks/useWorkspace"
import EndSessionDialog from "../components/EndSessionDialog"


function AddDatasetDialog({ open, onClose, onUploaded }) {
  const inputRef = useRef(null)
  const [state, setState] = useState("confirm")
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (open) {
      setState("confirm")
      setProgress(0)
      setError(null)
    }
  }, [open])

  if (!open) return null

  async function selectFile(event) {
    const [file] = event.target.files
    event.target.value = ""
    if (!file) return
    const isZip = (file.name || "").toLowerCase().endsWith(".zip")
    const isSupported = /\.(png|jpe?g|pdf|dxf|dwg|svf|zip)$/i.test(file.name || "")
    if (!isSupported) {
      setError({
        message: "Unsupported file format.",
        details: "Supported formats are PNG, JPG, PDF, CAD (.dxf, .dwg), SVF (.svf), and Map Studio project archives (.zip).",
      })
      return
    }
    setState("uploading")
    setError(null)
    try {
      const uploadFn = isZip ? importDatasetZip : uploadDataset
      const dataset = await uploadFn(file, (uploadEvent) => {
        if (uploadEvent.total) setProgress(Math.round((uploadEvent.loaded / uploadEvent.total) * 100))
      })
      await onUploaded(dataset)
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to add the dataset."))
      setState("confirm")
    }
  }

  return (
    <div className="workspace-dialog-backdrop" role="presentation">
      <section className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="add-dataset-title">
        <button type="button" className="workspace-dialog-close" onClick={onClose} aria-label="Close"><X /></button>
        <div className="workspace-dialog-icon"><Layers /></div>
        <h2 id="add-dataset-title">Add another dataset?</h2>
        <p>
          The new file will remain an independent dataset and will be attached to this workspace as another layer.
          If it is not georeferenced, you will be taken to the georeference page first.
        </p>
        {error && <div className="workspace-dialog-error"><AlertCircle /><div><strong>{error.message}</strong><span>{error.details}</span></div></div>}
        {state === "uploading" ? (
          <div className="workspace-dialog-progress">
            <Loader2 className="animate-spin" />
            <span>Uploading and preparing dataset…</span>
            <strong>{progress}%</strong>
          </div>
        ) : (
          <div className="workspace-dialog-actions">
            <button type="button" className="workspace-secondary-button" onClick={onClose}>Cancel</button>
            <button type="button" className="workspace-primary-button" onClick={() => inputRef.current?.click()}>
              <Upload /> Select File
            </button>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".png,.jpg,.jpeg,.pdf,.dxf,.dwg,.svf,.zip,image/png,image/jpeg,application/pdf,application/zip"
          className="sr-only"
          onChange={selectFile}
        />
      </section>
    </div>
  )
}

export default function WorkspacePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedView = searchParams.get("view")
  const [layersOpen, setLayersOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [icons, setIcons] = useState([])
  const [dirty, setDirty] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [reopening, setReopening] = useState(false)
  const reopenInputRef = useRef(null)
  const workspace = useWorkspace(id)
  const view = requestedView === "database" ? "database" : "map"

  async function handleReopenExportedZip(event) {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file) return
    if (!confirmDiscard()) return
    setReopening(true)
    try {
      let targetId = null
      try {
        const res = await importMapProject(file)
        targetId = res.data?.id || res.data?.dataset_id || res.dataset_id
      } catch (projErr) {
        const res = await importDatasetZip(file)
        targetId = res.id || res.data?.id
      }
      if (targetId) {
        navigate(`/datasets/${targetId}/workspace?view=map`)
      }
    } catch (err) {
      workspace.setError({
        message: "Failed to reopen exported project package.",
        details: err?.response?.data?.detail || err?.message || "Invalid package.",
      })
    } finally {
      setReopening(false)
    }
  }

  async function handleExportMap() {
    if (exporting || workspace.saveState === "saving") return
    setExporting(true)
    workspace.setError(null)
    try {
      await downloadProjectExport(id, workspace.manifest?.name)
    } catch (requestError) {
      workspace.setError(readableApiError(
        requestError,
        "Unable to export the Map Studio package.",
      ))
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    listIcons(controller.signal).then(setIcons).catch(() => setIcons([]))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!requestedView && workspace.manifest?.active_view) {
      setSearchParams({ view: workspace.manifest.active_view }, { replace: true })
    }
  }, [requestedView, setSearchParams, workspace.manifest?.active_view])

  useEffect(() => {
    const warn = (event) => {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])

  function confirmDiscard() {
    return !dirty || window.confirm("Discard the unsaved record changes?")
  }

  function setView(nextView) {
    if (!confirmDiscard()) return
    setDirty(false)
    setSearchParams({ view: nextView }, { replace: true })
    workspace.updateState({ active_view: nextView }).catch(() => undefined)
  }

  function selectLayer(datasetId, kind) {
    workspace.setFilters({ datasetId, kind })
    setLayersOpen(false)
    if (view !== "database") setView("database")
  }

  async function handleAddedDataset(dataset) {
    await workspace.attachDataset(dataset.id)
    setAddOpen(false)
    if (!dataset.is_georeferenced) {
      const returnTo = `/datasets/${id}/workspace?view=database`
      navigate(`/datasets/${dataset.id}/georeference?returnTo=${encodeURIComponent(returnTo)}`)
      return
    }
    setView("map")
  }

  function handleDetach(member) {
    if (!window.confirm(`Detach “${member.name}” from this workspace? The dataset and its files will remain in the library.`)) return
    workspace.detachDataset(member.dataset_id).catch(() => undefined)
  }

  function selectMapRecord(recordId) {
    workspace.setSelectedRecordId(recordId)
    if (recordId) {
      const record = workspace.mapRecords.find((item) => item.id === recordId)
      if (record) workspace.setFilters({ datasetId: record.dataset_id, kind: record.kind })
      setView("database")
    }
  }

  function handleSwitchToMap(recordId) {
    workspace.setSelectedRecordId(recordId)
    setView("map")
  }

  if (workspace.loading) {
    return <div className="workspace-loading"><Loader2 className="animate-spin" /> Loading workspace…</div>
  }

  if (!workspace.manifest) {
    return (
      <div className="workspace-loading workspace-load-error">
        <AlertCircle />
        <strong>{workspace.error?.message || "Unable to load this workspace."}</strong>
        <span>{workspace.error?.details}</span>
        <Link to="/">Return to library</Link>
      </div>
    )
  }

  return (
    <div className="dataset-workspace-shell">
      <header className="workspace-topbar">
        <div className="workspace-topbar-left">
          <Link to="/" onClick={(event) => { if (!confirmDiscard()) event.preventDefault() }} aria-label="Back to library"><ArrowLeft /></Link>
          <button type="button" className="workspace-mobile-layers" onClick={() => setLayersOpen(true)} aria-label="Open layers"><Menu /></button>
          <div>
            <span className="workspace-eyebrow">Dataset workspace</span>
            <h1>{workspace.manifest.name}</h1>
          </div>
        </div>
        <div className="workspace-topbar-actions">
          <div className={`workspace-save-state save-${workspace.saveState}`}>
            {workspace.saveState === "saving" ? <Loader2 className="animate-spin" /> : workspace.saveState === "failed" ? <AlertCircle /> : <Check />}
            <span>{workspace.saveState === "saving" ? "Saving" : workspace.saveState === "failed" ? "Save failed" : "Saved"}</span>
            {workspace.saveState === "failed" && <button type="button" onClick={workspace.retrySave}><RefreshCw /> Retry</button>}
          </div>
          <button type="button" className="workspace-primary-button" onClick={() => setAddOpen(true)}><Plus /> Add dataset</button>
          <button
            type="button"
            className="workspace-secondary-button"
            onClick={handleExportMap}
            disabled={exporting || workspace.saveState === "saving"}
            title="Export this Map Studio project as a ZIP package"
          >
            {exporting ? <Loader2 className="animate-spin" /> : <Download />}
            <span>{exporting ? "Exporting…" : "Export Map (.zip)"}</span>
          </button>
          <input
            ref={reopenInputRef}
            type="file"
            accept=".zip,application/zip"
            className="sr-only"
            onChange={handleReopenExportedZip}
            disabled={reopening}
          />
          <button
            type="button"
            className="workspace-secondary-button"
            onClick={() => reopenInputRef.current?.click()}
            disabled={reopening}
            title="Reopen an exported Map Studio project package"
          >
            {reopening ? <Loader2 className="animate-spin" /> : <FolderOpen />}
            <span>{reopening ? "Opening…" : "Reopen Map (.zip)"}</span>
          </button>
          <EndSessionDialog />
        </div>
      </header>

      {workspace.error && (
        <div className="workspace-error-banner">
          <AlertCircle />
          <span><strong>{workspace.error.message}</strong> {workspace.error.details}</span>
          <button type="button" onClick={() => workspace.setError(null)} aria-label="Dismiss error"><X /></button>
        </div>
      )}

      <div className="workspace-body">
        <div className="workspace-desktop-layers">
          <WorkspaceLayerPanel
            members={workspace.manifest.members}
            selectedDatasetId={workspace.filters.datasetId}
            selectedKind={workspace.filters.kind}
            onSelect={selectLayer}
            onUpdate={(datasetId, patch) => workspace.updateMember(datasetId, patch).catch(() => undefined)}
            onReorder={(ids) => workspace.reorderMembers(ids).catch(() => undefined)}
            onDetach={handleDetach}
            onLayerChanged={() => workspace.refreshManifest().catch(() => undefined)}
          />
        </div>
        {layersOpen && (
          <div className="workspace-mobile-layer-sheet">
            <div className="workspace-sheet-backdrop" onClick={() => setLayersOpen(false)} />
            <WorkspaceLayerPanel
              members={workspace.manifest.members}
              selectedDatasetId={workspace.filters.datasetId}
              selectedKind={workspace.filters.kind}
              onSelect={selectLayer}
              onUpdate={(datasetId, patch) => workspace.updateMember(datasetId, patch).catch(() => undefined)}
              onReorder={(ids) => workspace.reorderMembers(ids).catch(() => undefined)}
              onDetach={handleDetach}
              onClose={() => setLayersOpen(false)}
              onLayerChanged={() => workspace.refreshManifest().catch(() => undefined)}
            />
          </div>
        )}

        <main className="workspace-canvas">
          {view === "map" ? (
            <WorkspaceMap
              members={workspace.manifest.members}
              records={workspace.mapRecords}
              selectedRecordId={workspace.selectedRecordId}
              onSelectRecord={selectMapRecord}
              savedCamera={workspace.manifest.camera}
              onCameraChange={(camera) => workspace.updateState({ camera }).catch(() => undefined)}
            />
          ) : (
            <WorkspaceTable
              recordsData={workspace.records}
              filters={workspace.filters}
              onFiltersChange={workspace.setFilters}
              loading={workspace.recordsLoading}
              members={workspace.manifest.members}
              icons={icons}
              selectedRecordId={workspace.selectedRecordId}
              onSelectRecord={workspace.setSelectedRecordId}
              onMemberUpdate={workspace.updateMember}
              onRecordsRefresh={() => Promise.all([workspace.refreshRecords(), workspace.refreshMapRecords()])}
              onDirtyChange={setDirty}
              workspaceId={id}
              onAddDataset={() => setAddOpen(true)}
              onSwitchToMap={handleSwitchToMap}
            />
          )}
        </main>
      </div>

      <nav className="workspace-bottom-dock" aria-label="Workspace views">
        <div className="workspace-bottom-dock-inner">
          <button
            type="button"
            className={`workspace-dock-item ${view === "map" ? "is-active" : ""}`}
            onClick={() => setView("map")}
            aria-label="Interactive Map view"
          >
            <MapIcon className="size-4" />
            <span>Map</span>
            {workspace.manifest.members.length > 0 && (
              <span className="workspace-dock-badge">
                {workspace.manifest.members.filter((m) => m.visible).length}
              </span>
            )}
          </button>
          <button
            type="button"
            className={`workspace-dock-item ${view === "database" ? "is-active" : ""}`}
            onClick={() => setView("database")}
            aria-label="Database Table view"
          >
            <Database className="size-4" />
            <span>Database</span>
            {workspace.records.total > 0 && (
              <span className="workspace-dock-badge">{workspace.records.total}</span>
            )}
          </button>
          <div className="workspace-dock-divider" />
          <button
            type="button"
            className="workspace-dock-item workspace-dock-action"
            onClick={() => setAddOpen(true)}
            aria-label="Add or merge another dataset"
            title="Add another dataset to workspace"
          >
            <Plus className="size-4" />
            <span>Add Dataset</span>
          </button>
          <button
            type="button"
            className={`workspace-dock-item md:hidden ${layersOpen ? "is-active" : ""}`}
            onClick={() => setLayersOpen((value) => !value)}
            aria-label="Toggle Layers Panel"
            title="Layers hierarchy"
          >
            <Layers className="size-4" />
            <span>Layers</span>
          </button>
        </div>
      </nav>

      <AddDatasetDialog open={addOpen} onClose={() => setAddOpen(false)} onUploaded={handleAddedDataset} />
    </div>
  )
}
