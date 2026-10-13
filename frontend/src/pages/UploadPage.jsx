import React, { useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { importDatasetZip, uploadDataset, readableApiError } from "../api"
import UploadBox, { ACCEPTED_FORMATS } from "../components/UploadBox"
import UploadStatus from "../components/UploadStatus"
import TopHeader from "../components/TopHeader"
import { Button } from "@/components/ui/button"
import {
  ArrowLeft,
  Upload,
  CheckCircle,
  Sliders,
  Globe2,
  FileCheck2,
  Database,
  MapPinned,
  X,
} from "lucide-react"

export default function UploadPage() {
  const navigate = useNavigate()
  const replacementInputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [state, setState] = useState("idle")
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

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
    try {
      const isZip = (file.name || "").toLowerCase().endsWith(".zip")
      const uploadFn = isZip ? importDatasetZip : uploadDataset
      const uploaded = await uploadFn(file, (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
      })
      setResult(uploaded)
      setFile(null)
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
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#f5f5f7] text-[#1d1d1f]">
      <TopHeader
        breadcrumbs={[
          { label: "Datasets", path: "/" },
          { label: "Upload Dataset" },
        ]}
        actions={
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-8 rounded-full border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] text-xs text-[#1d1d1f]"
          >
            <Link to="/">
              <ArrowLeft className="size-3.5 mr-1" />
              <span>Back to Datasets</span>
            </Link>
          </Button>
        }
      />

      <main className="flex-1 pb-16">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-8 flex flex-col gap-8">
          {/* Header Section */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-6 border-b border-[#e0e0e0]">
            <div>
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-xs text-[#7a7a7a] hover:text-[#0066cc] transition-colors mb-2.5 group"
              >
                <ArrowLeft className="size-3.5 group-hover:-translate-x-0.5 transition-transform" />
                <span>Back to datasets</span>
              </Link>
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-semibold tracking-tight text-[#1d1d1f]">
                  Upload Dataset
                </h1>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono border border-[#e0e0e0] bg-[#ffffff] text-[#7a7a7a] font-semibold">
                  MVP
                </span>
              </div>
              <p className="text-sm text-[#7a7a7a] mt-1.5 max-w-xl">
                Upload PNG, JPG, PDF, CAD (.dxf, .dwg), SVF, or exported Map Studio project archives (.zip).
              </p>
            </div>

            <div className="flex items-center gap-2 bg-[#ffffff] border border-[#e0e0e0] px-3.5 py-2 rounded-full shrink-0 shadow-xs">
              <span className="size-2 rounded-full bg-[#34c759] animate-pulse"></span>
              <span className="text-xs font-medium text-[#1d1d1f]">Backend Ready</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Dropzone & Upload Box (7 Cols) */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              {state === "idle" ? (
                <UploadBox
                  disabled={false}
                  onSelect={selectFile}
                />
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
                    Georeferenced rasters open on the map. Raw rasters let you choose georeferencing or database inspection.
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

      {state === "success" && result && !result.is_georeferenced && (
        <div className="workspace-dialog-backdrop" role="presentation">
          <section className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-route-title">
            <button type="button" className="workspace-dialog-close" onClick={() => setState("idle")} aria-label="Close"><X /></button>
            <div className="workspace-dialog-icon"><MapPinned /></div>
            <h2 id="upload-route-title">This raster is not georeferenced</h2>
            <p>The dataset is safely stored. Choose where you want to continue.</p>
            <div className="workspace-dialog-actions workspace-dialog-actions-stacked">
              <button type="button" className="workspace-primary-button" onClick={() => navigate(`/datasets/${result.id}/georeference?returnTo=${encodeURIComponent(`/datasets/${result.id}/workspace?view=database`)}`)}>
                <MapPinned /> Open georeferencer
              </button>
              <button type="button" className="workspace-secondary-button" onClick={() => navigate(`/datasets/${result.id}/workspace?view=database`)}>
                <Database /> Inspect database first
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
