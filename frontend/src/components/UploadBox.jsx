import React, { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { UploadCloud, FileArchive } from "lucide-react"

export const ACCEPTED_FORMATS = ".png,.jpg,.jpeg,.pdf,.dxf,.dwg,.svf,.zip,image/png,image/jpeg,application/pdf,application/zip"

export default function UploadBox({ disabled, onSelect }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  function chooseFile() {
    inputRef.current?.click()
  }

  function selectFiles(files) {
    const [file] = files
    if (file) onSelect(file)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    if (!disabled) selectFiles(event.dataTransfer.files)
  }

  return (
    <div
      onClick={!disabled ? chooseFile : undefined}
      className={`relative group bg-[#ffffff] border-2 border-dashed transition-all duration-200 rounded-[18px] p-8 sm:p-12 flex flex-col items-center justify-center text-center cursor-pointer shadow-xs ${
        dragging
          ? "border-[#0066cc] bg-[#f5f5f7]"
          : "border-[#e0e0e0] hover:border-[#0066cc]/60 hover:bg-[#fafafc]"
      } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false)
      }}
      onDrop={handleDrop}
    >
      <div className="size-14 rounded-2xl bg-[#f5f5f7] border border-[#e0e0e0] flex items-center justify-center text-[#0066cc] mb-4 group-hover:scale-105 transition-transform">
        <UploadCloud className="size-7" />
      </div>

      <h3 className="text-base font-semibold text-[#1d1d1f] mb-1">
        Drop a dataset file here or click to browse
      </h3>
      <p className="text-xs text-[#7a7a7a] max-w-sm mb-6">
        Supports PNG, JPG, PDF, CAD (.dxf, .dwg), SVF (.svf), and Map Studio project archives (.zip).
      </p>

      <div className="flex flex-wrap items-center justify-center gap-2.5">
        <Button
          type="button"
          disabled={disabled}
          variant="pill"
          size="sm"
          className="bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-normal"
        >
          <FileArchive className="size-3.5 mr-1.5" />
          <span>Choose file</span>
        </Button>
      </div>

      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept={ACCEPTED_FORMATS}
        disabled={disabled}
        onChange={(event) => selectFiles(event.target.files)}
      />
    </div>
  )
}
