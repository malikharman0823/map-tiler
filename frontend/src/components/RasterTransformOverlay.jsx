import React, { useEffect, useRef, useState, useMemo } from "react"
import {
  Check,
  Compass,
  CornerDownLeft,
  CornerDownRight,
  Eye,
  Hand,
  Loader2,
  Lock,
  Maximize2,
  Move,
  Redo2,
  RotateCw,
  Sliders,
  Sparkles,
  Undo2,
  Unlock,
  X,
  AlertCircle,
} from "lucide-react"

import {
  applyRasterTransform,
  getRasterTransform,
  previewRasterTransform,
  readableApiError,
  redoRasterTransform,
  resetRasterTransform,
  undoRasterTransform,
} from "../api"

// MapLibre safety helpers
// MapLibre 6.x Style keeps sources in `tileManagers`. After map.remove() or a
// style teardown these can be missing, and getSource()/getLayer() then throw.
function isMapReady(map) {
  return Boolean(
    map
    && !map._removed
    && map.style
    && map.style.tileManagers
    && map.style._layers
  )
}

function safeGetSource(map, id) {
  if (!isMapReady(map)) return null
  try {
    return map.getSource(id) || null
  } catch {
    return null
  }
}

function safeGetLayer(map, id) {
  if (!isMapReady(map)) return null
  try {
    return map.getLayer(id) || null
  } catch {
    return null
  }
}

function safeRemoveLayer(map, id) {
  if (!map || map._removed) return
  try {
    if (map.style && map.style._layers && map.style._layers[id]) {
      map.removeLayer(id)
    }
  } catch {
    // ignore
  }
}

function safeRemoveSource(map, id) {
  if (!map || map._removed) return
  try {
    if (map.style && map.style.tileManagers && map.style.tileManagers[id]) {
      map.removeSource(id)
    }
  } catch {
    // ignore
  }
}

