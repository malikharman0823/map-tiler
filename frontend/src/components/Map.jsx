import React, { useEffect, useRef, useState } from "react"
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl"
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"

import { API_URL, BASEMAP_ATTRIBUTION, BASEMAP_TILE_URL } from "../api"
import { featureSummary } from "./FeatureInfo"
import MapCoordinates from "./MapCoordinates"

const BASEMAP_LAYER_ID = "basemap"
const DATASET_SOURCE_ID = "dataset-raster-source"
const DATASET_LAYER_ID = "dataset-raster-layer"
const VECTOR_SOURCE_ID = "dataset-vector-source"
const VECTOR_FILL_LAYER_ID = "dataset-vector-fill"
const VECTOR_LINE_LAYER_ID = "dataset-vector-line"
const VECTOR_POINT_LAYER_ID = "dataset-vector-point"
const VECTOR_TILE_SOURCE_ID = "dataset-vector-tile-source"
const DATASET_LAYER_IDS = [
  DATASET_LAYER_ID,
  VECTOR_FILL_LAYER_ID,
  VECTOR_LINE_LAYER_ID,
  VECTOR_POINT_LAYER_ID,
]
const CONTROL_POINTS_SOURCE_ID = "dataset-control-points-source"
const CONTROL_POINTS_LAYER_ID = "dataset-control-points-layer"
const CONTROL_POINTS_LABEL_LAYER_ID = "dataset-control-points-label-layer"
const ICON_POINTS_SOURCE_ID = "dataset-icon-points"
const ICON_POINTS_LAYER_ID = "dataset-icon-points-layer"
const WEB_MERCATOR_LIMIT = 20037508.342789244
const EMPTY_VECTOR_TILE_LAYERS = []

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
  const values = [
    bounds.min_longitude ?? bounds.min_x,
    bounds.min_latitude ?? bounds.min_y,
    bounds.max_longitude ?? bounds.max_x,
    bounds.max_latitude ?? bounds.max_y,
  ].map(Number)
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

function controlPointLabel(index) {
  return `CP-${String(index + 1).padStart(2, "0")}`
}

function iconPointLabel(index) {
  return `IP-${String(index + 1).padStart(2, "0")}`
}

function setLayerVisibility(map, layerIds, visible) {
  layerIds.forEach((layerId) => {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none")
    }
  })
}

function coordinateValue(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(6) : "Unavailable"
}

function controlPointPopup(point, label) {
  const container = document.createElement("div")
  container.className = "dataset-map-popup"
  const heading = document.createElement("strong")
  heading.textContent = `Control Point ${label.replace("CP-", "")}`
  container.appendChild(heading)

  const rows = [
    ["ID", point.id],
    ["Latitude", coordinateValue(point.latitude)],
    ["Longitude", coordinateValue(point.longitude)],
    ["Image X", coordinateValue(point.image_x)],
    ["Image Y", coordinateValue(point.image_y)],
  ]
  rows.forEach(([name, value]) => {
    const row = document.createElement("div")
    const nameElement = document.createElement("span")
    const valueElement = document.createElement("span")
    nameElement.textContent = name
    valueElement.textContent = value
    row.append(nameElement, valueElement)
    container.appendChild(row)
  })
  return container
}

function datasetFeatureAt(map, event, additionalLayerIds = []) {
  const layers = [...new Set([...DATASET_LAYER_IDS, ...additionalLayerIds])]
    .filter((layerId) => map.getLayer(layerId))
  return layers.length ? map.queryRenderedFeatures(event.point, { layers })[0] : null
}

function iconPointPopup(point, label) {
  const container = document.createElement("div")
  container.className = "dataset-map-popup"
  const heading = document.createElement("strong")
  heading.textContent = `Icon Point ${label.replace("IP-", "")}`
  container.appendChild(heading)
  if (point.description) {
    const description = document.createElement("p")
    description.textContent = point.description
    container.appendChild(description)
  }
  ;[
    ["Latitude", coordinateValue(point.latitude)],
    ["Longitude", coordinateValue(point.longitude)],
  ].forEach(([name, value]) => {
    const row = document.createElement("div")
    const nameElement = document.createElement("span")
    const valueElement = document.createElement("span")
    nameElement.textContent = name
    valueElement.textContent = value
    row.append(nameElement, valueElement)
    container.appendChild(row)
  })
  return container
}

