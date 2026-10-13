import React, { useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum)
}

function FloorControlPointMarker({ point, number, selected, style, onMove, onMoveEnd, onSelect, readOnly }) {
  const dragRef = useRef(null)

  function beginDrag(event) {
    if (readOnly) return
    event.preventDefault()
    event.stopPropagation()
    onSelect(point.id)
    dragRef.current = true

    function move(moveEvent) {
      onMove(point.id, moveEvent.clientX, moveEvent.clientY)
    }

    function finish(finishEvent) {
      onMoveEnd(point.id, finishEvent.clientX, finishEvent.clientY)
      dragRef.current = null
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", finish)
    }

    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", finish)
  }

  return (
    <button
      type="button"
      className={`floor-control-marker ${selected ? "is-selected" : ""}`}
      style={style}
      aria-label={`Control point ${number} on the source image`}
      onClick={(event) => {
        event.stopPropagation()
        onSelect(point.id)
      }}
      onPointerDown={beginDrag}
    >
      <span className="floor-control-marker__number">{number}</span>
    </button>
  )
}

export default function SourceImagePane({
  sourceUrl,
  imageSize,
  points,
  draft,
  selectedId,
  onSelect,
  onCreate,
  onMove,
  onMoveEnd,
  readOnly = false,
  placementMode = false,
}) {
  const viewportRef = useRef(null)
  const layoutRef = useRef(null)
  const panStartRef = useRef(null)
  const [viewport, setViewport] = useState({ width: 0, height: 0 })
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 })
  const [imageReady, setImageReady] = useState(false)
  const [cursorCoordinate, setCursorCoordinate] = useState(null)
  const sourceWidth = Number(imageSize?.width) || 1
  const sourceHeight = Number(imageSize?.height) || 1

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return undefined
    const observer = new ResizeObserver(([entry]) => {
      setViewport({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const layout = useMemo(() => {
    if (!viewport.width || !viewport.height) return null
    const baseScale = Math.min(
      viewport.width / sourceWidth,
      viewport.height / sourceHeight,
    )
    const scale = baseScale * view.zoom
    return {
      scale,
      x: (viewport.width - sourceWidth * scale) / 2 + view.panX,
      y: (viewport.height - sourceHeight * scale) / 2 + view.panY,
    }
  }, [sourceHeight, sourceWidth, view, viewport])

  useEffect(() => {
    layoutRef.current = layout
  }, [layout])

  function coordinatesFromClient(clientX, clientY) {
    const bounds = viewportRef.current?.getBoundingClientRect()
    const currentLayout = layoutRef.current
    if (!bounds || !currentLayout) return null
    const x = (clientX - bounds.left - currentLayout.x) / currentLayout.scale
    const y = (clientY - bounds.top - currentLayout.y) / currentLayout.scale
    if (x < 0 || y < 0 || x > sourceWidth || y > sourceHeight) return null
    return {
      image_x: clamp(x, 0, sourceWidth - Number.EPSILON),
      image_y: clamp(y, 0, sourceHeight - Number.EPSILON),
    }
  }

  function handleViewportPointerDown(event) {
    if (event.button !== 0) return
    panStartRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      panX: view.panX,
      panY: view.panY,
      moved: false,
    }

    function move(moveEvent) {
      const start = panStartRef.current
      if (!start) return
      const deltaX = moveEvent.clientX - start.clientX
      const deltaY = moveEvent.clientY - start.clientY
      if (Math.hypot(deltaX, deltaY) > 4) start.moved = true
      setView((current) => ({
        ...current,
        panX: start.panX + deltaX,
        panY: start.panY + deltaY,
      }))
    }

    function finish(finishEvent) {
      const start = panStartRef.current
      panStartRef.current = null
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", finish)
      if (!start || start.moved) return
      const coordinates = coordinatesFromClient(finishEvent.clientX, finishEvent.clientY)
      if (coordinates && !readOnly && placementMode) onCreate(coordinates)
    }

    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", finish)
  }

  function changeZoom(nextZoom) {
    setView((current) => ({
      ...current,
      zoom: clamp(nextZoom, 0.5, 6),
    }))
  }

  function markerMove(pointId, clientX, clientY) {
    const coordinates = coordinatesFromClient(clientX, clientY)
    if (coordinates) onMove(pointId, coordinates)
  }

  function markerMoveEnd(pointId, clientX, clientY) {
    const coordinates = coordinatesFromClient(clientX, clientY)
    if (coordinates) onMoveEnd(pointId, coordinates)
  }

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return undefined

    const onWheel = (event) => {
      event.preventDefault()
      changeZoom(view.zoom * (event.deltaY < 0 ? 1.15 : 0.87))
    }

    element.addEventListener("wheel", onWheel, { passive: false })
    return () => element.removeEventListener("wheel", onWheel)
  }, [view.zoom])

  return (
    <section className="relative flex min-h-[360px] min-w-0 flex-1 flex-col overflow-hidden rounded-utility border border-hairline bg-white">
      <header className="flex min-h-14 shrink-0 items-center justify-between border-b border-hairline px-4">
        <div>
          <h2 className="text-[13px] font-semibold tracking-[0.08em] text-ink">SOURCE IMAGE</h2>
          <p className="mt-0.5 text-[12px] text-muted">Original pixel coordinates</p>
        </div>
        <p className="text-[12px] tabular-nums text-muted">{sourceWidth.toLocaleString()} × {sourceHeight.toLocaleString()}</p>
      </header>

      <div
        ref={viewportRef}
        className={`relative min-h-0 flex-1 touch-none overflow-hidden bg-[#eef0f2]${placementMode && !readOnly ? " cursor-crosshair" : " cursor-grab"}`}
        onPointerDown={handleViewportPointerDown}
        onPointerMove={(event) => setCursorCoordinate(coordinatesFromClient(event.clientX, event.clientY))}
        onPointerLeave={() => setCursorCoordinate(null)}
      >
        {layout && (
          <div
            className="absolute select-none shadow-[0_10px_30px_rgba(0,0,0,0.12)]"
            style={{
              width: sourceWidth,
              height: sourceHeight,
              transformOrigin: "0 0",
              transform: `translate(${layout.x}px, ${layout.y}px) scale(${layout.scale})`,
            }}
          >
            <img
              src={sourceUrl}
              crossOrigin="anonymous"
              alt="Uploaded source map for georeferencing"
              className="block h-full w-full select-none object-fill"
              draggable="false"
              decoding="async"
              onLoad={() => setImageReady(true)}
            />
            {imageReady && points.map((point, index) => (
              <FloorControlPointMarker
                key={point.id}
                point={point}
                number={index + 1}
                selected={selectedId === point.id}
                style={{
                  left: `${(point.image_x / sourceWidth) * 100}%`,
                  top: `${(point.image_y / sourceHeight) * 100}%`,
                  transform: `translate(-50%, -50%) scale(${1 / layout.scale})`,
                }}
                onSelect={onSelect}
                onMove={markerMove}
                onMoveEnd={markerMoveEnd}
                readOnly={readOnly}
              />
            ))}
            {draft && (
              <span
                className="floor-control-marker is-draft"
                style={{
                  left: `${(draft.image_x / sourceWidth) * 100}%`,
                  top: `${(draft.image_y / sourceHeight) * 100}%`,
                  transform: `translate(-50%, -50%) scale(${1 / layout.scale})`,
                }}
                aria-label="Pending control point on the source image"
              >
                <span className="floor-control-marker__number">{points.length + 1}</span>
              </span>
            )}
          </div>
        )}
        <div className="absolute bottom-3 left-3 z-10 flex overflow-hidden rounded-full border border-hairline bg-white shadow-sm">
          <Button type="button" className="geo-canvas-control" aria-label="Zoom in source image" onClick={() => changeZoom(view.zoom * 1.25)}>+</Button>
          <Button type="button" className="geo-canvas-control border-l border-hairline" aria-label="Zoom out source image" onClick={() => changeZoom(view.zoom / 1.25)}>−</Button>
        </div>
        <output className="map-coordinates" aria-live="polite">
          <span>X: {cursorCoordinate ? cursorCoordinate.image_x.toFixed(2) : "—"}</span>
          <span>Y: {cursorCoordinate ? cursorCoordinate.image_y.toFixed(2) : "—"}</span>
        </output>
        {!imageReady && <p className="absolute inset-0 grid place-items-center text-[14px] text-muted">Loading source image…</p>}
      </div>
    </section>
  )
}
