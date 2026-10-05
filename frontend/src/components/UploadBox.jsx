import React, { useRef, useState } from "react"

export const ACCEPTED_FORMATS =
  ".jpg,.jpeg,.png,.tif,.tiff,.kml,.kmz,.shp,.shx,.dbf,.prj,.cpg,.osm,.pbf,.osm.pbf"

function UploadIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 48 48"
      className="h-16 w-16 fill-none stroke-[#7a7a7a]"
      strokeWidth="1.7"
    >
      <path d="M13 4h15l8 8v29a3 3 0 0 1-3 3H13a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z" strokeLinejoin="round" />
      <path d="M28 4v9h8M24 34V20m0 0-6 6m6-6 6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

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
      className={`flex min-h-[360px] flex-col items-center justify-center rounded-utility border bg-white px-6 py-12 text-center transition-colors ${
        dragging ? "border-primary" : "border-hairline"
      }`}
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
      <UploadIcon />
      <h2 className="mt-6 text-[28px] font-semibold leading-[1.14] text-ink">
        Choose a file
      </h2>
      <p className="mt-1 text-[17px] text-muted">or drop it here</p>
      <button
        type="button"
        className="primary-button mt-8 min-w-44"
        onClick={chooseFile}
        disabled={disabled}
      >
        Choose file
      </button>
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
