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
import RasterTransformOverlay from "./RasterTransformOverlay"


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
  transformMember,
  onEndTransform,
  onTransformApplied,
  activeFloorLevel = 0,
  onActiveFloorChange,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const membersRef = useRef(members)
  const selectRecordRef = useRef(onSelectRecord)
  const cameraChangeRef = useRef(onCameraChange)
  const activeFloorLevelRef = useRef(activeFloorLevel)
  const onActiveFloorChangeRef = useRef(onActiveFloorChange)
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
    activeFloorLevelRef.current = activeFloorLevel
  }, [activeFloorLevel])

  useEffect(() => {
    onActiveFloorChangeRef.current = onActiveFloorChange
  }, [onActiveFloorChange])

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
    map.on("load", () => {
      setReady(true)
    })
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
    window.__maptiler_map = map
    window.__maptiler_setLayerOpacity = (datasetId, opacityVal) => {
      const activeMap = mapRef.current
      if (!activeMap || !activeMap.isStyleLoaded()) return
      const ids = resourceIds(datasetId)
      if (activeMap.getLayer(ids.rasterLayer)) {
        const safe = Number.isFinite(opacityVal) ? Math.max(0, Math.min(1, opacityVal)) : 1.0
        activeMap.setPaintProperty(ids.rasterLayer, "raster-opacity", safe)
      }
    }
    return () => {
      clearTimeout(cameraTimer)
      mapRef.current = null
      delete window.__maptiler_map
      delete window.__maptiler_setFloor
      delete window.__maptiler_setLayerOpacity
      map.remove()
    }
  }, [])

  const sortedMembers = useMemo(
    () => [...members].sort((a, b) => a.sort_order - b.sort_order),
    [members],
  )

  const buildingFloors = useMemo(() => {
    return sortedMembers
      .filter((m) => m.is_building_floor || m.building_name)
      .sort((a, b) => (b.floor_level ?? 0) - (a.floor_level ?? 0)) // Higher floors on top
  }, [sortedMembers])

  function handleElevatorClick(level) {
    activeFloorLevelRef.current = level
    if (onActiveFloorChange) onActiveFloorChange(level)
  }

  useEffect(() => {
    window.__maptiler_setFloor = handleElevatorClick
  })

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
      activeLayerIds.add(ids.rasterLayer)
      const bgRemovalUpdate = member.dataset?.metadata?.background_removal?.updated_at
        || member.dataset?.extracted_metadata?.background_removal?.updated_at
        || ""
      const transformUpdate = member.dataset?.metadata?.raster_transform?.updated_at
        || member.dataset?.extracted_metadata?.raster_transform?.updated_at
        || ""
      const updateVersion = [transformUpdate, bgRemovalUpdate].filter(Boolean).join("_")
      const baseTileUrl = datasetTileUrl(member.dataset_id, layer.tile_url_template)
      const tileUrl = updateVersion
        ? `${baseTileUrl}${baseTileUrl.includes("?") ? "&" : "?"}v=${encodeURIComponent(updateVersion)}`
        : baseTileUrl

      const bounds = boundsArray(layer.bounds)
      const boundsKey = bounds ? bounds.map((n) => Number(n).toFixed(6)).join(",") : ""
      const existing = map.getSource(ids.rasterSource)

      if (existing) {
        const urlChanged = existing._currentTileUrl && existing._currentTileUrl !== tileUrl
        const boundsChanged = existing._currentBounds && existing._currentBounds !== boundsKey
        if (urlChanged || boundsChanged) {
          try {
            if (map.getLayer(ids.rasterLayer)) {
              map.removeLayer(ids.rasterLayer)
            }
            map.removeSource(ids.rasterSource)
          } catch {
            // ignore
          }
        }
      }

      if (!map.getSource(ids.rasterSource)) {
        const options = {
          type: "raster",
          tiles: [tileUrl],
          tileSize: layer.tile_size || 256,
          minzoom: layer.tile_min_zoom ?? 0,
          maxzoom: layer.tile_max_zoom ?? 22,
        }
        if (bounds) options.bounds = bounds
        map.addSource(ids.rasterSource, options)
        const added = map.getSource(ids.rasterSource)
        if (added) {
          added._currentTileUrl = tileUrl
          added._currentBounds = boundsKey
        }
      }

      const safeOpacity = typeof member.raster_opacity === "number" && Number.isFinite(member.raster_opacity)
        ? Math.max(0, Math.min(1, member.raster_opacity))
        : 1.0

      if (!map.getLayer(ids.rasterLayer)) {
        const firstPointLayer = [ids.controlCircle, ids.controlLabel, ids.iconCircle, ids.iconLabel]
          .find((layerId) => map.getLayer(layerId))
        map.addLayer({
          id: ids.rasterLayer,
          type: "raster",
          source: ids.rasterSource,
          paint: { "raster-opacity": safeOpacity },
        }, firstPointLayer)
      }

      // Check if this member is a floor of a building:
      // If so, only show it if its floor level matches activeFloorLevel
      const isBuildingFloor = Boolean(member.is_building_floor || member.building_name)
      const isFloorActive = !isBuildingFloor || (member.floor_level === activeFloorLevel)
      const isLayerVisible = member.visible && member.raster_visible && isFloorActive

      map.setPaintProperty(ids.rasterLayer, "raster-opacity", safeOpacity)
      setVisibility(map, [ids.rasterLayer], isLayerVisible)
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
  }, [ready, records, selectedRecordId, sortedMembers, activeFloorLevel])

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

      {buildingFloors.length > 1 && (
        <div className="workspace-elevator-widget">
          <div className="workspace-elevator-header">Floors</div>
          <div className="workspace-elevator-buttons">
            {buildingFloors.map((floor) => {
              const level = floor.floor_level ?? 0
              const isActive = activeFloorLevel === level
              const badge = level === -1 ? "B1" : level === 0 ? "G" : `${level}`
              const name = floor.floor_label || (level === -1 ? "Basement 1" : level === 0 ? "Ground Floor" : `Floor ${level}`)
              return (
                <button
                  key={floor.dataset_id}
                  type="button"
                  className={`workspace-elevator-btn ${isActive ? "is-active" : ""}`}
                  title={`${name} (Click to switch floor)`}
                  onClick={() => handleElevatorClick(level)}
                >
                  <span className="workspace-elevator-badge">{badge}</span>
                  <span>{name}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {transformMember && mapRef.current && (
        <RasterTransformOverlay
          map={mapRef.current}
          datasetId={transformMember.dataset_id}
          datasetName={transformMember.name}
          onClose={onEndTransform}
          onApplied={onTransformApplied}
        />
      )}
      {!sortedMembers.some((member) => member.dataset.map_layer) && (
        <div className="workspace-map-empty">
          <strong>No mapped raster is available</strong>
          <span>Open Database to inspect raw datasets or georeference a layer.</span>
        </div>
      )}
    </div>
  )
}
