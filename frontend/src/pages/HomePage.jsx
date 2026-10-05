import React, { useEffect, useState } from "react"
import { Link } from "react-router-dom"

import { listDatasets, readableApiError } from "../api"
import DatasetCard from "../components/DatasetCard"

export default function HomePage() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    listDatasets(controller.signal)
      .then(setDatasets)
      .catch((requestError) => {
        if (requestError.code !== "ERR_CANCELED") {
          setError(readableApiError(requestError, "Unable to load datasets."))
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  return (
    <main className="min-h-[calc(100vh-44px)] bg-parchment px-5 pb-20 phone:px-8">
      <section className="mx-auto max-w-canvas pt-20 text-center phone:pt-24 desktop:pt-24">
        <h1 className="text-[40px] font-semibold leading-[1.1] tracking-[-0.28px] text-ink small-desktop:text-[56px] small-desktop:leading-[1.07]">
          Your maps
        </h1>
        <p className="mt-3 text-[17px] text-muted phone:text-[24px] phone:font-light phone:leading-[1.5]">
          Manage and open your datasets
        </p>
        <Link className="primary-button mt-8 min-w-44" to="/upload">
          Upload a map
        </Link>
      </section>

      <section className="mx-auto mt-16 max-w-canvas desktop:mt-20" aria-label="Dataset library">
        {loading && <p className="page-message py-12">Loading datasets…</p>}
        {error && (
          <div className="error-panel mx-auto max-w-2xl" role="alert">
            <p className="font-semibold">{error.message}</p>
            <p className="mt-2 text-[14px] text-muted">{error.details}</p>
          </div>
        )}
        {!loading && !error && datasets.length === 0 && (
          <div className="mx-auto max-w-2xl border-t border-hairline py-12 text-center">
            <p className="text-[21px] font-semibold">No maps yet</p>
            <p className="mt-2 text-[17px] text-muted">Upload your first dataset to begin.</p>
          </div>
        )}
        {!loading && !error && datasets.length > 0 && (
          <div className="grid grid-cols-1 gap-5 phone:grid-cols-2 small-desktop:grid-cols-3 desktop:gap-6">
            {datasets.map((dataset) => (
              <DatasetCard key={dataset.id} dataset={dataset} />
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
