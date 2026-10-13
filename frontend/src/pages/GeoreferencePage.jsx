import React, { useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"

import {
  createControlPoint,
  datasetSourceImageUrl,
  georeferenceDataset,
  getDataset,
  getGeoreferenceConfig,
  listControlPoints,
  readableApiError,
  removeControlPoint,
  updateControlPoint,
} from "../api"
import ControlPointList from "../components/ControlPointList"
import ReferenceMap from "../components/ReferenceMap"
import SourceImagePane from "../components/SourceImagePane"
import { safeWorkspaceReturn } from "../lib/workspaceNavigation"
import { Button } from "@/components/ui/button"
import { ArrowLeft } from "lucide-react"
import EndSessionDialog from "../components/EndSessionDialog"

function overlayCoordinates(parameters, imageSize) {
  if (!parameters || !imageSize?.width || !imageSize?.height) return null
  const values = [parameters.a, parameters.b, parameters.c, parameters.d, parameters.e, parameters.f].map(Number)
  if (!values.every(Number.isFinite)) return null
  const [a, b, c, d, e, f] = values
  const project = (imageX, imageY) => [
    a * imageX + b * -imageY + c,
    d * imageX + e * -imageY + f,
  ]
  const width = Number(imageSize.width)
  const height = Number(imageSize.height)
  return [project(0, 0), project(width, 0), project(width, height), project(0, height)]
}

function recommendation(imageSize) {
  const width = Number(imageSize?.width) || 0
  const height = Number(imageSize?.height) || 0
  const longestEdge = Math.max(width, height)
  const ratio = Math.max(width, height) / Math.max(1, Math.min(width, height))
  if (longestEdge >= 6000 || ratio > 2.2) return "7–10 points for a large or irregular image"
  if (longestEdge >= 3000) return "4–6 points for this image"
  return "3–4 points for this image"
}

function titleText(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase())
}

