import React from "react"
import { Link } from "react-router-dom"
import { datasetSourceImageUrl } from "../api"

function displayName(filename) {
  const withoutExtension = filename.replace(/(\.osm)?\.[^.]+$/i, "")
  return withoutExtension
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatName(filename, metadata) {
  if (metadata?.driver) return metadata.driver === "GTiff" ? "TIFF" : metadata.driver
  const lower = filename.toLowerCase()
  if (lower.endsWith(".osm.pbf")) return "OSM PBF"
  const extension = lower.split(".").pop()
  return extension === "tif" || extension === "tiff"
    ? "TIFF"
    : extension.toUpperCase()
}

function fileSize(bytes) {
  if (!Number.isFinite(bytes)) return "Unknown"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function getStatusDetails(dataset) {
  let color = "bg-zinc-500"
  let text = "Uploaded"
  let isPulsing = false
  
  if (dataset.tile_status === "completed") {
    color = "bg-emerald-400"
    text = "Ready"
  } else if (
    dataset.tile_status === "failed" ||
    dataset.process_status === "failed" ||
    dataset.georeference_status === "failed"
  ) {
    color = "bg-red-400"
    text = "Failed"
  } else if (dataset.tile_status === "processing" || dataset.process_status === "processing" || dataset.georeference_status === "processing") {
    color = "bg-amber-400"
    text = "Processing"
    isPulsing = true
  }

  return { color, text, isPulsing }
}

export default function DatasetCard({ dataset, viewMode = "grid" }) {
  const status = getStatusDetails(dataset)
  const format = formatName(dataset.filename, dataset.metadata)
  const size = fileSize(dataset.file_size)
  const crs = dataset.metadata?.crs || "Unknown CRS"
  const name = displayName(dataset.filename)
  const dateStr = new Date(dataset.updated_at || dataset.created_at).toLocaleDateString()

  // For rasters, we might have a source image thumbnail. For vectors, maybe an SVG or default pattern.
  const isRaster = format.includes("TIF") || format.includes("PNG") || format.includes("JPG")

  if (viewMode === "list") {
    return (
      <div className="group rounded-md border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-900/80 transition-all duration-200 flex items-center p-3 gap-4">
        {/* Minimal icon/thumbnail */}
        <div className="w-10 h-10 rounded bg-zinc-950 border border-zinc-800 flex items-center justify-center shrink-0 overflow-hidden">
          {isRaster ? (
            <img src={datasetSourceImageUrl(dataset.id)} alt="Preview" className="w-full h-full object-cover opacity-60" onError={(e) => { e.target.style.display = 'none' }} />
          ) : (
            <span className="material-symbols-outlined text-[20px] text-zinc-600">map</span>
          )}
        </div>
        
        {/* Info */}
        <div className="flex-1 min-w-0 flex flex-col justify-center">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-sm text-zinc-100 truncate group-hover:text-white transition-colors">{name}</h3>
            <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-full border border-zinc-800 bg-zinc-950/80 text-[10px] font-medium text-zinc-300">
              <span className={`w-1.5 h-1.5 rounded-full ${status.color} ${status.isPulsing ? 'animate-pulse' : ''}`}></span>
              {status.text}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <p className="font-mono text-[11px] text-zinc-500 truncate">{dataset.filename}</p>
            <span className="text-zinc-700 text-[10px]">•</span>
            <span className="text-zinc-500 font-mono text-[10px]">{format}</span>
            <span className="text-zinc-700 text-[10px]">•</span>
            <span className="text-zinc-500 font-mono text-[10px]">{size}</span>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-zinc-500 hidden sm:block mr-2">Updated {dateStr}</span>
          <Link to={`/datasets/${dataset.id}`} className="inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 hover:border-zinc-700 text-zinc-200 text-xs font-medium transition-all">
            <span>Open</span>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="group rounded-lg border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 transition-all duration-200 flex flex-col justify-between overflow-hidden">
      <div>
        {/* Thumbnail preview area */}
        <div className="relative h-40 bg-zinc-950 border-b border-zinc-800 flex items-center justify-center overflow-hidden">
          {isRaster ? (
             <img src={datasetSourceImageUrl(dataset.id)} alt="Preview" className="absolute inset-0 w-full h-full object-cover opacity-40 group-hover:opacity-50 transition-opacity" onError={(e) => { e.target.style.display = 'none' }} />
          ) : (
            <div className="absolute inset-0 opacity-40 group-hover:opacity-50 transition-opacity bg-zinc-900 flex items-center justify-center">
              <span className="material-symbols-outlined text-[48px] text-zinc-800">map</span>
            </div>
          )}
          
          {/* Badges on image */}
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-zinc-800 bg-zinc-950/80 backdrop-blur text-[11px] font-medium text-zinc-300">
              <span className={`w-1.5 h-1.5 rounded-full ${status.color} ${status.isPulsing ? 'animate-pulse' : ''}`}></span>
              {status.text}
            </span>
          </div>
        </div>

        {/* Card Header & Metadata */}
        <div className="p-4 pb-3 space-y-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-medium text-sm text-zinc-100 truncate group-hover:text-white transition-colors" title={name}>{name}</h3>
              <p className="font-mono text-[11px] text-zinc-500 truncate mt-0.5" title={dataset.filename}>{dataset.filename}</p>
            </div>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-zinc-800 bg-zinc-900 text-zinc-300">{format}</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-zinc-800 bg-zinc-900 text-zinc-400">{size}</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-zinc-800 bg-zinc-900 text-zinc-400">{crs}</span>
          </div>
        </div>
      </div>

      {/* Card Footer */}
      <div className="p-4 pt-3 border-t border-zinc-800/80 space-y-3">
        <div className="flex items-center justify-between text-[11px] text-zinc-500">
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[13px]">schedule</span>
            {dateStr}
          </span>
        </div>

        {status.isPulsing ? (
          <button className="w-full inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md border border-zinc-800/60 bg-zinc-900/50 text-zinc-500 text-xs font-medium cursor-not-allowed" disabled>
             <span className="material-symbols-outlined text-[14px] animate-spin">refresh</span>
             <span>Processing...</span>
          </button>
        ) : (
          <Link to={`/datasets/${dataset.id}`} className="w-full inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 hover:border-zinc-700 text-zinc-200 text-xs font-medium transition-all">
            <span>Open in Studio</span>
            <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
          </Link>
        )}
      </div>
    </div>
  )
}

export { displayName, fileSize, formatName }
