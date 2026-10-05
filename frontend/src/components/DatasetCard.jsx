import React from "react"
import { Link } from "react-router-dom"

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
  if (!Number.isFinite(bytes)) return "Unknown size"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function statusLabel(dataset) {
  if (dataset.tile_status === "completed") return "Ready"
  if (
    dataset.tile_status === "failed" ||
    dataset.process_status === "failed" ||
    dataset.georeference_status === "failed"
  ) {
    return "Processing failed"
  }
  if (dataset.tile_status === "processing") return "Generating tiles"
  if (dataset.process_status === "processing") return "Processing raster"
  if (dataset.georeference_status === "processing") return "Georeferencing"
  return "Uploaded"
}

export default function DatasetCard({ dataset }) {
  return (
    <article className="flex min-h-60 flex-col rounded-utility border border-hairline bg-white p-6">
      <h2 className="text-[21px] font-semibold leading-[1.19] tracking-[0.231px] text-ink">
        {displayName(dataset.filename)}
      </h2>
      <p className="mt-1 break-all text-[17px] text-muted">{dataset.filename}</p>
      <p className="mt-3 text-[14px] leading-[1.43] tracking-[-0.224px] text-muted">
        {formatName(dataset.filename, dataset.metadata)} · {fileSize(dataset.file_size)}
      </p>
      <p className="mt-2 text-[12px] tracking-[-0.12px] text-muted">
        {new Date(dataset.created_at).toLocaleDateString()}
      </p>
      <div className="mt-auto flex items-end justify-between gap-4 pt-8">
        <p className="text-[14px] text-muted">{statusLabel(dataset)}</p>
        <Link className="text-action shrink-0" to={`/datasets/${dataset.id}`}>
          Open
          <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current" strokeWidth="1.8">
            <path d="M4 10h11M11 6l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>
    </article>
  )
}

export { displayName, fileSize, formatName, statusLabel }