function SavedConfiguration({ configuration }) {
  if (!configuration) return <p className="text-[13px] text-muted">No saved configuration.</p>
  const rows = [
    ["Status", titleText(configuration.status)],
    ["Transformation", titleText(configuration.transformation)],
    ["Control points", configuration.control_point_count],
    ["Target CRS", configuration.target_crs],
    ["Source size", `${configuration.source_width} × ${configuration.source_height}`],
    ["Output", configuration.output_format],
  ]
  return (
    <dl className="grid gap-2 text-[12px]">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[100px_1fr] gap-3">
          <dt className="text-muted">{label}</dt>
          <dd className="text-right text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function GeoreferencePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const returnTo = safeWorkspaceReturn(searchParams.get("returnTo"), id)
  const pointsRef = useRef([])
  const pairingRef = useRef(false)
  const [dataset, setDataset] = useState(null)
  const [points, setPoints] = useState([])
  const [savedConfig, setSavedConfig] = useState(null)
  const [calculation, setCalculation] = useState(null)
  const [mode, setMode] = useState("edit")
  const [controlPointPlacement, setControlPointPlacement] = useState(false)
  const [draft, setDraft] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [savingPoint, setSavingPoint] = useState(false)
  const [calculating, setCalculating] = useState(false)
  const [savingConfig, setSavingConfig] = useState(false)
  const [overlayEnabled, setOverlayEnabled] = useState(false)
  const [overlayOpacity, setOverlayOpacity] = useState(0.65)

  useEffect(() => {
    pointsRef.current = points
  }, [points])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    Promise.all([
      getDataset(id, controller.signal),
      listControlPoints(id, controller.signal),
      getGeoreferenceConfig(id, controller.signal),
    ])
      .then(([nextDataset, nextPoints, configuration]) => {
        if (!active) return
        setDataset(nextDataset)
        setPoints(nextPoints)
        setSavedConfig(configuration)
        setMode(configuration ? "view" : "edit")
        setSelectedId(nextPoints[0]?.id || null)
      })
      .catch((requestError) => {
        if (active && requestError.code !== "ERR_CANCELED") {
          setError(readableApiError(requestError, "Unable to load the visual georeferencer."))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [id])

  const imageSize = dataset?.metadata
  const sourceUrl = useMemo(() => datasetSourceImageUrl(id), [id])
  const previewCoordinates = useMemo(
    () => overlayCoordinates(calculation?.transformation_parameters, imageSize),
    [calculation, imageSize],
  )
  const transformLabel = points.length < 2
    ? "Add 2 points"
    : points.length === 2
      ? "Similarity transform"
      : "Affine transform"
  const editing = mode === "edit"
  const busy = savingPoint || calculating || savingConfig
  const canCalculate = editing && points.length >= 2 && !draft && !busy
  const canSave = editing && calculation?.status === "calculated" && !draft && !busy

  function invalidateCalculation() {
    setCalculation(null)
    setOverlayEnabled(false)
    if (savedConfig) {
      setSavedConfig((current) => current ? { ...current, status: "pending", reusable: false } : current)
    }
  }

  function selectPoint(pointId) {
    setSelectedId(pointId)
    setNotice(null)
  }

  function handleSourceCreate(coordinates) {
    if (!editing) return
    setError(null)
    setNotice(null)
    if (points.length >= 10) {
      setError({ message: "Too many control points were added.", details: "The visual georeferencer supports a maximum of 10 control points." })
      return
    }
    if (!controlPointPlacement) {
      setNotice("Select Add Control Point before choosing a source location.")
      return
    }
    setDraft(coordinates)
  }

  async function handleMapClick(location) {
    if (!editing || pairingRef.current) return
    setError(null)
    if (!draft) {
      setNotice("Click the corresponding location on the source image first.")
      return
    }
    pairingRef.current = true
    setSavingPoint(true)
    try {
      const created = await createControlPoint(id, {
        ...draft,
        longitude: location.lng,
        latitude: location.lat,
      })
      setPoints((current) => [...current, created])
      setSelectedId(created.id)
      setDraft(null)
      invalidateCalculation()
      setNotice(`Point ${points.length + 1} paired. Add another point or calculate the transformation.`)
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to save the control point."))
    } finally {
      pairingRef.current = false
      setSavingPoint(false)
    }
  }

  function cancelControlPoint() {
    setDraft(null)
    setControlPointPlacement(false)
    setNotice("Control point placement cancelled.")
  }

  function applyPointChange(pointId, patch) {
    setPoints((current) => current.map((point) => (point.id === pointId ? { ...point, ...patch } : point)))
  }

  async function persistPointChange(pointId, patch) {
    if (!editing) return
    const previous = pointsRef.current.find((point) => point.id === pointId)
    if (!previous) return
    const nextPoint = { ...previous, ...patch }
    applyPointChange(pointId, patch)
    try {
      const saved = await updateControlPoint(pointId, {
        image_x: nextPoint.image_x,
        image_y: nextPoint.image_y,
        longitude: nextPoint.longitude,
        latitude: nextPoint.latitude,
      })
      setPoints((current) => current.map((point) => (point.id === pointId ? saved : point)))
      invalidateCalculation()
    } catch (requestError) {
      applyPointChange(pointId, previous)
      setError(readableApiError(requestError, "Unable to update the control point."))
    }
  }

  function handleSourceMove(pointId, coordinates) {
    if (editing) applyPointChange(pointId, coordinates)
  }

  async function handleDelete(pointId) {
    if (!editing) return
    const previous = pointsRef.current
    const removed = previous.find((point) => point.id === pointId)
    if (!removed) return
    setPoints(previous.filter((point) => point.id !== pointId))
    if (selectedId === pointId) setSelectedId(previous.find((point) => point.id !== pointId)?.id || null)
    try {
      await removeControlPoint(pointId)
      invalidateCalculation()
    } catch (requestError) {
      setPoints(previous)
      setError(readableApiError(requestError, "Unable to delete the control point."))
    }
  }

  async function handleUndo() {
    if (!editing) return
    if (draft) {
      setDraft(null)
      return
    }
    const lastPoint = pointsRef.current.at(-1)
    if (lastPoint) await handleDelete(lastPoint.id)
  }

  async function handleReset() {
    if (!editing || (!points.length && !draft)) return
    if (!window.confirm("Clear all control points for this dataset?")) return
    const previous = pointsRef.current
    setDraft(null)
    setPoints([])
    setSelectedId(null)
    try {
      await Promise.all(previous.map((point) => removeControlPoint(point.id)))
      invalidateCalculation()
    } catch (requestError) {
      setPoints(previous)
      setError(readableApiError(requestError, "Unable to clear all control points."))
    }
  }

  async function handleCalculate() {
    setCalculating(true)
    setError(null)
    setNotice(null)
    try {
      const result = await georeferenceDataset(id, "calculate")
      setCalculation(result)
      setOverlayEnabled(true)
      const article = result.transformation === "affine" ? "an" : "a"
      setNotice(`${result.control_point_count} points calculated with ${article} ${result.transformation} transform. Review the preview, then save.`)
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to calculate the georeference."))
    } finally {
      setCalculating(false)
    }
  }

  async function handleSave() {
    setSavingConfig(true)
    setError(null)
    try {
      setNotice("Saving georeference configuration...")
      const result = await georeferenceDataset(id, "save")
      setCalculation(result)
      setSavedConfig(result)
      setMode("view")
      setNotice("Georeference saved and published to the main map.")
      navigate(returnTo, { replace: true })
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to save and publish the georeference."))
    } finally {
      setSavingConfig(false)
    }
  }

  function handleReuse() {
    if (!savedConfig?.reusable) return
    setCalculation(savedConfig)
    setOverlayEnabled(true)
    setMode("view")
    setError(null)
    setNotice("Saved control points and transformation parameters restored for inspection.")
  }

  if (loading) return <p className="page-message">Loading visual georeferencer…</p>
  if (!dataset) {
    return (
      <main className="min-h-[calc(100vh-44px)] bg-parchment px-5 py-20">
        <div className="error-panel mx-auto max-w-2xl" role="alert">
          <p className="font-semibold">{error?.message || "Dataset unavailable"}</p>
          <p className="mt-2 text-[14px] text-muted">{error?.details}</p>
          <Link className="text-action mt-5" to="/">Back to datasets</Link>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-[calc(100vh-44px)] bg-parchment p-3 phone:p-5">
      <div className="mx-auto flex max-w-canvas flex-col gap-3">
        <header className="flex min-h-[72px] flex-wrap items-center gap-2.5 rounded-[18px] border border-[#e0e0e0] bg-[#ffffff] px-4 py-3 sm:px-6 shadow-xs">
          <Link
            className="inline-flex items-center gap-1.5 text-xs text-[#7a7a7a] hover:text-[#0066cc] font-medium transition-colors shrink-0 mr-2 group"
            to={returnTo}
          >
            <ArrowLeft className="size-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span className="hidden sm:inline">Back to workspace</span>
            <span className="sm:hidden">Back</span>
          </Link>
          <h1 className="min-w-[160px] flex-1 text-xl sm:text-2xl font-semibold tracking-tight text-[#1d1d1f]">
            Visual Georeferencer
          </h1>
          <div className="min-w-[150px] text-right text-xs text-[#7a7a7a]">
            <p className="font-semibold text-[#1d1d1f]">
              {points.length} {points.length === 1 ? "point" : "points"} · {transformLabel}
            </p>
            <p className="mt-0.5 text-[11px]">Suggested: {recommendation(imageSize)}</p>
          </div>
          {savedConfig && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0 rounded-full border-[#e0e0e0] text-xs"
              disabled={!savedConfig.reusable || busy}
              onClick={handleReuse}
            >
              Reuse Config
            </Button>
          )}
          {savedConfig && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0 rounded-full border-[#e0e0e0] text-xs"
              disabled={editing || busy}
              onClick={() => {
                setMode("edit")
                setNotice("Editing enabled. Recalculate after changing control points.")
              }}
            >
              Edit Georeferencing
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 rounded-full border-[#e0e0e0] text-xs"
            disabled={!editing || busy || Boolean(draft)}
            onClick={() => {
              setControlPointPlacement(true)
              setNotice("Click the source image, then the matching reference-map location.")
            }}
          >
            {controlPointPlacement ? "Adding Point…" : "Add Control Point"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 rounded-full border-[#e0e0e0] text-xs"
            disabled={!canCalculate}
            onClick={handleCalculate}
          >
            {calculating ? "Calculating…" : "Calculate"}
          </Button>
          <Button
            type="button"
            variant="pill"
            size="sm"
            className="shrink-0 bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-normal"
            disabled={!canSave}
            onClick={handleSave}
          >
            {savingConfig ? "Saving…" : "Save Georeference"}
          </Button>
          <EndSessionDialog />
        </header>

        {savedConfig?.reuse_warning && <div className="rounded-utility border border-[#ebc36a] bg-[#fff8e6] px-4 py-3 text-[13px] text-ink" role="alert">{savedConfig.reuse_warning}</div>}
        {(error || notice || draft) && (
          <div className={`rounded-utility border px-4 py-3 text-[14px] ${error ? "border-[#e9b4b4] bg-[#fff6f6]" : "border-hairline bg-white"}`} role={error ? "alert" : "status"}>
            <p className="font-medium text-ink">{error?.message || (draft ? "Point pending map reference" : notice)}</p>
            <p className="mt-1 text-[12px] text-muted">{error?.details || (draft ? "Click the matching location on the reference map to complete this pair." : "")}</p>
            {draft && <Button type="button" variant="outline" className="mt-3 px-4" onClick={cancelControlPoint}>Cancel pending point</Button>}
          </div>
        )}

        <section className="grid min-h-[500px] gap-3 tablet-landscape:grid-cols-2" aria-label="Visual georeferencing workspace">
          <ReferenceMap points={points} selectedId={selectedId} onSelect={selectPoint} onMapClick={handleMapClick} onMoveEnd={persistPointChange} readOnly={!editing} placementMode={controlPointPlacement} overlay={{ visible: overlayEnabled && Boolean(previewCoordinates), imageUrl: sourceUrl, coordinates: previewCoordinates, opacity: overlayOpacity }} />
          <SourceImagePane sourceUrl={sourceUrl} imageSize={imageSize} points={points} draft={draft} selectedId={selectedId} onSelect={selectPoint} onCreate={handleSourceCreate} onMove={handleSourceMove} onMoveEnd={persistPointChange} readOnly={!editing} placementMode={controlPointPlacement} />
        </section>

        <section className="grid gap-3 desktop:grid-cols-[minmax(0,1fr)_330px]">
          <ControlPointList points={points} draft={draft} selectedId={selectedId} onSelect={selectPoint} onUpdate={persistPointChange} onDelete={handleDelete} readOnly={!editing} />
          <aside className="flex flex-col gap-5 rounded-utility border border-hairline bg-white p-4">
            <div><p className="mb-3 text-[12px] font-semibold tracking-[0.08em] text-ink">SAVED CONFIGURATION</p><SavedConfiguration configuration={savedConfig} /></div>
            <div className="grid grid-cols-3 gap-2"><Button type="button" variant="outline" onClick={handleUndo} disabled={!editing || (!points.length && !draft)}>Undo</Button><Button type="button" variant="outline" onClick={() => selectedId && handleDelete(selectedId)} disabled={!editing || !selectedId}>Delete</Button><Button type="button" variant="outline" onClick={handleReset} disabled={!editing || (!points.length && !draft)}>Reset</Button></div>
            <div className="border-t border-hairline pt-4"><div className="flex items-center justify-between gap-4"><label className="flex min-h-11 items-center gap-3 text-[14px] text-ink"><input type="checkbox" className="h-5 w-5 accent-primary" checked={overlayEnabled} disabled={!previewCoordinates} onChange={(event) => setOverlayEnabled(event.target.checked)} />Preview overlay</label><span className="text-[12px] text-muted">{previewCoordinates ? "Ready" : "Calculate first"}</span></div><div className="mt-3 flex items-center gap-3"><label htmlFor="georeference-opacity" className="shrink-0 text-[14px] text-muted">Opacity</label><input id="georeference-opacity" className="h-11 min-w-0 flex-1" type="range" min="0" max="100" disabled={!overlayEnabled || !previewCoordinates} value={Math.round(overlayOpacity * 100)} onChange={(event) => setOverlayOpacity(Number(event.target.value) / 100)} /><output className="w-9 text-right text-[13px] tabular-nums">{Math.round(overlayOpacity * 100)}%</output></div></div>
            <p className="text-[12px] leading-5 text-muted">Source convention: x = image_x, y = -image_y. Two points use similarity; three to ten use affine.</p>
          </aside>
        </section>
      </div>
    </main>
  )
}