export default function RasterTransformOverlay({
  map,
  datasetId,
  datasetName,
  onClose,
  onApplied,
}) {
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState("free") // 'move' | 'resize' | 'rotate' | 'free'
  const [lockAspect, setLockAspect] = useState(false)

  // 4 corners: top_left, top_right, bottom_right, bottom_left
  const [corners, setCorners] = useState(null)
  const [originalCorners, setOriginalCorners] = useState(null)
  const [rotationAngle, setRotationAngle] = useState(0)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  // Dragging interaction state
  const dragRef = useRef({
    active: false,
    handleType: null, // 'tl' | 'tr' | 'br' | 'bl' | 'edge-top' | 'edge-right' | 'edge-bottom' | 'edge-left' | 'body' | 'rot'
    startPoint: null, // { x, y, lng, lat }
    startCorners: null,
    startAngle: 0,
    center: null,
  })

  // Load initial status
  useEffect(() => {
    if (!datasetId) return
    let active = true
    setLoading(true)
    setError(null)

    getRasterTransform(datasetId)
      .then((data) => {
        if (!active) return
        if (data.corners) {
          setCorners(data.corners)
        }
        if (data.original_corners) {
          setOriginalCorners(data.original_corners)
        }
        if (typeof data.rotation_angle === "number") {
          setRotationAngle(data.rotation_angle)
        }
        setLockAspect(Boolean(data.lock_aspect_ratio))
        setCanUndo(Boolean(data.can_undo))
        setCanRedo(Boolean(data.can_redo))
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setLoading(false)
        setError(readableApiError(err, "Failed to load raster transformation status."))
      })

    return () => {
      active = false
    }
  }, [datasetId])

  // Stable Map Source & Layer IDs
  const {
    SOURCE_ID,
    LINE_LAYER_ID,
    FILL_LAYER_ID,
    HANDLES_SOURCE_ID,
    HANDLES_LAYER_ID,
    ROT_LINE_SOURCE_ID,
    ROT_LINE_LAYER_ID,
  } = useMemo(() => ({
    SOURCE_ID: `raster-tf-${datasetId}-outline`,
    LINE_LAYER_ID: `raster-tf-${datasetId}-line`,
    FILL_LAYER_ID: `raster-tf-${datasetId}-fill`,
    HANDLES_SOURCE_ID: `raster-tf-${datasetId}-handles`,
    HANDLES_LAYER_ID: `raster-tf-${datasetId}-handles-layer`,
    ROT_LINE_SOURCE_ID: `raster-tf-${datasetId}-rot-line`,
    ROT_LINE_LAYER_ID: `raster-tf-${datasetId}-rot-line-layer`,
  }), [datasetId])

  // Compute centers and midpoints
  const geometryInfo = useMemo(() => {
    if (!corners) return null
    const { top_left: tl, top_right: tr, bottom_right: br, bottom_left: bl } = corners
    const centerLng = (tl.longitude + tr.longitude + br.longitude + bl.longitude) / 4
    const centerLat = (tl.latitude + tr.latitude + br.latitude + bl.latitude) / 4

    const topMid = { longitude: (tl.longitude + tr.longitude) / 2, latitude: (tl.latitude + tr.latitude) / 2 }
    const rightMid = { longitude: (tr.longitude + br.longitude) / 2, latitude: (tr.latitude + br.latitude) / 2 }
    const bottomMid = { longitude: (bl.longitude + br.longitude) / 2, latitude: (bl.latitude + br.latitude) / 2 }
    const leftMid = { longitude: (tl.longitude + bl.longitude) / 2, latitude: (tl.latitude + bl.latitude) / 2 }

    // Rotation handle sticking out from top center
    const dLng = tr.longitude - tl.longitude
    const dLat = tr.latitude - tl.latitude
    const norm = Math.hypot(dLng, dLat) || 1
    // Normal perpendicular vector pointing "outward" (upwards)
    const perpLng = -dLat / norm
    const perpLat = dLng / norm
    const offset = norm * 0.18 // offset distance
    const rotHandle = {
      longitude: topMid.longitude + perpLng * offset,
      latitude: topMid.latitude + perpLat * offset,
    }

    return {
      center: { longitude: centerLng, latitude: centerLat },
      topMid,
      rightMid,
      bottomMid,
      leftMid,
      rotHandle,
    }
  }, [corners])

  // Draw GeoJSON bounding box & handles on MapLibre map
  useEffect(() => {
    if (!isMapReady(map) || !corners || !geometryInfo) return

    const { top_left: tl, top_right: tr, bottom_right: br, bottom_left: bl } = corners
    const { center, topMid, rightMid, bottomMid, leftMid, rotHandle } = geometryInfo

    const polyGeoJson = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [[
              [tl.longitude, tl.latitude],
              [tr.longitude, tr.latitude],
              [br.longitude, br.latitude],
              [bl.longitude, bl.latitude],
              [tl.longitude, tl.latitude],
            ]],
          },
        },
      ],
    }

    const rotLineGeoJson = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: [
              [topMid.longitude, topMid.latitude],
              [rotHandle.longitude, rotHandle.latitude],
            ],
          },
        },
      ],
    }

    const handlesGeoJson = {
      type: "FeatureCollection",
      features: [
        // Corners
        { type: "Feature", properties: { kind: "corner", handle: "tl" }, geometry: { type: "Point", coordinates: [tl.longitude, tl.latitude] } },
        { type: "Feature", properties: { kind: "corner", handle: "tr" }, geometry: { type: "Point", coordinates: [tr.longitude, tr.latitude] } },
        { type: "Feature", properties: { kind: "corner", handle: "br" }, geometry: { type: "Point", coordinates: [br.longitude, br.latitude] } },
        { type: "Feature", properties: { kind: "corner", handle: "bl" }, geometry: { type: "Point", coordinates: [bl.longitude, bl.latitude] } },
        // Midpoints
        { type: "Feature", properties: { kind: "edge", handle: "edge-top" }, geometry: { type: "Point", coordinates: [topMid.longitude, topMid.latitude] } },
        { type: "Feature", properties: { kind: "edge", handle: "edge-right" }, geometry: { type: "Point", coordinates: [rightMid.longitude, rightMid.latitude] } },
        { type: "Feature", properties: { kind: "edge", handle: "edge-bottom" }, geometry: { type: "Point", coordinates: [bottomMid.longitude, bottomMid.latitude] } },
        { type: "Feature", properties: { kind: "edge", handle: "edge-left" }, geometry: { type: "Point", coordinates: [leftMid.longitude, leftMid.latitude] } },
        // Pivot
        { type: "Feature", properties: { kind: "pivot", handle: "pivot" }, geometry: { type: "Point", coordinates: [center.longitude, center.latitude] } },
        // Rotation
        { type: "Feature", properties: { kind: "rotation", handle: "rot" }, geometry: { type: "Point", coordinates: [rotHandle.longitude, rotHandle.latitude] } },
      ],
    }

    // 1. Polygon outline & fill
    const src = safeGetSource(map, SOURCE_ID)
    if (!src) {
      try {
        map.addSource(SOURCE_ID, { type: "geojson", data: polyGeoJson })
        map.addLayer({
          id: FILL_LAYER_ID,
          type: "fill",
          source: SOURCE_ID,
          paint: {
            "fill-color": "#0066cc",
            "fill-opacity": 0.08,
          },
        })
        map.addLayer({
          id: LINE_LAYER_ID,
          type: "line",
          source: SOURCE_ID,
          paint: {
            "line-color": "#0066cc",
            "line-width": 2.5,
            "line-dasharray": [2, 1.5],
          },
        })
      } catch {
        // layer/source may already exist
      }
    } else {
      try {
        src.setData(polyGeoJson)
      } catch {
        // ignore
      }
    }

    // 2. Rotation arm line
    const rotLineSrc = safeGetSource(map, ROT_LINE_SOURCE_ID)
    if (!rotLineSrc) {
      try {
        map.addSource(ROT_LINE_SOURCE_ID, { type: "geojson", data: rotLineGeoJson })
        map.addLayer({
          id: ROT_LINE_LAYER_ID,
          type: "line",
          source: ROT_LINE_SOURCE_ID,
          paint: {
            "line-color": "#ff9500",
            "line-width": 2,
          },
        })
      } catch {
        // layer/source may already exist
      }
    } else {
      try {
        rotLineSrc.setData(rotLineGeoJson)
      } catch {
        // ignore
      }
    }

    // 3. Handles circles
    const handlesSrc = safeGetSource(map, HANDLES_SOURCE_ID)
    if (!handlesSrc) {
      try {
        map.addSource(HANDLES_SOURCE_ID, { type: "geojson", data: handlesGeoJson })
        map.addLayer({
          id: HANDLES_LAYER_ID,
          type: "circle",
          source: HANDLES_SOURCE_ID,
          paint: {
            "circle-radius": [
              "match",
              ["get", "kind"],
              "corner", 7,
              "rotation", 7.5,
              "pivot", 5,
              5.5,
            ],
            "circle-color": [
              "match",
              ["get", "kind"],
              "rotation", "#ff9500",
              "pivot", "#ff3b30",
              "#ffffff",
            ],
            "circle-stroke-width": 2.5,
            "circle-stroke-color": [
              "match",
              ["get", "kind"],
              "rotation", "#ffffff",
              "pivot", "#ffffff",
              "#0066cc",
            ],
          },
        })
      } catch {
        // layer/source may already exist
      }
    } else {
      try {
        handlesSrc.setData(handlesGeoJson)
      } catch {
        // ignore
      }
    }
  }, [map, corners, geometryInfo, SOURCE_ID, LINE_LAYER_ID, FILL_LAYER_ID, HANDLES_SOURCE_ID, HANDLES_LAYER_ID, ROT_LINE_SOURCE_ID, ROT_LINE_LAYER_ID])

  // Cleanup on unmount or datasetId change
  useEffect(() => {
    return () => {
      safeRemoveLayer(map, HANDLES_LAYER_ID)
      safeRemoveLayer(map, ROT_LINE_LAYER_ID)
      safeRemoveLayer(map, LINE_LAYER_ID)
      safeRemoveLayer(map, FILL_LAYER_ID)

      safeRemoveSource(map, HANDLES_SOURCE_ID)
      safeRemoveSource(map, ROT_LINE_SOURCE_ID)
      safeRemoveSource(map, SOURCE_ID)

      try {
        if (map && map.getCanvas?.()) {
          map.getCanvas().style.cursor = ""
        }
      } catch {
        // ignore
      }
    }
  }, [map, SOURCE_ID, LINE_LAYER_ID, FILL_LAYER_ID, HANDLES_SOURCE_ID, HANDLES_LAYER_ID, ROT_LINE_SOURCE_ID, ROT_LINE_LAYER_ID])

  // Mouse / Pointer Dragging Handlers
  useEffect(() => {
    if (!isMapReady(map)) return

    function onMouseDown(e) {
      if (!corners || !geometryInfo || !isMapReady(map)) return

      // Check if handle was clicked
      const handleFeatures = safeGetLayer(map, HANDLES_LAYER_ID)
        ? map.queryRenderedFeatures(e.point, { layers: [HANDLES_LAYER_ID] })
        : []
      let targetHandle = null

      if (handleFeatures.length > 0) {
        targetHandle = handleFeatures[0].properties.handle
      } else {
        // Check if inside polygon body
        const fillFeatures = safeGetLayer(map, FILL_LAYER_ID)
          ? map.queryRenderedFeatures(e.point, { layers: [FILL_LAYER_ID] })
          : []
        if (fillFeatures.length > 0) {
          targetHandle = "body"
        }
      }

      if (!targetHandle) return

      // Disable map dragging so user drags transform handles smoothly
      try {
        map.dragPan.disable()
      } catch {
        // ignore
      }

      const center = geometryInfo.center
      const centerScreen = map.project([center.longitude, center.latitude])
      const curAngle = Math.atan2(e.point.y - centerScreen.y, e.point.x - centerScreen.x) * (180 / Math.PI)

      dragRef.current = {
        active: true,
        handleType: targetHandle,
        startPoint: { x: e.point.x, y: e.point.y, lng: e.lngLat.lng, lat: e.lngLat.lat },
        startCorners: JSON.parse(JSON.stringify(corners)),
        startAngle: curAngle,
        center: center,
      }
    }

    function onMouseMove(e) {
      if (!isMapReady(map)) return

      if (!dragRef.current.active) {
        // Change cursor icon when hovering handles
        if (safeGetLayer(map, HANDLES_LAYER_ID)) {
          const handleFeatures = map.queryRenderedFeatures(e.point, { layers: [HANDLES_LAYER_ID] })
          if (handleFeatures.length > 0) {
            const kind = handleFeatures[0].properties.kind
            map.getCanvas().style.cursor = kind === "rotation" ? "grab" : "pointer"
            return
          }
        }
        if (safeGetLayer(map, FILL_LAYER_ID)) {
          const fillFeatures = map.queryRenderedFeatures(e.point, { layers: [FILL_LAYER_ID] })
          if (fillFeatures.length > 0) {
            map.getCanvas().style.cursor = "move"
            return
          }
        }
        try {
          if (map.getCanvas?.()) map.getCanvas().style.cursor = ""
        } catch {
          // ignore
        }
        return
      }

      const { handleType, startPoint, startCorners, center } = dragRef.current
      const deltaLng = e.lngLat.lng - startPoint.lng
      const deltaLat = e.lngLat.lat - startPoint.lat

      // 1. Move mode or body drag: translate all 4 corners
      if (mode === "move" || handleType === "body") {
        setCorners({
          top_left: { longitude: startCorners.top_left.longitude + deltaLng, latitude: startCorners.top_left.latitude + deltaLat },
          top_right: { longitude: startCorners.top_right.longitude + deltaLng, latitude: startCorners.top_right.latitude + deltaLat },
          bottom_right: { longitude: startCorners.bottom_right.longitude + deltaLng, latitude: startCorners.bottom_right.latitude + deltaLat },
          bottom_left: { longitude: startCorners.bottom_left.longitude + deltaLng, latitude: startCorners.bottom_left.latitude + deltaLat },
        })
        return
      }

      // 2. Rotate mode or rotation handle drag
      if (mode === "rotate" || handleType === "rot") {
        const centerScreen = map.project([center.longitude, center.latitude])
        const curAngle = Math.atan2(e.point.y - centerScreen.y, e.point.x - centerScreen.x) * (180 / Math.PI)
        const angleDiff = curAngle - dragRef.current.startAngle
        const rad = (angleDiff * Math.PI) / 180

        const cos = Math.cos(rad)
        const sin = Math.sin(rad)

        function rotPoint(pt) {
          const dx = pt.longitude - center.longitude
          const dy = pt.latitude - center.latitude
          return {
            longitude: center.longitude + (dx * cos - dy * sin),
            latitude: center.latitude + (dx * sin + dy * cos),
          }
        }

        setRotationAngle((prev) => Math.round((prev + angleDiff) % 360))
        setCorners({
          top_left: rotPoint(startCorners.top_left),
          top_right: rotPoint(startCorners.top_right),
          bottom_right: rotPoint(startCorners.bottom_right),
          bottom_left: rotPoint(startCorners.bottom_left),
        })
        return
      }

      // 3. Free transform: move single corner independently
      if (mode === "free" && ["tl", "tr", "br", "bl"].includes(handleType)) {
        const next = JSON.parse(JSON.stringify(startCorners))
        const keyMap = { tl: "top_left", tr: "top_right", br: "bottom_right", bl: "bottom_left" }
        const key = keyMap[handleType]
        next[key].longitude += deltaLng
        next[key].latitude += deltaLat
        setCorners(next)
        return
      }

      // 4. Resize mode or corner/edge drag
      if (mode === "resize" || ["tl", "tr", "br", "bl", "edge-top", "edge-right", "edge-bottom", "edge-left"].includes(handleType)) {
        const next = JSON.parse(JSON.stringify(startCorners))

        if (lockAspect && ["tl", "tr", "br", "bl"].includes(handleType)) {
          // Scale relative to opposite corner
          const oppMap = { tl: "bottom_right", tr: "bottom_left", br: "top_left", bl: "top_right" }
          const oppKey = oppMap[handleType]
          const curKey = { tl: "top_left", tr: "top_right", br: "bottom_right", bl: "bottom_left" }[handleType]
          const opp = startCorners[oppKey]
          const curStart = startCorners[curKey]

          const initW = Math.abs(curStart.longitude - opp.longitude) || 1e-6
          const initH = Math.abs(curStart.latitude - opp.latitude) || 1e-6
          const newW = Math.abs(curStart.longitude + deltaLng - opp.longitude)
          const scale = newW / initW

          // Apply scale from opposite corner
          for (const k of ["top_left", "top_right", "bottom_right", "bottom_left"]) {
            next[k].longitude = opp.longitude + (startCorners[k].longitude - opp.longitude) * scale
            next[k].latitude = opp.latitude + (startCorners[k].latitude - opp.latitude) * scale
          }
        } else {
          // Non-uniform resize
          if (handleType === "tl") {
            next.top_left.longitude += deltaLng
            next.top_left.latitude += deltaLat
            next.top_right.latitude += deltaLat
            next.bottom_left.longitude += deltaLng
          } else if (handleType === "tr") {
            next.top_right.longitude += deltaLng
            next.top_right.latitude += deltaLat
            next.top_left.latitude += deltaLat
            next.bottom_right.longitude += deltaLng
          } else if (handleType === "br") {
            next.bottom_right.longitude += deltaLng
            next.bottom_right.latitude += deltaLat
            next.bottom_left.latitude += deltaLat
            next.top_right.longitude += deltaLng
          } else if (handleType === "bl") {
            next.bottom_left.longitude += deltaLng
            next.bottom_left.latitude += deltaLat
            next.bottom_right.latitude += deltaLat
            next.top_left.longitude += deltaLng
          } else if (handleType === "edge-top") {
            next.top_left.latitude += deltaLat
            next.top_right.latitude += deltaLat
          } else if (handleType === "edge-bottom") {
            next.bottom_left.latitude += deltaLat
            next.bottom_right.latitude += deltaLat
          } else if (handleType === "edge-left") {
            next.top_left.longitude += deltaLng
            next.bottom_left.longitude += deltaLng
          } else if (handleType === "edge-right") {
            next.top_right.longitude += deltaLng
            next.bottom_right.longitude += deltaLng
          }
        }
        setCorners(next)
      }
    }

    function onMouseUp() {
      if (dragRef.current.active) {
        dragRef.current.active = false
        map.dragPan.enable()
      }
    }

    try {
      map.on("mousedown", onMouseDown)
      map.on("mousemove", onMouseMove)
      map.on("mouseup", onMouseUp)
    } catch {
      // ignore
    }

    return () => {
      try {
        map.off("mousedown", onMouseDown)
        map.off("mousemove", onMouseMove)
        map.off("mouseup", onMouseUp)
        if (map.dragPan?.enable) map.dragPan.enable()
      } catch {
        // ignore
      }
    }
  }, [map, corners, geometryInfo, mode, lockAspect, HANDLES_LAYER_ID, FILL_LAYER_ID])

  // Action handlers
  async function handleApply() {
    if (!corners || processing) return
    setProcessing(true)
    setError(null)
    try {
      const res = await applyRasterTransform(datasetId, {
        corners,
        mode,
        rotationAngle,
        lockAspectRatio: lockAspect,
      })
      setCanUndo(Boolean(res.can_undo))
      setCanRedo(Boolean(res.can_redo))
      setProcessing(false)
      if (onApplied) onApplied(res)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to apply transformation."))
    }
  }

  async function handleUndo() {
    if (!canUndo || processing) return
    setProcessing(true)
    setError(null)
    try {
      const res = await undoRasterTransform(datasetId)
      if (res.corners) setCorners(res.corners)
      setCanUndo(Boolean(res.can_undo))
      setCanRedo(Boolean(res.can_redo))
      setProcessing(false)
      if (onApplied) onApplied(res)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to undo."))
    }
  }

  async function handleRedo() {
    if (!canRedo || processing) return
    setProcessing(true)
    setError(null)
    try {
      const res = await redoRasterTransform(datasetId)
      if (res.corners) setCorners(res.corners)
      setCanUndo(Boolean(res.can_undo))
      setCanRedo(Boolean(res.can_redo))
      setProcessing(false)
      if (onApplied) onApplied(res)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to redo."))
    }
  }

  async function handleReset() {
    if (processing) return
    if (!window.confirm("Reset raster to its original geographic footprint?")) return
    setProcessing(true)
    setError(null)
    try {
      const res = await resetRasterTransform(datasetId)
      if (res.corners) setCorners(res.corners)
      setCanUndo(false)
      setCanRedo(false)
      setRotationAngle(0)
      setProcessing(false)
      if (onApplied) onApplied(res)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to reset."))
    }
  }

  return (
    <aside className="workspace-transform-toolbar" aria-label="Raster Transformation Controls">
      <div className="workspace-transform-header">
        <div className="workspace-transform-title">
          <Sparkles className="size-4 text-[#0066cc]" />
          <span>Transform: {datasetName}</span>
        </div>
        <button
          type="button"
          className="workspace-dialog-close"
          onClick={onClose}
          aria-label="Close transform tool"
        >
          <X className="size-4" />
        </button>
      </div>

      {error && (
        <div className="workspace-dialog-error" style={{ margin: "4px 0" }}>
          <AlertCircle className="size-4" />
          <div>
            <strong>{error.message}</strong>
            <span>{error.details}</span>
          </div>
        </div>
      )}

      {/* Mode Switcher */}
      <div className="workspace-transform-modes">
        <button
          type="button"
          className={`workspace-transform-mode-btn${mode === "move" ? " is-active" : ""}`}
          onClick={() => setMode("move")}
          title="Move: Translate entire raster"
        >
          <Move className="size-3.5" />
          <span>Move</span>
        </button>
        <button
          type="button"
          className={`workspace-transform-mode-btn${mode === "resize" ? " is-active" : ""}`}
          onClick={() => setMode("resize")}
          title="Resize: Scale corners and edges"
        >
          <Maximize2 className="size-3.5" />
          <span>Resize</span>
        </button>
        <button
          type="button"
          className={`workspace-transform-mode-btn${mode === "rotate" ? " is-active" : ""}`}
          onClick={() => setMode("rotate")}
          title="Rotate: Rotate around pivot"
        >
          <RotateCw className="size-3.5" />
          <span>Rotate</span>
        </button>
        <button
          type="button"
          className={`workspace-transform-mode-btn${mode === "free" ? " is-active" : ""}`}
          onClick={() => setMode("free")}
          title="Free Transform: Move individual corners"
        >
          <Sliders className="size-3.5" />
          <span>Free</span>
        </button>
      </div>

      {/* Options & Metrics */}
      <div className="workspace-transform-options">
        <label className="workspace-transform-lock-label">
          <input
            type="checkbox"
            checked={lockAspect}
            onChange={(e) => setLockAspect(e.target.checked)}
          />
          {lockAspect ? <Lock className="size-3 text-[#0066cc]" /> : <Unlock className="size-3 text-[#7a7a7a]" />}
          <span>Lock Aspect Ratio</span>
        </label>
        {rotationAngle !== 0 && (
          <span className="workspace-transform-badge">
            {rotationAngle}°
          </span>
        )}
      </div>

      {/* Action Buttons */}
      <div className="workspace-transform-actions">
        <div className="workspace-transform-history-btns">
          <button
            type="button"
            className="workspace-secondary-button size-8 p-0"
            onClick={handleUndo}
            disabled={!canUndo || processing}
            title="Undo applied transformation"
          >
            <Undo2 className="size-3.5" />
          </button>
          <button
            type="button"
            className="workspace-secondary-button size-8 p-0"
            onClick={handleRedo}
            disabled={!canRedo || processing}
            title="Redo transformation"
          >
            <Redo2 className="size-3.5" />
          </button>
          <button
            type="button"
            className="workspace-secondary-button size-8 p-0"
            onClick={handleReset}
            disabled={processing}
            title="Reset to original"
          >
            <CornerDownLeft className="size-3.5" />
          </button>
        </div>

        <div className="workspace-transform-commit-btns">
          <button
            type="button"
            className="workspace-secondary-button text-xs py-1 px-3"
            onClick={onClose}
            disabled={processing}
          >
            Cancel
          </button>
          <button
            type="button"
            className="workspace-primary-button text-xs py-1 px-3"
            onClick={handleApply}
            disabled={processing || loading}
          >
            {processing ? <Loader2 className="size-3 animate-spin mr-1" /> : <Check className="size-3 mr-1" />}
            <span>Apply</span>
          </button>
        </div>
      </div>
    </aside>
  )
}
