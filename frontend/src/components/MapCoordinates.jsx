import React from "react"

function coordinateText(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(6) : "—"
}

export default function MapCoordinates({ coordinate }) {
  return (
    <output className="map-coordinates" aria-live="polite">
      <span>Lat: {coordinateText(coordinate?.latitude)}</span>
      <span>Lon: {coordinateText(coordinate?.longitude)}</span>
    </output>
  )
}
