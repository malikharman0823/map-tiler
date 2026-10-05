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
      <div className="flex min-h-[360px] flex-col items-center justify-center rounded-utility border border-hairline bg-white p-8 text-center">
        <p className="text-[28px] font-semibold leading-[1.14]">Upload complete</p>
        <p className="mt-3 max-w-xl break-all text-[17px] text-muted">{result.filename}</p>
        <Link className="primary-button mt-8" to={`/datasets/${result.id}`}>
          Open dataset
        </Link>
      </div>
    )
  }

  if (state === "error") {
    return (
      <div className="flex min-h-[360px] flex-col items-center justify-center rounded-utility border border-hairline bg-white p-8 text-center">
        <p className="text-[28px] font-semibold leading-[1.14]">Unable to upload the file</p>
        <div className="error-panel mt-6 max-w-xl" role="alert">
          <p className="font-semibold">{error.message}</p>
          <p className="mt-2 text-[14px] leading-[1.43] text-muted">{error.details}</p>
        </div>
        <button type="button" className="primary-button mt-8" onClick={onRetry}>
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="flex min-h-[360px] flex-col justify-between rounded-utility border border-hairline bg-white p-6 phone:p-10">
      <div>
        <p className="text-[14px] text-muted">
          {state === "uploading" ? "Uploading…" : "Selected"}
        </p>
        <p className="mt-4 break-all text-[28px] font-semibold leading-[1.14] text-ink">
          {file.name}
        </p>
        <p className="mt-2 text-[17px] text-muted">{fileSize(file.size)}</p>
      </div>

      {state === "uploading" ? (
        <div className="pt-12" aria-live="polite">
          <div className="h-1 overflow-hidden rounded-full bg-[#e0e0e0]">
            <div
              className="h-full bg-primary transition-[width]"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-3 text-[14px] text-muted">Uploading… {progress}%</p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 pt-12">
          <button type="button" className="primary-button" onClick={onUpload}>
            Upload
          </button>
          <button type="button" className="text-action px-3" onClick={onReplace}>
            Replace file
          </button>
          <button type="button" className="text-action px-3" onClick={onRemove}>
            Remove
          </button>
        </div>
      )}
    </div>
  )
}
