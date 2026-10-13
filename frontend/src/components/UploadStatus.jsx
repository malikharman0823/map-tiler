import React from "react"
import { fileSize } from "./DatasetCard"
import { Button } from "@/components/ui/button"
import {
  Attachment,
  AttachmentMedia,
  AttachmentContent,
  AttachmentTitle,
  AttachmentDescription,
  AttachmentAction,
} from "@/components/ui/attachment"
import {
  CheckCircle2,
  AlertCircle,
  FileArchive,
  ArrowRight,
  Upload,
  RefreshCw,
  X,
  Loader2,
} from "lucide-react"

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
  onOpen,
}) {
  if (state === "success") {
    return (
      <div className="relative bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-8 sm:p-12 flex flex-col items-center justify-center text-center shadow-xs">
        <div className="size-14 rounded-2xl bg-[#34c759]/10 border border-[#34c759]/20 flex items-center justify-center text-[#34c759] mb-4">
          <CheckCircle2 className="size-7" />
        </div>
        <h3 className="text-lg font-semibold text-[#1d1d1f] mb-1">Upload complete</h3>
        <p className="text-xs text-[#7a7a7a] max-w-sm mb-6 font-mono truncate">
          {result.filename}
        </p>
        <Button
          type="button"
          variant="pill"
          size="default"
          onClick={onOpen}
          className="bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-normal"
        >
          <span>Continue</span>
          <ArrowRight className="size-3.5 ml-1.5" />
        </Button>
      </div>
    )
  }

  if (state === "error") {
    return (
      <div className="relative bg-[#ffffff] border border-[#ff3b30]/30 rounded-[18px] p-8 sm:p-12 flex flex-col items-center justify-center text-center shadow-xs">
        <div className="size-14 rounded-2xl bg-[#ff3b30]/10 border border-[#ff3b30]/20 flex items-center justify-center text-[#ff3b30] mb-4">
          <AlertCircle className="size-7" />
        </div>
        <h3 className="text-lg font-semibold text-[#1d1d1f] mb-1">Upload failed</h3>
        <p className="text-xs text-[#ff3b30] mt-1 max-w-sm font-semibold">{error?.message}</p>
        {error?.details && (
          <p className="text-xs text-[#7a7a7a] mt-1 max-w-sm mb-6">{error.details}</p>
        )}
        <div className="flex gap-2.5 mt-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRetry}
            className="rounded-full border-[#e0e0e0] text-xs"
          >
            <RefreshCw className="size-3.5 mr-1.5" />
            <span>Try again</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="rounded-full text-[#ff3b30] hover:bg-[#ff3b30]/10 text-xs"
          >
            Cancel
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-6 sm:p-8 flex flex-col justify-between min-h-[320px] shadow-xs">
      <div>
        <div className="flex items-center justify-between mb-4">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-mono border border-[#e0e0e0] bg-[#fafafc] text-[#1d1d1f]">
            {state === "uploading" ? "UPLOADING CHUNKS" : "READY TO INGEST"}
          </span>
          <span className="text-xs text-[#7a7a7a] font-mono">{fileSize(file.size)}</span>
        </div>

        {/* Shadcn Attachment Component */}
        <div className="mt-3">
          <Attachment
            state={state === "uploading" ? "uploading" : "done"}
            size="default"
            className="w-full border border-[#e0e0e0] bg-[#fafafc] rounded-2xl p-3 flex items-center gap-3"
          >
            <AttachmentMedia className="size-11 rounded-xl bg-[#ffffff] border border-[#e0e0e0] text-[#0066cc]">
              {state === "uploading" ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <FileArchive className="size-5" />
              )}
            </AttachmentMedia>
            <AttachmentContent className="min-w-0 flex-1">
              <AttachmentTitle className="text-xs font-semibold text-[#1d1d1f] truncate">
                {file.name}
              </AttachmentTitle>
              <AttachmentDescription className="text-[11px] text-[#7a7a7a]">
                {fileSize(file.size)} • Ready for spatial ingestion
              </AttachmentDescription>
            </AttachmentContent>
            {state !== "uploading" && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onRemove}
                className="size-8 rounded-full text-[#7a7a7a] hover:text-[#ff3b30]"
                title="Remove file"
              >
                <X className="size-4" />
              </Button>
            )}
          </Attachment>
        </div>
      </div>

      {state === "uploading" ? (
        <div className="mt-8 space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#7a7a7a] flex items-center gap-1.5">
              <Loader2 className="size-3.5 animate-spin text-[#0066cc]" />
              Processing spatial payload…
            </span>
            <span className="text-[#1d1d1f] font-mono font-semibold">{progress}%</span>
          </div>
          <div className="h-2 bg-[#f5f5f7] rounded-full overflow-hidden border border-[#e0e0e0]">
            <div
              className="h-full bg-[#0066cc] transition-[width] duration-300 rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-[#e0e0e0] pt-6">
          <Button
            type="button"
            variant="pill"
            size="sm"
            onClick={onUpload}
            className="bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-normal"
          >
            <Upload className="size-3.5 mr-1.5" />
            <span>Start Upload</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onReplace}
            className="rounded-full border-[#e0e0e0] text-xs"
          >
            Replace file
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="rounded-full text-[#ff3b30] hover:bg-[#ff3b30]/10 text-xs ml-auto"
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  )
}
