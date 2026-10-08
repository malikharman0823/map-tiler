import React from "react"
import { Link } from "react-router-dom"
import { fileSize } from "./DatasetCard"

export default function UploadStatus({
  state,
  file,
  progress,
  result,
  error,
  onRemove,
  onReplace,
  onUpload,
  onRetry,
}) {
  if (state === "success") {
    return (
      <div className="relative bg-white border border-[#c0c0c0] transition-all rounded-lg p-10 flex flex-col items-center justify-center text-center">
        <div className="w-12 h-12 rounded-lg bg-emerald-100 border border-emerald-200 flex items-center justify-center text-emerald-600 mb-4">
          <span className="material-symbols-outlined text-[24px]">check_circle</span>
        </div>
        <h3 className="text-lg font-medium text-ink mb-1">Upload complete</h3>
        <p className="text-xs text-muted max-w-sm mb-6 font-mono truncate">{result.filename}</p>
        <Link to={`/datasets/${result.id}`} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-ink hover:bg-[#202020] text-sm font-semibold text-white transition-colors shadow-sm">
          <span>Open dataset in Studio</span>
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>
      </div>
    )
  }

  if (state === "error") {
    return (
      <div className="relative bg-white border border-red-200 transition-all rounded-lg p-10 flex flex-col items-center justify-center text-center">
        <div className="w-12 h-12 rounded-lg bg-red-50 border border-red-100 flex items-center justify-center text-red-600 mb-4">
          <span className="material-symbols-outlined text-[24px]">error</span>
        </div>
        <h3 className="text-lg font-medium text-ink mb-1">Upload failed</h3>
        <p className="text-xs text-red-600 mt-2 max-w-sm font-medium">{error.message}</p>
        <p className="text-xs text-muted mt-1 max-w-sm mb-6">{error.details}</p>
        <div className="flex gap-3">
          <button type="button" onClick={onRetry} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md border border-hairline bg-white hover:bg-pearl text-sm font-medium text-ink transition-colors">
            Try again
          </button>
          <button type="button" onClick={onRemove} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-white hover:bg-pearl text-sm font-medium text-red-600 border border-red-200 transition-colors">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative bg-white border border-hairline transition-all rounded-lg p-8 flex flex-col justify-between min-h-[360px]">
      <div>
        <div className="flex items-center justify-between mb-4">
           <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-[#c0c0c0] bg-pearl text-muted">
             {state === "uploading" ? "UPLOADING" : "READY TO UPLOAD"}
           </span>
           <span className="text-xs text-muted font-mono">{fileSize(file.size)}</span>
        </div>
        <div className="flex items-start gap-3">
           <div className="w-10 h-10 rounded border border-hairline bg-pearl flex items-center justify-center text-muted shrink-0">
             <span className="material-symbols-outlined text-[20px]">description</span>
           </div>
           <div className="min-w-0 flex-1">
             <h3 className="text-sm font-medium text-ink truncate">{file.name}</h3>
             <p className="text-xs text-muted mt-0.5">Will be uploaded to your workspace.</p>
           </div>
        </div>
      </div>

      {state === "uploading" ? (
        <div className="mt-8 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted">Uploading chunks...</span>
            <span className="text-ink font-mono">{progress}%</span>
          </div>
          <div className="h-1.5 bg-[#e0e2e5] rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-[width] duration-300 rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-hairline pt-6">
          <button type="button" onClick={onUpload} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-ink hover:bg-[#202020] text-sm font-semibold text-white transition-colors shadow-sm">
            <span className="material-symbols-outlined text-[18px]">upload</span>
            <span>Start Upload</span>
          </button>
          <button type="button" onClick={onReplace} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md border border-hairline bg-white hover:bg-pearl text-sm font-medium text-ink transition-colors">
            Replace
          </button>
          <button type="button" onClick={onRemove} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md hover:bg-red-50 text-sm font-medium text-red-600 transition-colors ml-auto">
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}
