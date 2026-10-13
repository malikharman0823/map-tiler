import React, { useEffect, useMemo, useRef, useState } from "react"
import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl"
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"

import {
  BASEMAP_ATTRIBUTION,
  BASEMAP_TILE_URL,
  datasetTileUrl,
} from "../api"
import MapCoordinates from "./MapCoordinates"


setWorkerUrl(mapLibreWorkerUrl)

const BASEMAP_LAYER = "workspace-basemap"

function resourceIds(datasetId) {
  const prefix = `workspace-${datasetId}`
  return {
    rasterSource: `${prefix}-raster-source`,
    rasterLayer: `${prefix}-raster-layer`,
    controlSource: `${prefix}-control-source`,
    controlCircle: `${prefix}-control-circle`,
    controlLabel: `${prefix}-control-label`,
    iconSource: `${prefix}-icon-source`,
    iconCircle: `${prefix}-icon-circle`,
    iconLabel: `${prefix}-icon-label`,
  }
}

function boundsArray(bounds) {
  if (!bounds) return null
  const values = Array.isArray(bounds)
    ? bounds
    : [
        bounds.min_longitude ?? bounds.min_x,
        bounds.min_latitude ?? bounds.min_y,
        bounds.max_longitude ?? bounds.max_x,
        bounds.max_latitude ?? bounds.max_y,
      ]
  const parsed = values.map(Number)
  return parsed.length === 4 && parsed.every(Number.isFinite) ? parsed : null
}

function pointCollection(records, kind, selectedRecordId) {
  return {
    type: "FeatureCollection",
    features: records
      .filter((record) => record.kind === kind)
      .map((record) => ({
        type: "Feature",
        id: record.id,
        properties: {
          record_id: record.id,
          number: record.pair_number || "",
          label: record.description || record.name,
          selected: record.id === selectedRecordId,
        },
        geometry: {
          type: "Point",
          coordinates: [record.longitude, record.latitude],
        },
      })),
  }
}

function setVisibility(map, layerIds, visible) {
  layerIds.forEach((layerId) => {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none")
    }
  })
}

