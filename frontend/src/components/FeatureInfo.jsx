import React, { useMemo } from "react"

function titleCase(value) {
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return null
  if (typeof value === "object") {
    const serialized = JSON.stringify(value)
    return serialized.length > 280 ? `${serialized.slice(0, 277)}…` : serialized
  }
  return String(value)
}

function firstCoordinate(geometry) {
  if (!geometry?.coordinates) return null
  let coordinates = geometry.coordinates
  while (Array.isArray(coordinates) && Array.isArray(coordinates[0])) {
    coordinates = coordinates[0]
  }
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null
  const [longitude, latitude] = coordinates.map(Number)
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    ? { latitude, longitude }
    : null
}

export function featureSummary(properties = {}) {
  const entry = Object.entries(properties).find(([, value]) => displayValue(value))
  return entry
    ? { label: titleCase(entry[0]), value: displayValue(entry[1]) }
    : null
}

export default function FeatureInfo({ feature }) {
  const properties = feature?.properties || {}
  const representativeCoordinate = useMemo(
    () => feature?.coordinate || firstCoordinate(feature?.geometry),
    [feature],
  )
  const rows = Object.entries(properties)
    .map(([key, value]) => [titleCase(key), displayValue(value)])
    .filter(([, value]) => value)

  if (!feature) return null

  return (
    <section className="space-y-4" aria-label="Feature information">
      <div>
        <p className="text-[11px] font-semibold tracking-wider uppercase text-[#7a7a7a]">FEATURE INFORMATION</p>
      </div>
      <dl className="grid gap-y-2 text-xs">
        {feature.geometry?.type && (
          <div className="flex justify-between items-start gap-3 py-1 border-b border-[#f0f0f0] last:border-0">
            <dt className="text-[#7a7a7a] shrink-0">Geometry</dt>
            <dd className="min-w-0 break-words text-right text-[#1d1d1f] font-mono text-[11px]">{feature.geometry.type}</dd>
          </div>
        )}
        {representativeCoordinate && (
          <>
            <div className="flex justify-between items-start gap-3 py-1 border-b border-[#f0f0f0] last:border-0">
              <dt className="text-[#7a7a7a] shrink-0">Latitude</dt>
              <dd className="min-w-0 break-words text-right text-[#1d1d1f] font-mono text-[11px]">{representativeCoordinate.latitude.toFixed(6)}</dd>
            </div>
            <div className="flex justify-between items-start gap-3 py-1 border-b border-[#f0f0f0] last:border-0">
              <dt className="text-[#7a7a7a] shrink-0">Longitude</dt>
              <dd className="min-w-0 break-words text-right text-[#1d1d1f] font-mono text-[11px]">{representativeCoordinate.longitude.toFixed(6)}</dd>
            </div>
          </>
        )}
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between items-start gap-3 py-1 border-b border-[#f0f0f0] last:border-0">
            <dt className="text-[#7a7a7a] shrink-0">{label}</dt>
            <dd className="min-w-0 break-words text-right text-[#1d1d1f] font-mono text-[11px]">{value}</dd>
          </div>
        ))}
      </dl>
      {rows.length === 0 && !feature.geometry?.type && (
        <p className="text-[11px] text-[#7a7a7a] mt-2">This feature has no displayable attributes.</p>
      )}
    </section>
  )
}
