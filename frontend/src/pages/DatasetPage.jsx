import React, { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import {
  datasetTileUrl,
  deleteDataset,
  getDataset,
  getPbfPreview,
  readableApiError,
} from "../api"
import Map from "../components/Map"
import { displayName, formatName, statusLabel } from "../components/DatasetCard"

function BackIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current" strokeWidth="1.8">
      <path d="m9 5-5 5 5 5M4 10h12" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function DatasetPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [dataset, setDataset] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)
  const [opacity, setOpacity] = useState(0.65)
  const [pbfPreview, setPbfPreview] = useState(null)
  const [pbfLoading, setPbfLoading] = useState(false)
  const [pbfError, setPbfError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    getDataset(id, controller.signal)
      .then(setDataset)
      .catch((requestError) => {
        if (requestError.code !== "ERR_CANCELED") {
          setError(readableApiError(requestError, "Unable to load the dataset."))
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [id])

  const isPbf = Boolean(dataset?.filename?.toLowerCase().endsWith(".pbf"))

  useEffect(() => {
    if (!isPbf) return undefined

    const controller = new AbortController()
    setPbfLoading(true)
    setPbfError(null)
    getPbfPreview(id, controller.signal)
      .then(setPbfPreview)
      .catch((requestError) => {
        if (requestError.code !== "ERR_CANCELED") {
          setPbfError(readableApiError(requestError, "Unable to display the PBF preview."))
        }
      })
      .finally(() => setPbfLoading(false))
    return () => controller.abort()
  }, [id, isPbf])

  const tileUrl = useMemo(() => datasetTileUrl(id), [id])

  async function removeDataset() {
    if (!window.confirm("Delete this dataset and all of its stored files?")) return
    setDeleting(true)
    setError(null)
    try {
      await deleteDataset(id)
      navigate("/", { replace: true })
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to delete the dataset."))
      setDeleting(false)
    }
  }

  if (loading) return <p className="page-message">Loading dataset…</p>
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

  const metadata = dataset.metadata || {}
  const tilesReady = dataset.tile_status === "completed" && Boolean(dataset.tile_path)
  const pbfReady = isPbf && Boolean(pbfPreview?.geojson)
  const layerReady = tilesReady || pbfReady
  const mapBounds = pbfPreview?.bounds || metadata.bounds
  const mapCrs = pbfReady ? "EPSG:4326" : metadata.crs

  return (
    <main className="flex h-[calc(100vh-44px)] min-h-[620px] flex-col bg-parchment">
      <header className="z-10 flex min-h-[72px] shrink-0 items-center border-b border-hairline bg-[rgba(245,245,247,0.88)] px-5 backdrop-blur-[20px] phone:px-8">
        <div className="mx-auto flex w-full max-w-canvas items-center gap-5">
          <Link className="text-action shrink-0 text-[14px]" to="/">
            <BackIcon />
            <span className="hidden small-phone:inline">Back to datasets</span>
            <span className="small-phone:hidden">Back</span>
          </Link>
          <div className="min-w-0 flex-1 phone:flex phone:items-baseline phone:gap-6">
            <h1 className="truncate text-[21px] font-semibold leading-[1.19] phone:text-[28px] phone:leading-[1.14]">
              {displayName(dataset.filename)}
            </h1>
            <p className="truncate text-[12px] text-muted phone:text-[14px]">{dataset.filename}</p>
          </div>
          <button
            type="button"
            className="text-action shrink-0 px-2 text-[14px] text-muted"
            onClick={removeDataset}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "Delete dataset"}
          </button>
        </div>
      </header>

      <section className="relative min-h-0 flex-1" aria-label="Map workspace">
        <Map
          tileUrl={tileUrl}
          tilesReady={tilesReady}
          minZoom={dataset.tile_min_zoom}
          maxZoom={dataset.tile_max_zoom}
          bounds={mapBounds}
          crs={mapCrs}
          opacity={opacity}
          vectorData={pbfPreview?.geojson}
          vectorReady={pbfReady}
        />

        <aside className="absolute left-4 top-4 z-10 w-[calc(100%-2rem)] rounded-utility border border-hairline bg-white p-5 tablet:w-[370px] tablet:p-6">
          <dl className="grid grid-cols-[1fr_auto] gap-x-5 gap-y-2 text-[14px]">
            <dt className="text-muted">Format</dt>
            <dd className="text-right text-ink">{formatName(dataset.filename, metadata)}</dd>
            <dt className="text-muted">Status</dt>
            <dd className="text-right text-ink">{statusLabel(dataset)}</dd>
          </dl>
          <div className="mt-5 border-t border-hairline pt-5">
            <div className="flex items-center justify-between text-[14px]">
              <label htmlFor="opacity" className="text-muted">Layer opacity</label>
              <output htmlFor="opacity">{Math.round(opacity * 100)}%</output>
            </div>
            <input
              id="opacity"
              className="mt-3 h-11 w-full cursor-pointer"
              type="range"
              min="0"
              max="100"
              value={Math.round(opacity * 100)}
              disabled={!layerReady}
              onChange={(event) => setOpacity(Number(event.target.value) / 100)}
            />
            {isPbf && pbfLoading && (
              <p className="mt-2 text-[12px] leading-[1.3] text-muted">
                Preparing the PBF map preview…
              </p>
            )}
            {pbfReady && (
              <p className="mt-2 text-[12px] leading-[1.3] text-muted">
                Showing {pbfPreview.feature_count.toLocaleString()} map features
                {pbfPreview.truncated ? " in a bounded preview." : "."}
              </p>
            )}
            {!isPbf && !tilesReady && (
              <p className="mt-2 text-[12px] leading-[1.3] text-muted">
                Generated tiles are not ready. The base map remains available.
              </p>
            )}
          </div>
          {error && (
            <div className="mt-4 border-t border-hairline pt-4 text-[12px]" role="alert">
              <p className="font-semibold">{error.message}</p>
              <p className="mt-1 text-muted">{error.details}</p>
            </div>
          )}
          {pbfError && (
            <div className="mt-4 border-t border-hairline pt-4 text-[12px]" role="alert">
              <p className="font-semibold">{pbfError.message}</p>
              <p className="mt-1 text-muted">{pbfError.details}</p>
            </div>
          )}
        </aside>
      </section>
    </main>
  )
}
