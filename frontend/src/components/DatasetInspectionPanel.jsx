import React, { useEffect, useMemo, useState } from "react"
import FeatureInfo from "./FeatureInfo"
import IconPointForm from "./IconPointForm"
import { Eye, X, Crosshair, MapPinPlus, ChevronDown, Maximize2 } from "lucide-react"

function ChevronIcon({ open }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={`h-4 w-4 fill-none stroke-current transition-transform${open ? " rotate-180" : ""}`} strokeWidth="1.8">
      <path d="m5 8 5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DisclosureSection({ title, children, defaultOpen = false, forceOpen = false, badge }) {
  const [open, setOpen] = useState(defaultOpen)

  useEffect(() => {
    if (forceOpen) setOpen(true)
  }, [forceOpen])

  return (
    <section className="border-b border-hairline last:border-b-0">
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2 text-left hover:bg-pearl transition-colors"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="text-[11px] font-semibold tracking-[0.08em] text-muted">{title}</span>
        <span className="flex items-center gap-2 text-[12px] text-muted">
          {badge && <span className="px-1.5 py-0.5 rounded bg-[#e0e2e5] text-[10px] text-ink">{badge}</span>}
          <ChevronIcon open={open} />
        </span>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </section>
  )
}

function controlPointLabel(index) {
  return `CP-${String(index + 1).padStart(2, "0")}`
}

function numberText(value, digits = 5) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : null
}

function byteText(value) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes < 0) return null
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB", "TB"]
  let scaled = bytes / 1024
  let index = 0
  while (scaled >= 1024 && index < units.length - 1) {
    scaled /= 1024
    index += 1
  }
  return `${scaled.toFixed(scaled >= 100 ? 0 : 1)} ${units[index]}`
}

function statusText(value) {
  if (!value) return null
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase())
}

function boundsText(bounds) {
  if (!bounds || typeof bounds !== "object") return null
  const values = [bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y].map((value) => numberText(value, 4))
  return values.every(Boolean) ? `${values[0]}, ${values[1]} to ${values[2]}, ${values[3]}` : null
}

function LegendSymbol({ item }) {
  const color = typeof item.color === "string" ? item.color : "#7a7a7a"
  const opacity = Number.isFinite(Number(item.opacity)) ? Number(item.opacity) : 1
  const type = item.type || "raster"
  if (type === "line") {
    return <span aria-hidden="true" className="h-[3px] w-7 rounded-full" style={{ backgroundColor: color, opacity }} />
  }
  return (
    <span
      aria-hidden="true"
      className={`h-4 w-4 shrink-0 ${type === "point" ? "rounded-full" : "rounded-sm"}`}
      style={{ backgroundColor: color, opacity }}
    />
  )
}

function MetadataRows({ rows }) {
  return (
    <dl className="grid gap-y-2 text-xs">
      {rows.map(([label, value]) => (
        value ? (
          <div key={label} className="flex justify-between items-start gap-3 py-1 border-b border-hairline last:border-0">
            <dt className="text-muted shrink-0">{label}</dt>
            <dd className="min-w-0 break-words text-right text-ink font-mono text-[11px]">{value}</dd>
          </div>
        ) : null
      ))}
    </dl>
  )
}