export default function WorkspaceMap({
  members = [],
  records = [],
  selectedRecordId,
  onSelectRecord,
  onCameraChange,
  savedCamera,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const membersRef = useRef(members)
  const selectRecordRef = useRef(onSelectRecord)
  const cameraChangeRef = useRef(onCameraChange)
  const fittedRef = useRef(false)
  const [ready, setReady] = useState(false)
  const [coordinate, setCoordinate] = useState(null)

  useEffect(() => {
    membersRef.current = members
  }, [members])

  useEffect(() => {
    selectRecordRef.current = onSelectRecord
  }, [onSelectRecord])

  useEffect(() => {
    cameraChangeRef.current = onCameraChange
  }, [onCameraChange])

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
        layers: [{ id: BASEMAP_LAYER, type: "raster", source: "basemap" }],
      },
      center: savedCamera ? [savedCamera.longitude, savedCamera.latitude] : [0, 20],
      zoom: savedCamera?.zoom ?? 1.5,
      bearing: savedCamera?.bearing ?? 0,
      pitch: savedCamera?.pitch ?? 0,
      maxZoom: 22,
    })
    map.addControl(new NavigationControl({ showCompass: true }), "bottom-right")
    map.on("load", () => setReady(true))
    map.on("mousemove", (event) => {
      setCoordinate({ latitude: event.lngLat.lat, longitude: event.lngLat.lng })
    })
    map.on("mouseleave", () => setCoordinate(null))
    map.on("click", (event) => {
      const pointLayers = membersRef.current.flatMap((member) => {
        const ids = resourceIds(member.dataset_id)
        return [ids.controlCircle, ids.controlLabel, ids.iconCircle, ids.iconLabel]
      }).filter((layerId) => map.getLayer(layerId))
      if (!pointLayers.length) return
      const feature = map.queryRenderedFeatures(event.point, { layers: pointLayers })[0]
      if (feature?.properties?.record_id) {
        selectRecordRef.current?.(feature.properties.record_id)
      }
    })
    let cameraTimer
    map.on("moveend", () => {
      clearTimeout(cameraTimer)
      cameraTimer = setTimeout(() => {
        const center = map.getCenter()
        cameraChangeRef.current?.({
          longitude: center.lng,
          latitude: center.lat,
          zoom: map.getZoom(),
          bearing: map.getBearing(),
          pitch: map.getPitch(),
        })
      }, 400)
    })
    mapRef.current = map
    return () => {
      clearTimeout(cameraTimer)
      mapRef.current = null
      map.remove()
    }
  }, [])

  const sortedMembers = useMemo(
    () => [...members].sort((a, b) => a.sort_order - b.sort_order),
    [members],
  )

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !map.isStyleLoaded()) return
    const activeSourceIds = new Set()
    const activeLayerIds = new Set()

    sortedMembers.forEach((member) => {
      const ids = resourceIds(member.dataset_id)
      const layer = member.dataset.map_layer
      if (!layer) return
      activeSourceIds.add(ids.rasterSource)
      const bgRemovalUpdate = member.dataset?.extracted_metadata?.background_removal?.updated_at || ""
      const baseTileUrl = datasetTileUrl(member.dataset_id, layer.tile_url_template)
      const tileUrl = bgRemovalUpdate
        ? `${baseTileUrl}${baseTileUrl.includes("?") ? "&" : "?"}v=${encodeURIComponent(bgRemovalUpdate)}`
        : baseTileUrl
      const existing = map.getSource(ids.rasterSource)
      if (existing?.setTiles) existing.setTiles([tileUrl])
      if (!existing) {
        const options = {
          type: "raster",
          tiles: [tileUrl],
          tileSize: layer.tile_size || 256,
          minzoom: layer.tile_min_zoom ?? 0,
          maxzoom: layer.tile_max_zoom ?? 22,
        }
        const bounds = boundsArray(layer.bounds)
        if (bounds) options.bounds = bounds
        map.addSource(ids.rasterSource, options)
      }
      if (!map.getLayer(ids.rasterLayer)) {
        map.addLayer({
          id: ids.rasterLayer,
          type: "raster",
          source: ids.rasterSource,
          paint: { "raster-opacity": member.raster_opacity },
        })
      }
      map.setPaintProperty(ids.rasterLayer, "raster-opacity", member.raster_opacity)
      setVisibility(map, [ids.rasterLayer], member.visible && member.raster_visible)
    })

    sortedMembers.forEach((member) => {
      const ids = resourceIds(member.dataset_id)
      const memberRecords = records.filter((record) => record.dataset_id === member.dataset_id)
      const controlData = pointCollection(memberRecords, "control_point", selectedRecordId)
      const iconData = pointCollection(memberRecords, "icon_point", selectedRecordId)
      const definitions = [
        {
          sourceId: ids.controlSource,
          data: controlData,
          layers: [
            {
              id: ids.controlCircle,
              type: "circle",
              paint: {
                "circle-radius": ["case", ["get", "selected"], 8, 6],
                "circle-color": "#0066cc",
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
              },
            },
            {
              id: ids.controlLabel,
              type: "symbol",
              layout: {
                "text-field": ["to-string", ["get", "number"]],
                "text-size": 11,
                "text-allow-overlap": true,
                "text-ignore-placement": true,
              },
              paint: { "text-color": "#ffffff" },
            },
          ],
          visible: member.visible && member.control_points_visible,
        },
        {
          sourceId: ids.iconSource,
          data: iconData,
          layers: [
            {
              id: ids.iconCircle,
              type: "circle",
              paint: {
                "circle-radius": ["case", ["get", "selected"], 9, 7],
                "circle-color": "#ff3b30",
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
              },
            },
            {
              id: ids.iconLabel,
              type: "symbol",
              layout: {
                "text-field": ["get", "label"],
                "text-size": 11,
                "text-offset": [0, 1.4],
                "text-anchor": "top",
                "text-allow-overlap": false,
              },
              paint: {
                "text-color": "#1d1d1f",
                "text-halo-color": "#ffffff",
                "text-halo-width": 2,
              },
            },
          ],
          visible: member.visible && member.icon_points_visible,
        },
      ]
      definitions.forEach((definition) => {
        activeSourceIds.add(definition.sourceId)
        definition.layers.forEach((layer) => activeLayerIds.add(layer.id))
        const source = map.getSource(definition.sourceId)
        if (source?.setData) source.setData(definition.data)
        if (!source) map.addSource(definition.sourceId, { type: "geojson", data: definition.data })
        definition.layers.forEach((layer) => {
          if (!map.getLayer(layer.id)) {
            map.addLayer({ ...layer, source: definition.sourceId })
          }
        })
        setVisibility(map, definition.layers.map((layer) => layer.id), definition.visible)
      })
    })

    const firstPointLayer = sortedMembers
      .flatMap((member) => {
        const ids = resourceIds(member.dataset_id)
        return [ids.controlCircle, ids.controlLabel, ids.iconCircle, ids.iconLabel]
      })
      .find((layerId) => map.getLayer(layerId))
    ;[...sortedMembers].reverse().forEach((member) => {
      const rasterLayer = resourceIds(member.dataset_id).rasterLayer
      if (map.getLayer(rasterLayer)) map.moveLayer(rasterLayer, firstPointLayer)
    })

    const style = map.getStyle()
    ;(style.layers || [])
      .filter((layer) => layer.id.startsWith("workspace-") && layer.id !== BASEMAP_LAYER)
      .forEach((layer) => {
        if (!activeLayerIds.has(layer.id) && map.getLayer(layer.id)) map.removeLayer(layer.id)
      })
    Object.keys(style.sources || {})
      .filter((sourceId) => sourceId.startsWith("workspace-"))
      .forEach((sourceId) => {
        if (!activeSourceIds.has(sourceId) && map.getSource(sourceId)) map.removeSource(sourceId)
      })

    if (!fittedRef.current) {
      const visibleBounds = sortedMembers
        .filter((member) => member.visible && member.dataset.map_layer)
        .map((member) => boundsArray(member.dataset.map_layer.bounds))
        .filter(Boolean)
      if (visibleBounds.length) {
        const union = visibleBounds.reduce((current, bounds) => [
          Math.min(current[0], bounds[0]),
          Math.min(current[1], bounds[1]),
          Math.max(current[2], bounds[2]),
          Math.max(current[3], bounds[3]),
        ])
        map.fitBounds([[union[0], union[1]], [union[2], union[3]]], { padding: 60, duration: 0 })
        fittedRef.current = true
      }
    }
  }, [ready, records, selectedRecordId, sortedMembers])

  useEffect(() => {
    const selected = records.find((record) => record.id === selectedRecordId)
    const map = mapRef.current
    if (!map || !selected) return
    if (selected.kind === "raster") {
      const bounds = boundsArray(selected.bounds)
      if (bounds) {
        map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 60, duration: 1000 })
      }
      return
    }
    if (selected.longitude != null && selected.latitude != null) {
      map.easeTo({ center: [selected.longitude, selected.latitude], zoom: Math.max(map.getZoom(), 16), duration: 1000 })
    }
  }, [records, selectedRecordId])

  return (
    <div className="workspace-map-canvas">
      <div ref={containerRef} className="workspace-map" />
      <MapCoordinates coordinate={coordinate} />
      {!sortedMembers.some((member) => member.dataset.map_layer) && (
        <div className="workspace-map-empty">
          <strong>No mapped raster is available</strong>
          <span>Open Database to inspect raw datasets or georeference a layer.</span>
        </div>
      )}
    </div>
  )
}
