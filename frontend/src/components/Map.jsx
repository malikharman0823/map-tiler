import React, { useEffect, useRef } from "react"
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl"
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"

import { BASEMAP_ATTRIBUTION, BASEMAP_TILE_URL } from "../api"

const DATASET_SOURCE_ID = "dataset-raster-source"
const DATASET_LAYER_ID = "dataset-raster-layer"
const VECTOR_SOURCE_ID = "dataset-vector-source"
const VECTOR_FILL_LAYER_ID = "dataset-vector-fill"
const VECTOR_LINE_LAYER_ID = "dataset-vector-line"
const VECTOR_POINT_LAYER_ID = "dataset-vector-point"
const WEB_MERCATOR_LIMIT = 20037508.342789244

setWorkerUrl(mapLibreWorkerUrl)

function mercatorToLngLat(x, y) {
  const longitude = (x / WEB_MERCATOR_LIMIT) * 180
  const latitude =
    (Math.atan(Math.exp((y / WEB_MERCATOR_LIMIT) * Math.PI)) * 360) /
      Math.PI -
    90
  return [longitude, latitude]
}

function usableBounds(bounds, crs) {
  if (!bounds) return null
  const values = [bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y].map(Number)
  if (!values.every(Number.isFinite)) return null
  const [minX, minY, maxX, maxY] = values
  if (minX >= maxX || minY >= maxY) return null

  const normalizedCrs = String(crs || "").toUpperCase()
  if (normalizedCrs.includes("4326")) return [[minX, minY], [maxX, maxY]]
  if (normalizedCrs.includes("3857")) {
    return [mercatorToLngLat(minX, minY), mercatorToLngLat(maxX, maxY)]
  }
  return null
}

export default function Map({
  tileUrl,
  tilesReady,
  minZoom,
  maxZoom,
  bounds,
  crs,
  opacity,
  vectorData,
  vectorReady,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const initialOpacityRef = useRef(opacity)

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
          },
        },
        layers: [{ id: "basemap", type: "raster", source: "basemap" }],
      },
      zoom: 1.5,
      minZoom: 0,
      maxZoom: 22,
      attributionControl: true,
    })

    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right")
    map.on("load", () => {
      if (tilesReady) {
        map.addSource(DATASET_SOURCE_ID, {
          type: "raster",
          tiles: [tileUrl],
          tileSize: 256,
          minzoom: Number.isInteger(minZoom) ? minZoom : 0,
          maxzoom: Number.isInteger(maxZoom) ? maxZoom : 22,
        })
        map.addLayer({
          id: DATASET_LAYER_ID,
          type: "raster",
          source: DATASET_SOURCE_ID,
          paint: { "raster-opacity": initialOpacityRef.current },
        })
      }

      if (vectorReady) {
        map.addSource(VECTOR_SOURCE_ID, {
          type: "geojson",
          data: vectorData,
        })
        map.addLayer({
          id: VECTOR_FILL_LAYER_ID,
          type: "fill",
          source: VECTOR_SOURCE_ID,
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: {
            "fill-color": "#1677ff",
            "fill-opacity": initialOpacityRef.current * 0.45,
          },
        })
        map.addLayer({
          id: VECTOR_LINE_LAYER_ID,
          type: "line",
          source: VECTOR_SOURCE_ID,
          filter: ["==", ["geometry-type"], "LineString"],
          paint: {
            "line-color": "#0057b8",
            "line-width": 2,
            "line-opacity": initialOpacityRef.current,
          },
        })
        map.addLayer({
          id: VECTOR_POINT_LAYER_ID,
          type: "circle",
          source: VECTOR_SOURCE_ID,
          filter: ["==", ["geometry-type"], "Point"],
          paint: {
            "circle-color": "#0057b8",
            "circle-radius": 4,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1,
            "circle-opacity": initialOpacityRef.current,
          },
        })
      }

      const targetBounds = usableBounds(bounds, crs)
      if (targetBounds) map.fitBounds(targetBounds, { padding: 72, duration: 0 })
    })

    mapRef.current = map
    return () => {
      mapRef.current = null
      map.remove()
    }
  }, [bounds, crs, maxZoom, minZoom, tileUrl, tilesReady, vectorData, vectorReady])

  useEffect(() => {
    const map = mapRef.current
    if (map?.getLayer(DATASET_LAYER_ID)) {
      map.setPaintProperty(DATASET_LAYER_ID, "raster-opacity", opacity)
    }
    if (map?.getLayer(VECTOR_FILL_LAYER_ID)) {
      map.setPaintProperty(VECTOR_FILL_LAYER_ID, "fill-opacity", opacity * 0.45)
    }
    if (map?.getLayer(VECTOR_LINE_LAYER_ID)) {
      map.setPaintProperty(VECTOR_LINE_LAYER_ID, "line-opacity", opacity)
    }
    if (map?.getLayer(VECTOR_POINT_LAYER_ID)) {
      map.setPaintProperty(VECTOR_POINT_LAYER_ID, "circle-opacity", opacity)
    }
  }, [opacity])

  return <div ref={containerRef} className="h-full w-full" aria-label="Dataset map" />
}
