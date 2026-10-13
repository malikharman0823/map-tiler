import React, { useState } from "react"
import { displayName } from "./DatasetCard"
import { ChevronDown, ChevronUp } from "lucide-react"

export default function DatasetMetadataOverlay({ dataset }) {
  const [collapsed, setCollapsed] = useState(false)

  if (!dataset) return null

  const {
    display_type,
    is_spatial,
    is_georeferenced,
    metadata
  } = dataset

  const isGeoTiff = display_type === "raster" && is_georeferenced
  const isOrdinaryTiff = display_type === "raster" && !is_georeferenced

  const renderField = (label, value) => {
    if (value === undefined || value === null) return null
    return (
      <div className="flex justify-between py-0.5">
        <span className="text-[#7a7a7a] w-24 shrink-0">{label}</span>
        <span className="text-[#1d1d1f] font-mono text-right truncate pl-2" title={value}>{value}</span>
      </div>
    )
  }

  const formatNumber = (num) => {
    if (typeof num !== "number") return num
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 }).format(num)
  }

  return (
    <div className="absolute top-4 left-4 z-40 bg-[#ffffff]/95 backdrop-blur-md border border-[#e0e0e0] rounded-[18px] shadow-sm w-76 flex flex-col overflow-hidden transition-all duration-300">
      <div 
        className="flex items-center justify-between px-3.5 py-2.5 bg-[#fafafc] border-b border-[#e0e0e0] cursor-pointer select-none"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${is_georeferenced || is_spatial ? 'bg-[#34c759]' : 'bg-[#ff3b30]'}`} />
          <span className="text-xs font-semibold text-[#1d1d1f]">
            {isGeoTiff ? "GeoTIFF Metadata" : isOrdinaryTiff ? "TIFF Metadata" : "Dataset Metadata"}
          </span>
        </div>
        <button className="text-[#7a7a7a] hover:text-[#1d1d1f] size-6 flex items-center justify-center rounded">
          {collapsed ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
        </button>
      </div>

      {!collapsed && (
        <div className="p-3 text-xs flex flex-col gap-2 max-h-[60vh] overflow-y-auto">
          <div className="border-b border-hairline pb-2 mb-1">
            {renderField("File", displayName(dataset.filename))}
            {renderField("Format", metadata?.format?.toUpperCase() || display_type)}
            {renderField("Status", isGeoTiff ? "Georeferenced" : isOrdinaryTiff ? "Not georeferenced" : is_spatial ? "Spatial" : "Unknown")}
            {renderField("Size", dataset.file_size ? `${(dataset.file_size / (1024 * 1024)).toFixed(2)} MB` : null)}
          </div>

          {(isGeoTiff || metadata?.crs) && (
            <div className="border-b border-hairline pb-2 mb-1">
              {renderField("CRS", metadata?.crs || "EPSG:4326")}
              {metadata?.bounds && (
                <div className="mt-1">
                  <span className="text-muted block mb-1">Bounds</span>
                  <div className="pl-2 border-l-2 border-blue-100">
                    {renderField("W", formatNumber(metadata.bounds.min_x || metadata.bounds.min_longitude))}
                    {renderField("E", formatNumber(metadata.bounds.max_x || metadata.bounds.max_longitude))}
                    {renderField("S", formatNumber(metadata.bounds.min_y || metadata.bounds.min_latitude))}
                    {renderField("N", formatNumber(metadata.bounds.max_y || metadata.bounds.max_latitude))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="pb-1">
            {metadata?.width && metadata?.height && (
              renderField("Dimensions", `${metadata.width} × ${metadata.height}`)
            )}
            {metadata?.bands && (
              renderField("Bands", metadata.bands)
            )}
            {metadata?.driver && (
              renderField("Driver", metadata.driver)
            )}
            {metadata?.feature_count !== undefined && (
              renderField("Features", formatNumber(metadata.feature_count))
            )}
            {dataset.tile_min_zoom !== null && dataset.tile_min_zoom !== undefined && (
              renderField("Zoom", `${dataset.tile_min_zoom} - ${dataset.tile_max_zoom}`)
            )}
          </div>
        </div>
      )}
    </div>
  )
}