export default function Map({
  tileUrl,
  tilesReady,
  minZoom,
  maxZoom,
  bounds,
  crs,
  fitKey,
  opacity,
  vectorData,
  vectorReady,
  vectorTileUrl,
  vectorTileLayers = EMPTY_VECTOR_TILE_LAYERS,
  styleDocument,
  controlPoints = [],
  iconPoints = [],
  icons = [],
  selectedControlPointId,
  selectedIconPointId,
  onSelectControlPoint,
  onSelectIconPoint,
  showBasemap = true,
  showDataset = true,
  showControlPoints = true,
  showIconPoints = true,
  interactionMode = "normal",
  onPlaceCoordinate,
  onSelectFeature,
  layoutRevision,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const popupRef = useRef(null)
  const hoverPopupRef = useRef(null)

  const onSelectControlPointRef = useRef(onSelectControlPoint)
  const onSelectIconPointRef = useRef(onSelectIconPoint)
  const onPlaceCoordinateRef = useRef(onPlaceCoordinate)
  const onSelectFeatureRef = useRef(onSelectFeature)
  const interactionModeRef = useRef(interactionMode)
  const showDatasetRef = useRef(showDataset)
  const controlPointsRef = useRef(controlPoints)
  const iconPointsRef = useRef(iconPoints)
  const initialOpacityRef = useRef(opacity)
  const fittedDatasetRef = useRef(null)
  const vectorTileLayerIdsRef = useRef([])
  const importedStyleLayerIdsRef = useRef(
    Array.isArray(styleDocument?.layers)
      ? styleDocument.layers.map((layer) => layer?.id).filter(Boolean)
      : [],
  )
  const [mapReady, setMapReady] = useState(false)
  const [cursorCoordinate, setCursorCoordinate] = useState(null)
  const [hoveredFeature, setHoveredFeature] = useState(null)

  useEffect(() => {
    onSelectControlPointRef.current = onSelectControlPoint
  }, [onSelectControlPoint])

  useEffect(() => {
    onSelectIconPointRef.current = onSelectIconPoint
  }, [onSelectIconPoint])

  useEffect(() => {
    onPlaceCoordinateRef.current = onPlaceCoordinate
    onSelectFeatureRef.current = onSelectFeature
    interactionModeRef.current = interactionMode
    showDatasetRef.current = showDataset
  }, [interactionMode, onPlaceCoordinate, onSelectFeature, showDataset])

  useEffect(() => {
    controlPointsRef.current = controlPoints
  }, [controlPoints])

  useEffect(() => {
    iconPointsRef.current = iconPoints
  }, [iconPoints])

  useEffect(() => {
    if (!containerRef.current) return undefined

    const importedStyle = styleDocument?.version === 8
      && styleDocument.sources
      && Array.isArray(styleDocument.layers)
      ? JSON.parse(JSON.stringify(styleDocument))
      : null
    const map = new MapLibreMap({
      container: containerRef.current,
      style: importedStyle || {
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
        layers: [{ id: BASEMAP_LAYER_ID, type: "raster", source: "basemap" }],
      },
      zoom: 1.5,
      minZoom: 0,
      maxZoom: 22,
      attributionControl: true,
    })

    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right")
    map.on("mousemove", (event) => {
      const coordinate = { latitude: event.lngLat.lat, longitude: event.lngLat.lng }
      setCursorCoordinate(coordinate)
      if (interactionModeRef.current === "add-icon-point" || interactionModeRef.current === "add-control-point" || !showDatasetRef.current) {
        setHoveredFeature(null)
        map.getCanvas().style.cursor = (interactionModeRef.current === "add-icon-point" || interactionModeRef.current === "add-control-point") ? "crosshair" : ""
        return
      }
      const feature = datasetFeatureAt(map, event, [
        ...vectorTileLayerIdsRef.current,
        ...importedStyleLayerIdsRef.current,
      ])
      if (!feature) {
        setHoveredFeature(null)
        map.getCanvas().style.cursor = ""
        return
      }
      const summary = featureSummary(feature.properties)
      setHoveredFeature({
        summary,
        x: event.point.x,
        y: event.point.y,
      })
      map.getCanvas().style.cursor = "pointer"
    })
    map.on("mouseleave", () => {
      setCursorCoordinate(null)
      setHoveredFeature(null)
      map.getCanvas().style.cursor = ""
    })
    map.on("click", (event) => {
      const coordinate = { latitude: event.lngLat.lat, longitude: event.lngLat.lng }
      if (interactionModeRef.current === "add-icon-point" || interactionModeRef.current === "add-control-point") {
        onPlaceCoordinateRef.current?.(coordinate)
        return
      }
      if (!showDatasetRef.current) return
      const feature = datasetFeatureAt(map, event, [
        ...vectorTileLayerIdsRef.current,
        ...importedStyleLayerIdsRef.current,
      ])
      if (!feature) return
      onSelectFeatureRef.current?.({
        properties: feature.properties || {},
        geometry: feature.geometry,
        coordinate,
      })
    })
    map.on("styleimagemissing", (e) => {
      const id = e.id
      const img = new Image()
      img.crossOrigin = "Anonymous"
      img.onload = () => {
        if (!map.hasImage(id)) map.addImage(id, img)
      }
      img.onerror = () => {
        if (!map.hasImage(id)) {
          const redCircleSvg = `<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10" fill="#d92d20" stroke="#fff" stroke-width="2"/></svg>`
          const fallbackImg = new Image()
          fallbackImg.onload = () => {
            if (!map.hasImage(id)) map.addImage(id, fallbackImg)
          }
          fallbackImg.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(redCircleSvg)}`
        }
      }
      // Add a cache buster so we don't load the broken cached SVGs from earlier
      img.src = `${API_URL}/icons/${id}?t=${Date.now()}`
    })

    const defaultSvg = `<svg width="42" height="42" viewBox="0 0 42 42" xmlns="http://www.w3.org/2000/svg"><circle cx="21" cy="21" r="19.5" fill="none" stroke="#16a34a" stroke-width="3"/><line x1="21" y1="0" x2="21" y2="42" stroke="#16a34a" stroke-width="2"/><line x1="0" y1="21" x2="42" y2="21" stroke="#16a34a" stroke-width="2"/><circle cx="21" cy="21" r="21" fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="2"/></svg>`
    const selectedSvg = `<svg width="42" height="42" viewBox="0 0 42 42" xmlns="http://www.w3.org/2000/svg"><circle cx="21" cy="21" r="19.5" fill="none" stroke="#15803d" stroke-width="3"/><line x1="21" y1="0" x2="21" y2="42" stroke="#15803d" stroke-width="2"/><line x1="0" y1="21" x2="42" y2="21" stroke="#15803d" stroke-width="2"/><circle cx="21" cy="21" r="21" fill="none" stroke="rgba(22,163,74,0.18)" stroke-width="5"/></svg>`
    const loadImg = (id, svg) => {
      const img = new Image()
      img.onload = () => { if (!map.hasImage(id)) map.addImage(id, img) }
      img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
    }

    map.on("load", () => {
      loadImg("cp-crosshair-default", defaultSvg)
      loadImg("cp-crosshair-selected", selectedSvg)
      setMapReady(true)
    })
    mapRef.current = map

    return () => {
      popupRef.current?.remove()
      popupRef.current = null
      hoverPopupRef.current?.remove()
      hoverPopupRef.current = null

      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return

    if (!tilesReady) {
      if (map.getLayer(DATASET_LAYER_ID)) map.removeLayer(DATASET_LAYER_ID)
      if (map.getSource(DATASET_SOURCE_ID)) map.removeSource(DATASET_SOURCE_ID)
      return
    }

    const existingSource = map.getSource(DATASET_SOURCE_ID)
    if (existingSource?.setTiles) {
      existingSource.setTiles([tileUrl])
    } else if (!existingSource) {
      const sourceOptions = {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
        minzoom: Number.isInteger(minZoom) ? minZoom : 0,
        maxzoom: Number.isInteger(maxZoom) ? maxZoom : 22,
      }
      const targetBounds = usableBounds(bounds, crs)
      if (targetBounds) {
        sourceOptions.bounds = [targetBounds[0][0], targetBounds[0][1], targetBounds[1][0], targetBounds[1][1]]
      }
      map.addSource(DATASET_SOURCE_ID, sourceOptions)
    }
    if (!map.getLayer(DATASET_LAYER_ID)) {
      const firstPointLayer = [CONTROL_POINTS_LAYER_ID, ICON_POINTS_LAYER_ID]
        .find((layerId) => map.getLayer(layerId))
      map.addLayer({
        id: DATASET_LAYER_ID,
        type: "raster",
        source: DATASET_SOURCE_ID,
        paint: { "raster-opacity": initialOpacityRef.current },
        layout: { visibility: showDatasetRef.current ? "visible" : "none" },
      }, firstPointLayer)
    }
  }, [mapReady, maxZoom, minZoom, tileUrl, tilesReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !vectorReady || !vectorData) return

    const source = map.getSource(VECTOR_SOURCE_ID)
    if (source) {
      source.setData(vectorData)
      return
    }

    map.addSource(VECTOR_SOURCE_ID, { type: "geojson", data: vectorData })
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
  }, [mapReady, vectorData, vectorReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !map.isStyleLoaded()) return

    vectorTileLayerIdsRef.current.forEach((layerId) => {
      if (map.getLayer(layerId)) map.removeLayer(layerId)
    })
    vectorTileLayerIdsRef.current = []
    if (map.getSource(VECTOR_TILE_SOURCE_ID)) map.removeSource(VECTOR_TILE_SOURCE_ID)
    if (!vectorTileUrl || !vectorTileLayers.length) return

    map.addSource(VECTOR_TILE_SOURCE_ID, {
      type: "vector",
      tiles: [vectorTileUrl],
      minzoom: Number.isInteger(minZoom) ? minZoom : 0,
      maxzoom: Number.isInteger(maxZoom) ? maxZoom : 22,
    })
    vectorTileLayers.forEach((sourceLayer, index) => {
      const definitions = [
        {
          id: `dataset-vector-tile-${index}-fill`,
          type: "fill",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": "#1677ff", "fill-opacity": initialOpacityRef.current * 0.45 },
        },
        {
          id: `dataset-vector-tile-${index}-line`,
          type: "line",
          filter: ["==", ["geometry-type"], "LineString"],
          paint: { "line-color": "#0057b8", "line-width": 2, "line-opacity": initialOpacityRef.current },
        },
        {
          id: `dataset-vector-tile-${index}-point`,
          type: "circle",
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-color": "#0057b8", "circle-radius": 4, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1, "circle-opacity": initialOpacityRef.current },
        },
      ]
      definitions.forEach((definition) => {
        map.addLayer({
          ...definition,
          source: VECTOR_TILE_SOURCE_ID,
          "source-layer": sourceLayer,
          layout: { visibility: showDatasetRef.current ? "visible" : "none" },
        })
        vectorTileLayerIdsRef.current.push(definition.id)
      })
    })
  }, [mapReady, maxZoom, minZoom, vectorTileLayers, vectorTileUrl])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !map.isStyleLoaded()) return

    if (!map.getSource(CONTROL_POINTS_SOURCE_ID)) {
      map.addSource(CONTROL_POINTS_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      })
      map.addLayer({
        id: CONTROL_POINTS_LAYER_ID,
        type: "symbol",
        source: CONTROL_POINTS_SOURCE_ID,
        layout: {
          "icon-image": ["case", ["boolean", ["get", "selected"], false], "cp-crosshair-selected", "cp-crosshair-default"],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        }
      })
      map.addLayer({
        id: CONTROL_POINTS_LABEL_LAYER_ID,
        type: "symbol",
        source: CONTROL_POINTS_SOURCE_ID,
        layout: {
          "text-field": ["get", "number"],
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-size": 12,
          "text-offset": [1, -1],
          "text-anchor": "center",
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#1d1d1f",
          "text-halo-color": "#ffffff",
          "text-halo-width": 4,
        }
      })

      const onCpClick = (e) => {
        if (e.features.length > 0) {
          e.preventDefault()
          onSelectControlPointRef.current?.(e.features[0].properties.id)
        }
      }
      map.on("click", CONTROL_POINTS_LAYER_ID, onCpClick)
      map.on("click", CONTROL_POINTS_LABEL_LAYER_ID, onCpClick)

      const onCpEnter = (e) => {
        map.getCanvas().style.cursor = "pointer"
        if (e.features.length > 0) {
          const point = e.features[0].properties
          if (!hoverPopupRef.current) hoverPopupRef.current = new Popup({ closeButton: false, closeOnClick: false, offset: 14 })
          hoverPopupRef.current
            .setLngLat(e.lngLat)
            .setDOMContent(controlPointPopup(point, point.label))
            .addTo(map)
        }
      }
      const onCpLeave = () => {
        map.getCanvas().style.cursor = ""
        hoverPopupRef.current?.remove()
      }
      map.on("mouseenter", CONTROL_POINTS_LAYER_ID, onCpEnter)
      map.on("mouseleave", CONTROL_POINTS_LAYER_ID, onCpLeave)
      map.on("mouseenter", CONTROL_POINTS_LABEL_LAYER_ID, onCpEnter)
      map.on("mouseleave", CONTROL_POINTS_LABEL_LAYER_ID, onCpLeave)
    }

    const source = map.getSource(CONTROL_POINTS_SOURCE_ID)
    if (source) {
      source.setData({
        type: "FeatureCollection",
        features: controlPoints.map((point, index) => {
          const longitude = Number(point.longitude)
          const latitude = Number(point.latitude)
          if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null
          return {
            type: "Feature",
            geometry: { type: "Point", coordinates: [longitude, latitude] },
            properties: {
              ...point,
              number: String(index + 1),
              label: controlPointLabel(index),
              selected: point.id === selectedControlPointId
            }
          }
        }).filter(Boolean)
      })
    }

    setLayerVisibility(map, [CONTROL_POINTS_LAYER_ID, CONTROL_POINTS_LABEL_LAYER_ID], showControlPoints)
  }, [controlPoints, mapReady, selectedControlPointId, showControlPoints])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !map.isStyleLoaded()) return
    if (!map.getSource(ICON_POINTS_SOURCE_ID)) {
      map.addSource(ICON_POINTS_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      })
      map.addLayer({
        id: ICON_POINTS_LAYER_ID,
        type: "symbol",
        source: ICON_POINTS_SOURCE_ID,
        layout: {
          "icon-image": ["get", "icon"],
          "icon-size": ["case", ["==", ["get", "selected"], true], 1.2, 1],
          "icon-allow-overlap": true
        },
        filter: ["!=", ["get", "icon"], ""]
      })

      // We need a fallback red circle in case of missing icon and fallback not working
      map.addLayer({
        id: `${ICON_POINTS_LAYER_ID}-fallback`,
        type: "circle",
        source: ICON_POINTS_SOURCE_ID,
        paint: {
          "circle-color": "#d92d20",
          "circle-radius": ["case", ["==", ["get", "selected"], true], 10, 8],
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2
        },
        filter: ["==", ["get", "icon"], ""]
      }, ICON_POINTS_LAYER_ID)

      map.on("click", ICON_POINTS_LAYER_ID, (e) => {
        if (e.features.length > 0) {
          e.preventDefault()
          onSelectIconPointRef.current?.(e.features[0].properties.id)
        }
      })
      map.on("click", `${ICON_POINTS_LAYER_ID}-fallback`, (e) => {
        if (e.features.length > 0) {
          e.preventDefault()
          onSelectIconPointRef.current?.(e.features[0].properties.id)
        }
      })

      const mouseEnter = (e) => {
        map.getCanvas().style.cursor = "pointer"
        if (e.features.length > 0) {
          const point = e.features[0].properties
          if (!hoverPopupRef.current) hoverPopupRef.current = new Popup({ closeButton: false, closeOnClick: false, offset: 14 })
          hoverPopupRef.current
            .setLngLat(e.lngLat)
            .setDOMContent(iconPointPopup(point, point.label))
            .addTo(map)
        }
      }
      const mouseLeave = () => {
        map.getCanvas().style.cursor = ""
        hoverPopupRef.current?.remove()
      }
      map.on("mouseenter", ICON_POINTS_LAYER_ID, mouseEnter)
      map.on("mouseleave", ICON_POINTS_LAYER_ID, mouseLeave)
      map.on("mouseenter", `${ICON_POINTS_LAYER_ID}-fallback`, mouseEnter)
      map.on("mouseleave", `${ICON_POINTS_LAYER_ID}-fallback`, mouseLeave)
    }

    const source = map.getSource(ICON_POINTS_SOURCE_ID)
    if (source) {
      source.setData({
        type: "FeatureCollection",
        features: iconPoints.map((point, index) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [Number(point.longitude), Number(point.latitude)]
          },
          properties: {
            ...point,
            label: iconPointLabel(index),
            icon: point.icon_key || "",
            selected: point.id === selectedIconPointId
          }
        }))
      })
    }

    setLayerVisibility(map, [ICON_POINTS_LAYER_ID, `${ICON_POINTS_LAYER_ID}-fallback`], showIconPoints)
  }, [mapReady, selectedIconPointId, showIconPoints, iconPoints])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    setLayerVisibility(map, [BASEMAP_LAYER_ID], showBasemap)
    setLayerVisibility(map, [
      ...DATASET_LAYER_IDS,
      ...vectorTileLayerIdsRef.current,
      ...importedStyleLayerIdsRef.current,
    ], showDataset)
    setLayerVisibility(map, [CONTROL_POINTS_LAYER_ID, CONTROL_POINTS_LABEL_LAYER_ID], showControlPoints)
    setLayerVisibility(map, ["dataset-icon-points-layer", "dataset-icon-points-layer-fallback"], showIconPoints)
  }, [mapReady, showBasemap, showControlPoints, showDataset, showIconPoints])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    if (map.getLayer(DATASET_LAYER_ID)) {
      map.setPaintProperty(DATASET_LAYER_ID, "raster-opacity", opacity)
    }
    if (map.getLayer(VECTOR_FILL_LAYER_ID)) {
      map.setPaintProperty(VECTOR_FILL_LAYER_ID, "fill-opacity", opacity * 0.45)
    }
    if (map.getLayer(VECTOR_LINE_LAYER_ID)) {
      map.setPaintProperty(VECTOR_LINE_LAYER_ID, "line-opacity", opacity)
    }
    if (map.getLayer(VECTOR_POINT_LAYER_ID)) {
      map.setPaintProperty(VECTOR_POINT_LAYER_ID, "circle-opacity", opacity)
    }
    vectorTileLayerIdsRef.current.forEach((layerId) => {
      if (!map.getLayer(layerId)) return
      if (layerId.endsWith("-fill")) map.setPaintProperty(layerId, "fill-opacity", opacity * 0.45)
      if (layerId.endsWith("-line")) map.setPaintProperty(layerId, "line-opacity", opacity)
      if (layerId.endsWith("-point")) map.setPaintProperty(layerId, "circle-opacity", opacity)
    })
  }, [mapReady, opacity])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return

    function fitToDataset() {
      const targetBounds = usableBounds(bounds, crs)
      if (targetBounds) map.fitBounds(targetBounds, { padding: 72, duration: 800 })
    }

    if (fitKey && fittedDatasetRef.current !== fitKey && usableBounds(bounds, crs)) {
      fittedDatasetRef.current = fitKey
      fitToDataset()
    }

    // Listen for manual fit requests
    const listener = () => fitToDataset()
    window.addEventListener("map-fit-dataset", listener)
    return () => window.removeEventListener("map-fit-dataset", listener)
  }, [bounds, crs, fitKey, mapReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return undefined
    const timer = window.setTimeout(() => map.resize(), 180)
    return () => window.clearTimeout(timer)
  }, [layoutRevision, mapReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    const index = controlPoints.findIndex((point) => point.id === selectedControlPointId)
    const point = index === -1 ? null : controlPoints[index]
    if (!point || !showControlPoints) {
      popupRef.current?.remove()
      return
    }

    const longitude = Number(point.longitude)
    const latitude = Number(point.latitude)
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return
    map.flyTo({ center: [longitude, latitude], zoom: Math.max(map.getZoom(), 12), speed: 1.1 })
    if (!popupRef.current) {
      popupRef.current = new Popup({ closeButton: true, closeOnClick: false })
    }
    popupRef.current
      .setLngLat([longitude, latitude])
      .setDOMContent(controlPointPopup(point, controlPointLabel(index)))
      .addTo(map)
  }, [controlPoints, mapReady, selectedControlPointId, showControlPoints])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    const index = iconPoints.findIndex((point) => point.id === selectedIconPointId)
    const point = index === -1 ? null : iconPoints[index]
    if (!point || !showIconPoints) {
      if (selectedIconPointId) popupRef.current?.remove()
      return
    }
    const longitude = Number(point.longitude)
    const latitude = Number(point.latitude)
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return
    map.flyTo({ center: [longitude, latitude], zoom: Math.max(map.getZoom(), 12), speed: 1.1 })
    if (!popupRef.current) {
      popupRef.current = new Popup({ closeButton: true, closeOnClick: false })
    }
    popupRef.current
      .setLngLat([longitude, latitude])
      .setDOMContent(iconPointPopup(point, iconPointLabel(index)))
      .addTo(map)
  }, [mapReady, selectedIconPointId, showIconPoints, iconPoints])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Dataset map" />
      {hoveredFeature?.summary && (
        <div className="pointer-events-none absolute z-10 max-w-52 rounded-lg border border-hairline bg-white px-3 py-2 text-[12px] shadow-sm" style={{ left: hoveredFeature.x + 14, top: hoveredFeature.y + 14 }}>
          <p className="font-semibold text-ink">{hoveredFeature.summary.label}</p>
          <p className="mt-0.5 break-words text-muted">{hoveredFeature.summary.value}</p>
        </div>
      )}
      <MapCoordinates coordinate={cursorCoordinate} />
    </div>
  )
}
