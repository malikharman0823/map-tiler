import React, { useRef, useState } from "react"

export const ACCEPTED_FORMATS =
  ".mtmap,.gpkg,.geojson,.tif,.tiff,.mbtiles,.json,.jpg,.jpeg,.png,.kml,.kmz,.shp,.shx,.dbf,.prj,.cpg,.osm,.pbf,.osm.pbf"

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
      className={`relative group bg-white border-2 border-dashed transition-all rounded-lg p-10 flex flex-col items-center justify-center text-center cursor-pointer ${
        dragging ? "border-[#a0a0a0] bg-pearl" : "border-[#d0d0d0] hover:border-[#a0a0a0]"
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
      <div className="w-12 h-12 rounded-lg bg-[#f8f9fa] border border-hairline flex items-center justify-center text-muted mb-4 group-hover:text-ink group-hover:border-[#c0c0c0] transition-colors">
        <span className="material-symbols-outlined text-[24px]">cloud_upload</span>
      </div>
      <h3 className="text-sm font-medium text-ink mb-1">
        Drag and drop files here or click to browse
      </h3>
      <p className="text-xs text-muted max-w-sm mb-5">
        Supports Full MapProjects (.mtmap), GeoPackage, GeoJSON, GeoTIFF, MBTiles, MapLibre style JSON, and legacy raster/vector formats.
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={disabled}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-ink hover:bg-[#202020] text-xs font-medium text-white transition-colors"
        >
          <span className="material-symbols-outlined text-[15px]">folder_open</span>
          <span>Browse local files</span>
        </button>
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
