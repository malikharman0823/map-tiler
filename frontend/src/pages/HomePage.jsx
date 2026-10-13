import React, { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  listDatasets,
  deleteDataset,
  readableApiError,
  importProjectFolder,
  importMapProject,
  importDatasetZip,
  uploadDataset,
} from "../api"
import UploadBox, { ACCEPTED_FORMATS } from "../components/UploadBox"
import UploadStatus from "../components/UploadStatus"
import DatasetCard from "../components/DatasetCard"
import TopHeader from "../components/TopHeader"
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
  FolderOpen,
  Archive,
  Loader2,
  Sliders,
  Globe2,
  FileCheck2,
  MapPinned,
  Database,
  X,
  AlertCircle,
  Layers,
} from "lucide-react"

export default function HomePage() {
  const navigate = useNavigate()
  const replacementInputRef = useRef(null)

  // Upload state
  const [file, setFile] = useState(null)
  const [state, setState] = useState("idle")
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Session dataset catalog state
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [datasetToDelete, setDatasetToDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const loadDatasets = () => {
    setLoading(true)
    listDatasets()
      .then(setDatasets)
      .catch((err) => {
        if (err.code !== "ERR_CANCELED") {
          console.warn("Unable to load workspace datasets:", err)
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadDatasets()
  }, [])

  function selectFile(nextFile) {
    setFile(nextFile)
    setState("selected")
    setProgress(0)
    setResult(null)
    setError(null)
  }

  function removeFile() {
    setFile(null)
    setState("idle")
    setProgress(0)
  }

  async function upload() {
    if (!file) return
    setState("uploading")
    setProgress(0)
    setError(null)
    try {
      const isZip = (file.name || "").toLowerCase().endsWith(".zip")
      const uploadFn = isZip ? importDatasetZip : uploadDataset
      const uploaded = await uploadFn(file, (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
      })
      setResult(uploaded)
      setFile(null)
      loadDatasets()

      if (uploaded.is_georeferenced) {
        navigate(`/datasets/${uploaded.id}/workspace?view=map`)
        return
      }
      setState("success")
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to upload the file."))
      setState("error")
    }
  }

  function continueAfterUpload() {
    if (!result) return
    if (result.is_georeferenced) {
      navigate(`/datasets/${result.id}/workspace?view=map`)
    } else {
      navigate(`/datasets/${result.id}/workspace?view=database`)
    }
  }

  const handleReopenZip = async (event) => {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return
    setImporting(true)
    setError(null)
    try {
      let targetId = null
      try {
        const res = await importMapProject(selectedFile)
        targetId = res.data?.id || res.data?.dataset_id || res.dataset_id
      } catch {
        const res = await importDatasetZip(selectedFile)
        targetId = res.id || res.data?.id
      }
      if (targetId) {
        navigate(`/datasets/${targetId}/workspace?view=map`)
      } else {
        loadDatasets()
      }
    } catch (err) {
      setError(readableApiError(err, "Failed to reopen exported project package."))
    } finally {
      setImporting(false)
      event.target.value = ""
    }
  }

  const handleImportFolder = async (event) => {
    const files = Array.from(event.target.files)
    if (!files.length) return
    setImporting(true)
    setError(null)
    try {
      const res = await importProjectFolder(files)
      navigate(`/datasets/${res.dataset_id}`)
    } catch (err) {
      setError(readableApiError(err, "Failed to import project folder."))
    } finally {
      setImporting(false)
      event.target.value = ""
    }
  }

  const handleDeleteConfirm = async () => {
    if (!datasetToDelete) return
    setDeleting(true)
    try {
      await deleteDataset(datasetToDelete.id)
      setDatasets((prev) => prev.filter((d) => d.id !== datasetToDelete.id))
      setDatasetToDelete(null)
    } catch (err) {
      setError(readableApiError(err, "Failed to delete dataset."))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#f5f5f7] text-[#1d1d1f]">
      <TopHeader breadcrumbs={[{ label: "Upload Dataset" }]} />

      <main className="flex-1 pb-16">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-8 flex flex-col gap-8">
          {/* Header Section */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-6 border-b border-[#e0e0e0]">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-[#7a7a7a] mb-1">
                <span>Spatial Workspace</span>
                <span>•</span>
                <span className="text-[#0066cc]">New Dataset</span>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-[#1d1d1f]">
                Upload Dataset
              </h1>
              <p className="text-sm text-[#7a7a7a] mt-1.5 max-w-xl">
                Upload GeoTIFF, PNG, JPG, PDF, CAD (.dxf, .dwg), SVF (.svf), GeoJSON, Shapefile (.zip), or Map Studio project packages.
              </p>
            </div>

            <div className="flex items-center gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={handleReopenZip}
                className="hidden"
                id="reopen-zip-input"
                disabled={importing}
              />
              <Button
                asChild
                variant="outline"
                size="sm"
                className="h-9 rounded-full border-[#0066cc]/30 bg-[#f0f7ff] hover:bg-[#e1effe] text-xs text-[#0066cc] cursor-pointer font-medium"
              >
                <label htmlFor="reopen-zip-input">
                  {importing ? (
                    <Loader2 className="size-3.5 mr-1.5 animate-spin text-[#0066cc]" />
                  ) : (
                    <Archive className="size-3.5 mr-1.5 text-[#0066cc]" />
                  )}
                  <span>{importing ? "Opening…" : "Reopen Exported Map (.zip)"}</span>
                </label>
              </Button>

              <input
                type="file"
                multiple
                webkitdirectory=""
                directory=""
                onChange={handleImportFolder}
                className="hidden"
                id="import-folder-input"
                disabled={importing}
              />
              <Button
                asChild
                variant="outline"
                size="sm"
                className="h-9 rounded-full border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] text-xs text-[#1d1d1f] cursor-pointer"
              >
                <label htmlFor="import-folder-input">
                  {importing ? (
                    <Loader2 className="size-3.5 mr-1.5 animate-spin text-[#0066cc]" />
                  ) : (
                    <FolderOpen className="size-3.5 mr-1.5 text-[#7a7a7a]" />
                  )}
                  <span>{importing ? "Importing…" : "Open Project Folder"}</span>
                </label>
              </Button>

              <div className="flex items-center gap-2 bg-[#ffffff] border border-[#e0e0e0] px-3.5 py-1.5 rounded-full shadow-xs">
                <span className="size-2 rounded-full bg-[#34c759] animate-pulse"></span>
                <span className="text-xs font-medium text-[#1d1d1f]">Ready</span>
              </div>
            </div>
          </div>

          {/* Global Error Alert */}
          {error && (
            <div className="rounded-[18px] border border-[#ff3b30]/30 bg-[#ff3b30]/5 p-4 flex items-center gap-3">
              <AlertCircle className="size-5 text-[#ff3b30] shrink-0" />
              <div className="text-xs">
                <p className="font-semibold text-[#ff3b30]">{error.message || "An error occurred"}</p>
                {error.details && <p className="text-[#ff3b30]/80 mt-0.5">{error.details}</p>}
              </div>
            </div>
          )}

          {/* Main Upload Area */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Dropzone & Upload Box (7 Cols) */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              {state === "idle" ? (
                <UploadBox disabled={false} onSelect={selectFile} />
              ) : (
                <UploadStatus
                  state={state}
                  file={file}
                  progress={progress}
                  result={result}
                  error={error}
                  onRemove={removeFile}
                  onReplace={() => replacementInputRef.current?.click()}
                  onUpload={upload}
                  onRetry={() => setState(file ? "selected" : "idle")}
                  onOpen={continueAfterUpload}
                />
              )}
            </div>

            {/* Right Column: Ingestion Parameters (5 Cols) */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="border border-[#e0e0e0] rounded-[18px] bg-[#ffffff] p-6 space-y-5 shadow-xs">
                <div className="flex items-center justify-between pb-3 border-b border-[#f0f0f0]">
                  <div className="flex items-center gap-2">
                    <Sliders className="size-4 text-[#0066cc]" />
                    <h3 className="text-sm font-semibold text-[#1d1d1f]">
                      Ingestion Parameters
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-[#7a7a7a] px-2 py-0.5 rounded-full bg-[#f5f5f7] border border-[#e0e0e0]">
                    Auto
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-medium text-[#1d1d1f] flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Globe2 className="size-3.5 text-[#7a7a7a]" />
                      Georeference detection
                    </span>
                    <span className="text-[10px] text-[#0066cc] font-mono font-semibold">
                      AUTOMATIC
                    </span>
                  </label>
                  <div className="w-full bg-[#f5f5f7] border border-[#e0e0e0] rounded-xl py-2 px-3 text-xs text-[#1d1d1f] font-mono flex items-center justify-between">
                    <span>Raster metadata + sidecars</span>
                    <FileCheck2 className="size-3.5 text-[#34c759]" />
                  </div>
                  <p className="text-[11px] text-[#7a7a7a]">
                    Georeferenced rasters open directly on the map. Raw rasters allow point-based georeferencing.
                  </p>
                </div>

                <div className="pt-2 border-t border-[#f0f0f0] space-y-3">
                  <div className="flex items-start justify-between gap-3 p-3 rounded-xl bg-[#fafafc] border border-[#e0e0e0]">
                    <div className="space-y-0.5">
                      <div className="text-xs font-semibold text-[#1d1d1f]">
                        Auto-Tiling Pipeline
                      </div>
                      <p className="text-[11px] text-[#7a7a7a]">
                        Rasters are automatically processed and converted into Slippy tiles.
                      </p>
                    </div>
                    <span className="size-2 rounded-full bg-[#34c759] mt-1 shrink-0"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Active Datasets in this Session (if any exist) */}
          {datasets.length > 0 && (
            <div className="pt-8 border-t border-[#e0e0e0] space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="size-4 text-[#0066cc]" />
                  <h2 className="text-sm font-semibold tracking-tight text-[#1d1d1f]">
                    Active Workspace Datasets ({datasets.length})
                  </h2>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {datasets.map((dataset) => (
                  <DatasetCard
                    key={dataset.id}
                    dataset={dataset}
                    viewMode="grid"
                    onDeleteClick={setDatasetToDelete}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <input
          ref={replacementInputRef}
          type="file"
          accept={ACCEPTED_FORMATS}
          className="sr-only"
          onChange={(event) => {
            const [nextFile] = event.target.files
            if (nextFile) selectFile(nextFile)
          }}
        />
      </main>

      {/* Un-georeferenced Dialog */}
      {state === "success" && result && !result.is_georeferenced && (
        <div className="workspace-dialog-backdrop" role="presentation">
          <section
            className="workspace-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-route-title"
          >
            <button
              type="button"
              className="workspace-dialog-close"
              onClick={() => setState("idle")}
              aria-label="Close"
            >
              <X />
            </button>
            <div className="workspace-dialog-icon">
              <MapPinned />
            </div>
            <h2 id="upload-route-title">This raster is not georeferenced</h2>
            <p>The dataset is safely stored. Choose where you want to continue.</p>
            <div className="workspace-dialog-actions workspace-dialog-actions-stacked">
              <button
                type="button"
                className="workspace-primary-button"
                onClick={() =>
                  navigate(
                    `/datasets/${result.id}/georeference?returnTo=${encodeURIComponent(
                      `/datasets/${result.id}/workspace?view=database`
                    )}`
                  )
                }
              >
                <MapPinned /> Open georeferencer
              </button>
              <button
                type="button"
                className="workspace-secondary-button"
                onClick={() => navigate(`/datasets/${result.id}/workspace?view=database`)}
              >
                <Database /> Inspect database first
              </button>
            </div>
          </section>
        </div>
      )}

      {/* Delete Dataset Confirmation Dialog */}
      <AlertDialog
        open={Boolean(datasetToDelete)}
        onOpenChange={(open) => !open && setDatasetToDelete(null)}
      >
        <AlertDialogContent className="rounded-[20px] bg-[#ffffff] border border-[#e0e0e0] text-[#1d1d1f] shadow-lg max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-base font-semibold text-[#1d1d1f]">
              Delete Dataset?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-xs text-[#7a7a7a] mt-1.5">
              Are you sure you want to delete{" "}
              <strong className="text-[#1d1d1f]">
                {datasetToDelete?.name || datasetToDelete?.filename}
              </strong>
              ? This action will permanently remove all associated rasters, vector caches, and tilesets.
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
              onClick={handleDeleteConfirm}
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
