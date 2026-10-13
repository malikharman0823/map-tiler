import React, { useEffect, useRef, useState } from "react"
import { Input } from "@/components/ui/input"
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl"
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"

import { BASEMAP_ATTRIBUTION, BASEMAP_TILE_URL } from "../api"
import MapCoordinates from "./MapCoordinates"

const OVERLAY_SOURCE_ID = "georeference-preview-source"
const OVERLAY_LAYER_ID = "georeference-preview-layer"

setWorkerUrl(mapLibreWorkerUrl)


export default function ReferenceMap({
  points,
  selectedId,
  onSelect,
  onMapClick,
  onMoveEnd,
  overlay,
  readOnly = false,
  placementMode = false,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  const mapClickRef = useRef(onMapClick)
  const selectRef = useRef(onSelect)
  const moveEndRef = useRef(onMoveEnd)
  const readOnlyRef = useRef(readOnly)
  const placementModeRef = useRef(placementMode)
  const [searchValue, setSearchValue] = useState("")
  const [searchError, setSearchError] = useState(null)
  const [cursorCoordinate, setCursorCoordinate] = useState(null)

  mapClickRef.current = onMapClick
  selectRef.current = onSelect
  moveEndRef.current = onMoveEnd
  readOnlyRef.current = readOnly
  placementModeRef.current = placementMode

  useEffect(() => {
    if (!containerRef.current) return undefined
    const map = new MapLibreMap({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: "raster",
            tiles: [BASEMAP_TILE_URL],
            tileSize: 256,
            attribution: BASEMAP_ATTRIBUTION,
            maxzoom: 19,
          },
        },
        layers: [{ id: "basemap", type: "raster", source: "basemap" }],
      },
      center: [0, 20],
      zoom: 1.5,
      minZoom: 0,
      maxZoom: 22,
    })
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-left")
    map.on("click", (event) => {
      if (!readOnlyRef.current && placementModeRef.current) {
        const location = event.lngLat.wrap()
        const lat = Math.min(Math.max(location.lat, -90), 90)
        mapClickRef.current({ lng: location.lng, lat })
      }
    })
    map.on("mousemove", (event) => {
      setCursorCoordinate({ latitude: event.lngLat.lat, longitude: event.lngLat.lng })
    })
    map.on("mouseleave", () => setCursorCoordinate(null))
    mapRef.current = map
    return () => {
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (map) map.getCanvas().style.cursor = !readOnly && placementMode ? "crosshair" : ""
  }, [placementMode, readOnly])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined
    
    const renderGeoJSON = () => {
      const geojson = {
        type: "FeatureCollection",
        features: points.map((point, index) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
          properties: { id: point.id, number: String(index + 1), selected: selectedId === point.id }
        }))
      }

      if (map.getSource("control-points")) {
        map.getSource("control-points").setData(geojson)
      } else {
        map.addSource("control-points", { type: "geojson", data: geojson })
        map.addLayer({
          id: "control-points-circle",
          type: "circle",
          source: "control-points",
          paint: {
            "circle-radius": ["case", ["boolean", ["get", "selected"], false], 12, 10],
            "circle-color": ["case", ["boolean", ["get", "selected"], false], "#0052a3", "#0066cc"],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#ffffff",
          }
        })
        map.addLayer({
          id: "control-points-label",
          type: "symbol",
          source: "control-points",
          layout: {
            "text-field": ["get", "number"],
            "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
            "text-size": 11,
            "text-anchor": "center",
            "text-allow-overlap": true,
            "text-ignore-placement": true,
          },
          paint: {
            "text-color": "#ffffff",
          }
        })
      }
    }
    
    if (map.isStyleLoaded()) renderGeoJSON()
    else map.once("load", renderGeoJSON)

    return () => map.off("load", renderGeoJSON)
  }, [points, readOnly, selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readOnly) return undefined

    let isDragging = false
    let draggedId = null

    const onMouseDown = (e) => {
      if (e.defaultPrevented || isDragging) return
      const features = map.queryRenderedFeatures(e.point, { layers: ["control-points-circle", "control-points-label"] })
      if (!features.length) return
      e.preventDefault()
      isDragging = true
      draggedId = features[0].properties.id
      selectRef.current(draggedId)
      map.getCanvas().style.cursor = "grabbing"
      map.dragPan.disable()
    }

    const onMouseMove = (e) => {
      if (!isDragging || !draggedId) return
      const source = map.getSource("control-points")
      if (source) {
        // Update visually instantly during drag
        const currentData = {
          type: "FeatureCollection",
          features: points.map((p, i) => {
            if (p.id === draggedId) {
              return { type: "Feature", geometry: { type: "Point", coordinates: [e.lngLat.lng, e.lngLat.lat] }, properties: { id: p.id, number: String(i + 1), selected: true } }
            }
            return { type: "Feature", geometry: { type: "Point", coordinates: [p.longitude, p.latitude] }, properties: { id: p.id, number: String(i + 1), selected: selectedId === p.id } }
          })
        }
        source.setData(currentData)
      }
    }

    const onMouseUp = (e) => {
      if (!isDragging || !draggedId) return
      isDragging = false
      map.getCanvas().style.cursor = ""
      map.dragPan.enable()
      const location = e.lngLat.wrap()
      const lat = Math.min(Math.max(location.lat, -90), 90)
      moveEndRef.current(draggedId, { longitude: location.lng, latitude: lat })
      draggedId = null
    }

    map.on("mousedown", onMouseDown)
    map.on("mousemove", onMouseMove)
    map.on("mouseup", onMouseUp)

    return () => {
      map.off("mousedown", onMouseDown)
      map.off("mousemove", onMouseMove)
      map.off("mouseup", onMouseUp)
    }
  }, [points, readOnly, selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined
    const syncOverlay = () => {
      const source = map.getSource(OVERLAY_SOURCE_ID)
      if (!overlay?.visible || !overlay.coordinates || !overlay.imageUrl) {
        if (map.getLayer(OVERLAY_LAYER_ID)) map.removeLayer(OVERLAY_LAYER_ID)
        if (source) map.removeSource(OVERLAY_SOURCE_ID)
        return
      }
      if (source) {
        source.updateImage({
          url: overlay.imageUrl,
          coordinates: overlay.coordinates,
        })
      } else {
        map.addSource(OVERLAY_SOURCE_ID, {
          type: "image",
          url: overlay.imageUrl,
          coordinates: overlay.coordinates,
        })
        map.addLayer({
          id: OVERLAY_LAYER_ID,
          type: "raster",
          source: OVERLAY_SOURCE_ID,
          paint: { "raster-opacity": overlay.opacity },
        })
      }
      if (map.getLayer(OVERLAY_LAYER_ID)) {
        map.setPaintProperty(OVERLAY_LAYER_ID, "raster-opacity", overlay.opacity)
      }
    }
    if (map.isStyleLoaded()) syncOverlay()
    else map.once("load", syncOverlay)
    return () => map.off("load", syncOverlay)
  }, [overlay])

  function submitSearch(event) {
    event.preventDefault()
    const values = searchValue.split(",").map((value) => Number(value.trim()))
    if (values.length !== 2 || !values.every(Number.isFinite) || Math.abs(values[0]) > 180 || Math.abs(values[1]) > 90) {
      setSearchError("Use longitude, latitude to navigate.")
      return
    }
    setSearchError(null)
    mapRef.current?.flyTo({ center: values, zoom: 15, essential: true })
  }

  return (
    <section className="relative flex min-h-[360px] min-w-0 flex-1 flex-col overflow-hidden rounded-utility border border-hairline bg-white">
      <header className="flex min-h-14 shrink-0 items-center justify-between border-b border-hairline px-4">
        <div>
          <h2 className="text-[13px] font-semibold tracking-[0.08em] text-ink">REFERENCE MAP</h2>
          <p className="mt-0.5 text-[12px] text-muted">{readOnly ? "Inspect saved geographic references" : "Click a geographic location to pair it"}</p>
        </div>
        <form className="relative" onSubmit={submitSearch}>
          <Input
            className="w-48 text-[12px] rounded-full px-4 phone:w-56"
            value={searchValue}
            placeholder="Go to longitude, latitude"
            aria-label="Navigate to map coordinates"
            onChange={(event) => setSearchValue(event.target.value)}
          />
        </form>
      </header>
      <div ref={containerRef} className="min-h-0 flex-1" aria-label="Interactive geographic reference map" />
      <MapCoordinates coordinate={cursorCoordinate} />
      {searchError && <p className="absolute right-4 top-[60px] rounded-full bg-white px-3 py-1 text-[12px] text-muted shadow-sm">{searchError}</p>}
    </section>
  )
}
