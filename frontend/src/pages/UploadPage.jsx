import React, { useRef, useState } from "react"
import { Link } from "react-router-dom"
import { readableApiError, uploadDataset, importMapProject } from "../api"
import UploadBox, { ACCEPTED_FORMATS } from "../components/UploadBox"
import UploadStatus from "../components/UploadStatus"
import TopHeader from "../components/TopHeader"

export default function UploadPage() {
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
      let uploaded;
      if (file.name.toLowerCase().endsWith(".mtmap")) {
        const importRes = await importMapProject(file, (event) => {
          if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
        })
        // Format the result to match the uploadDataset response structure expected by UploadStatus
        uploaded = { id: importRes.dataset_id, filename: importRes.name }
      } else {
        const uploadRes = await uploadDataset(file, (event) => {
          if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
        })
        uploaded = uploadRes
      }
      setResult(uploaded)
      setFile(null)
      setState("success")
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to upload the file."))
      setState("error")
    }
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopHeader 
        breadcrumbs={[{ label: "Upload", path: "/upload" }]} 
        actions={
          <button type="button" className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-ink hover:bg-[#202020] text-xs font-medium text-white transition-colors shadow-xs">
            <span className="material-symbols-outlined text-[15px]">upload_file</span>
            <span>Upload</span>
          </button>
        }
      />
      <main className="flex-1 pb-12">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col gap-8">
          {/* Header & Breadcrumb / Quota Info */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-6 border-b border-hairline">
            <div>
              <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors mb-2 group">
                <span className="material-symbols-outlined text-[15px] group-hover:-translate-x-0.5 transition-transform">arrow_back</span>
                <span>Back to datasets</span>
              </Link>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl font-semibold tracking-tight text-ink">Upload dataset</h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono border border-hairline bg-pearl text-muted">MVP</span>
              </div>
              <p className="text-sm text-muted mt-1 max-w-xl">
                Add vector features, high-resolution raster tiles, or spatial archives to your MapTiler workspace.
              </p>
            </div>
            
            <div className="flex items-center gap-4 bg-white border border-hairline px-4 py-2.5 rounded-lg shrink-0">
              <div className="flex items-center gap-1.5 text-xs text-ink">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span>Backend Ready</span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="inline-flex items-center rounded-lg bg-white p-1 border border-hairline text-xs">
              <button type="button" className="inline-flex items-center justify-center whitespace-nowrap rounded-md bg-pearl px-3 py-1 font-medium text-ink shadow-sm">
                File Ingestion
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Dropzone & Formats (7 Cols) */}
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
                />
              )}

              {/* Supported Format Cards */}
              <div className="border border-hairline rounded-lg bg-white p-4">
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-hairline">
                  <span className="text-xs font-medium text-ink">Supported Formats</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-3 rounded-md bg-[#f8f9fa] border border-hairline flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-xs font-medium text-ink">
                      <span>Raster Images</span>
                      <span className="text-[10px] font-mono text-muted bg-[#e0e2e5] px-1.5 py-0.5 rounded">JPG / PNG</span>
                    </div>
                    <p className="text-[11px] text-muted">
                      Upload a map image, floor plan or scanned map. If it has no geographic reference, you can manually georeference it.
                    </p>
                  </div>
                  
                  <div className="p-3 rounded-md bg-[#f8f9fa] border border-hairline flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-xs font-medium text-ink">
                      <span>GeoTIFF</span>
                      <span className="text-[10px] font-mono text-muted bg-[#e0e2e5] px-1.5 py-0.5 rounded">TIF / TIFF</span>
                    </div>
                    <p className="text-[11px] text-muted">
                      Upload a georeferenced raster. If spatial metadata is valid, it can be placed directly on the map.
                    </p>
                  </div>

                  <div className="p-3 rounded-md bg-[#f8f9fa] border border-hairline flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-xs font-medium text-ink">
                      <span>Custom Tiles</span>
                      <span className="text-[10px] font-mono text-muted bg-[#e0e2e5] px-1.5 py-0.5 rounded">MBTiles</span>
                    </div>
                    <p className="text-[11px] text-muted">
                      Upload generated map tiles.
                    </p>
                  </div>

                  <div className="p-3 rounded-md bg-[#f8f9fa] border border-hairline flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-xs font-medium text-ink">
                      <span>Map Project</span>
                      <span className="text-[10px] font-mono text-muted bg-[#e0e2e5] px-1.5 py-0.5 rounded">MTMAP</span>
                    </div>
                    <p className="text-[11px] text-muted">
                      Open a complete MapTiler Clone project.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Ingestion Parameters */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="border border-hairline rounded-lg bg-white p-5 space-y-5">
                <div>
                  <h3 className="text-sm font-medium text-ink">Ingestion parameters</h3>
                  <p className="text-xs text-muted mt-0.5">Parameters are auto-detected by MapTiler MVP backend.</p>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-ink flex items-center justify-between">
                    <span>Coordinate Reference System (CRS)</span>
                    <span className="text-[10px] text-muted font-mono">AUTO-DETECT</span>
                  </label>
                  <div className="relative">
                    <select disabled className="w-full bg-[#f8f9fa] border border-hairline rounded-md py-1.5 px-3 text-xs text-muted appearance-none pr-8 font-mono cursor-not-allowed">
                      <option>EPSG:4326 / Detected</option>
                    </select>
                  </div>
                </div>
                <div className="space-y-3 pt-1">
                  <label className="flex items-start justify-between gap-3 cursor-not-allowed group opacity-60">
                    <div className="space-y-0.5">
                      <div className="text-xs font-medium text-ink">Auto-Process Raster</div>
                      <p className="text-[11px] text-muted">Automatically tiled if georeferenced</p>
                    </div>
                    <input disabled checked type="checkbox" className="mt-0.5 h-4 w-4 rounded border-[#c0c0c0] bg-[#f8f9fa] text-ink cursor-not-allowed" />
                  </label>
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
    </div>
  )
}