function LayerToggle({ checked, disabled, label, detail, onChange }) {
  return (
    <label className={`flex items-center justify-between p-2 rounded-md bg-white border border-[#e0e0e0] hover:border-[#0066cc]/40 transition-colors cursor-pointer group mb-1.5 ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}>
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        <input
          className="w-3.5 h-3.5 rounded border-[#c0c0c0] bg-white accent-[#0066cc] text-[#0066cc] focus:ring-0 focus:ring-offset-0 cursor-pointer"
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <div className="flex flex-col min-w-0 flex-1">
           <span className="text-xs text-[#1d1d1f] group-hover:text-[#0066cc] transition-colors truncate">{label}</span>
           {detail && <span className="text-[10px] text-[#7a7a7a] truncate">{detail}</span>}
        </div>
      </div>
      <Eye className="size-3.5 text-[#7a7a7a]" />
    </label>
  )
}

export default function DatasetInspectionPanel({
  dataset,
  points,
  iconPoints,
  icons,
  selectedPointId,
  selectedIconPointId,
  selectedFeature,
  onSelectPoint,
  onSelectIconPoint,
  onCreateIconPoint,
  onUpdateIconPoint,
  onDeleteIconPoint,
  onDeleteControlPoint,
  iconPointDraft,
  placingIconPoint,
  placingControlPoint,
  onStartIconPoint,
  onCancelIconPoint,
  onStartControlPoint,
  onCancelControlPoint,
  panelOpen,
  onClose,
  layerVisibility,
  onLayerVisibilityChange,
  opacity,
  onOpacityChange,
  datasetLayerAvailable,
  datasetLayerName,
  georeferencedLayerAvailable,
  controlPointsError,
  iconPointsError,
}) {
  const [editingIconPoint, setEditingIconPoint] = useState(false)

  const metadata = dataset.metadata || {}
  const selectedIndex = points.findIndex((point) => point.id === selectedPointId)
  const selectedPoint = selectedIndex === -1 ? null : points[selectedIndex]
  const selectedIconPointIndex = iconPoints.findIndex((point) => point.id === selectedIconPointId)
  const selectedIconPoint = selectedIconPointIndex === -1 ? null : iconPoints[selectedIconPointIndex]
  const georeference = dataset.georeference
  const legend = metadata.legend && Array.isArray(metadata.legend.items) ? metadata.legend : null
  
  const metadataRows = useMemo(() => {
    const extension = dataset.filename?.split(".").at(-1)?.toUpperCase()
    const dimensions = Number.isFinite(Number(metadata.width)) && Number.isFinite(Number(metadata.height))
      ? `${metadata.width} × ${metadata.height}`
      : null
    const interpretation = Array.isArray(metadata.color_interpretation)
      ? metadata.color_interpretation.join(", ")
      : null
    return [
      ["Format", metadata.driver || extension || dataset.content_type],
      ["Size", byteText(dataset.file_size)],
      ["CRS", metadata.crs],
      ["Bounds", boundsText(metadata.bounds)],
      ["Dimensions", dimensions],
      ["Bands", Number.isFinite(Number(metadata.bands)) ? String(metadata.bands) : null],
      ["Georeference", statusText(dataset.georeference_status)],
      ["Processing", statusText(dataset.process_status)],
      ["Tiles", statusText(dataset.tile_status)],
    ]
  }, [dataset, metadata])

  useEffect(() => {
    setEditingIconPoint(false)
  }, [selectedIconPointId])

  if (!panelOpen) return null

  return (
    <aside className="w-80 h-full bg-white border-l border-hairline flex flex-col z-30 select-none shrink-0" aria-label="Dataset map information">
      {/* Sidebar Header */}
      <div className="p-3.5 border-b border-hairline flex items-start justify-between gap-2 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-sm font-semibold text-ink truncate" title={datasetLayerName || dataset.filename}>{datasetLayerName || dataset.filename}</h2>
          </div>
          <p className="text-xs font-mono text-muted truncate">{dataset.filename}</p>
        </div>
        <button className="size-6 rounded flex items-center justify-center text-[#7a7a7a] hover:text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors shrink-0" onClick={onClose} title="Close Panel">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <DisclosureSection title="LAYERS" defaultOpen>
          <div className="space-y-1">
            <LayerToggle checked={layerVisibility.basemap} label="World Map" detail="Reference base map" onChange={(visible) => onLayerVisibilityChange("basemap", visible)} />
            <LayerToggle checked={layerVisibility.dataset} disabled={!datasetLayerAvailable} label={datasetLayerName || "Dataset"} detail={datasetLayerAvailable ? "Geospatial data" : "Unavailable"} onChange={(visible) => onLayerVisibilityChange("dataset", visible)} />
            <LayerToggle checked={layerVisibility.controlPoints} label="Control Points" detail={`${points.length} references`} onChange={(visible) => onLayerVisibilityChange("controlPoints", visible)} />
            <LayerToggle checked={layerVisibility.iconPoints} label="Icon Points" detail={`${iconPoints.length} annotations`} onChange={(visible) => onLayerVisibilityChange("iconPoints", visible)} />
          </div>
          
          <div className="pt-4 border-t border-hairline mt-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="dataset-opacity" className="text-muted font-medium">Layer Opacity</label>
              <span className="font-mono text-ink text-[11px]">{Math.round(opacity * 100)}%</span>
            </div>
            <input
              id="dataset-opacity"
              className="w-full h-1.5 bg-[#d0d0d0] rounded-lg appearance-none cursor-pointer accent-[#606060]"
              type="range"
              min="0"
              max="100"
              value={Math.round(opacity * 100)}
              disabled={!datasetLayerAvailable}
              onChange={(event) => onOpacityChange(Number(event.target.value) / 100)}
            />
          </div>

          <div className="pt-3 border-t border-hairline mt-3">
             <button
              type="button"
              className="w-full inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded border border-hairline bg-white hover:bg-pearl text-ink text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!datasetLayerAvailable}
              onClick={() => {
                window.dispatchEvent(new CustomEvent("map-fit-dataset"))
              }}
            >
              <Maximize2 className="size-3.5" />
              <span>Fit to Screen</span>
            </button>
          </div>
        </DisclosureSection>

        <DisclosureSection title="METADATA" defaultOpen>
          <div className="rounded-md border border-hairline bg-white p-2 text-xs">
            <MetadataRows rows={metadataRows} />
          </div>
        </DisclosureSection>

        {selectedFeature && (
          <DisclosureSection title="FEATURE INSPECTOR" defaultOpen forceOpen>
            <FeatureInfo feature={selectedFeature} />
          </DisclosureSection>
        )}

        {georeference && (
          <DisclosureSection title="GEOREFERENCING" defaultOpen>
            <div className="rounded-md border border-hairline bg-white p-2 text-xs">
              <MetadataRows rows={[
                ["Status", statusText(georeference.status)],
                ["Transform", statusText(georeference.transformation)],
                ["Points", String(georeference.control_point_count)],
                ["Target", georeference.target_crs],
                ["Output", georeference.output_format],
              ]} />
            </div>
          </DisclosureSection>
        )}

        <DisclosureSection title="MAP LEGEND" defaultOpen>
           <div className="space-y-3">
            <div>
              {legend ? (
                <>
                  {legend.title && <p className="mb-2 text-[11px] text-muted font-medium">{legend.title}</p>}
                  <ul className="space-y-1.5">
                    {legend.items.map((item, index) => (
                      <li key={`${item.label || "legend"}-${index}`} className="flex items-center justify-between py-1 px-2 rounded bg-white border border-hairline text-xs text-ink">
                        <div className="flex items-center gap-2">
                           <LegendSymbol item={item} />
                           <span className="min-w-0 break-words">{item.label || `Value ${item.value ?? index}`}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-[11px] leading-[1.4] text-muted">Legend not specified by dataset.</p>
              )}
            </div>
          </div>
        </DisclosureSection>

        <DisclosureSection title="CONTROL POINTS" badge={points.length || null} forceOpen={Boolean(selectedPoint)}>
          {controlPointsError && <p className="mb-3 text-[11px] text-red-600">{controlPointsError}</p>}
          {points.length === 0 ? (
            <p className="text-[11px] text-muted">No stored control points.</p>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
              {points.map((point, index) => {
                const selected = point.id === selectedPointId
                return (
                  <button
                    key={point.id}
                    type="button"
                    className={`w-full flex items-center justify-between p-2 rounded-md border transition-colors text-left ${selected ? "bg-[#e0e2e5] border-[#c0c0c0]" : "bg-white border-hairline hover:border-[#c0c0c0]"}`}
                    onClick={() => onSelectPoint(point.id)}
                  >
                    <div className="flex items-center gap-2">
                       <span className={`w-2 h-2 rounded-full ${selected ? "bg-blue-400" : "bg-[#c0c0c0]"}`}></span>
                       <span className="text-[11px] font-mono text-ink">{controlPointLabel(index)}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
          {selectedPoint && (
            <div className="mt-3 pt-3 border-t border-hairline">
              <div className="text-[11px] font-semibold text-ink mb-2">{controlPointLabel(selectedIndex)} Details</div>
              <MetadataRows rows={[
                ["Lat", numberText(selectedPoint.latitude, 6)],
                ["Lng", numberText(selectedPoint.longitude, 6)],
                ["Img X", numberText(selectedPoint.image_x, 2)],
                ["Img Y", numberText(selectedPoint.image_y, 2)],
              ]} />
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button type="button" className="col-start-2 px-2 py-1 text-xs rounded border border-red-200 hover:bg-red-50 text-red-600 transition-colors" onClick={() => onDeleteControlPoint(selectedPoint.id)}>Delete</button>
              </div>
            </div>
          )}
          {datasetLayerAvailable && (
            <div className="mt-3 pt-3 border-t border-[#e0e0e0]">
              <button type="button" className={`w-full inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-full border border-dashed transition-colors text-xs font-medium ${placingControlPoint ? "bg-[#f5f5f7] border-[#0066cc] text-[#0066cc]" : "bg-transparent border-[#e0e0e0] hover:border-[#0066cc] text-[#7a7a7a] hover:text-[#0066cc]"}`} onClick={onStartControlPoint}>
                <Crosshair className="size-3.5" />
                <span>{placingControlPoint ? "Click map to reverse-calc..." : "Add Control Point (Map)"}</span>
              </button>
            </div>
          )}
        </DisclosureSection>

        <DisclosureSection title="ICON ANNOTATIONS" badge={iconPoints.length || null} forceOpen={Boolean(selectedIconPoint)}>
          {iconPointsError && <p className="mb-3 text-[11px] text-red-600">{iconPointsError}</p>}
          {iconPoints.length === 0 ? (
            <p className="text-[11px] text-muted mb-2">No annotations added.</p>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto pr-1 mb-3">
              {iconPoints.map((point, index) => {
                const selected = point.id === selectedIconPointId
                return (
                  <button key={point.id} type="button" className={`w-full flex flex-col p-2 rounded-md border transition-colors text-left ${selected ? "bg-[#e0e2e5] border-[#c0c0c0]" : "bg-white border-hairline hover:border-[#c0c0c0]"}`} onClick={() => onSelectIconPoint(point.id)}>
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${selected ? "bg-red-500" : "bg-[#c0c0c0]"}`}></span>
                      <span className="text-[11px] font-mono text-ink">IP-{String(index + 1).padStart(2, "0")}</span>
                    </div>
                    <span className="mt-1 block text-[10px] text-muted truncate">{point.description || `${numberText(point.latitude)}, ${numberText(point.longitude)}`}</span>
                  </button>
                )
              })}
            </div>
          )}
          
          {selectedIconPoint && (
            <div className="mt-2 pt-3 border-t border-hairline">
              <MetadataRows rows={[
                ["Icon", selectedIconPoint.icon_key],
                ["Desc", selectedIconPoint.description || "-"],
              ]} />
              
              {editingIconPoint ? (
                <div className="mt-3 pt-3 border-t border-hairline">
                  <IconPointForm
                    coordinate={selectedIconPoint}
                    initialDescription={selectedIconPoint.description}
                    initialIconKey={selectedIconPoint.icon_key}
                    icons={icons}
                    submitLabel="Save changes"
                    title="Edit Annotation"
                    onCancel={() => setEditingIconPoint(false)}
                    onSubmit={async (data) => {
                      await onUpdateIconPoint(selectedIconPoint, data)
                      setEditingIconPoint(false)
                    }}
                  />
                </div>
              ) : (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button type="button" className="px-2 py-1 text-xs rounded border border-hairline hover:bg-pearl text-ink transition-colors" onClick={() => setEditingIconPoint(true)}>Edit</button>
                  <button type="button" className="px-2 py-1 text-xs rounded border border-red-200 hover:bg-red-50 text-red-600 transition-colors" onClick={() => onDeleteIconPoint(selectedIconPoint.id)}>Delete</button>
                </div>
              )}
            </div>
          )}
          
          <div className="mt-3 pt-3 border-t border-[#e0e0e0]">
            {!iconPointDraft && (
              <button type="button" className={`w-full inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-full border border-dashed transition-colors text-xs font-medium ${placingIconPoint ? "bg-[#f5f5f7] border-[#0066cc] text-[#0066cc]" : "bg-transparent border-[#e0e0e0] hover:border-[#0066cc] text-[#7a7a7a] hover:text-[#0066cc]"}`} onClick={onStartIconPoint}>
                <MapPinPlus className="size-3.5" />
                <span>{placingIconPoint ? "Click map to place..." : "Add New Annotation"}</span>
              </button>
            )}
            {iconPointDraft && (
              <IconPointForm 
                coordinate={iconPointDraft} 
                icons={icons} 
                onCancel={onCancelIconPoint} 
                onSubmit={onCreateIconPoint} 
              />
            )}
          </div>
        </DisclosureSection>
      </div>
    </aside>
  )
}
