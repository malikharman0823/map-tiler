import React, { useEffect, useState, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { listDatasets, readableApiError, importMapProject } from "../api"
import DatasetCard from "../components/DatasetCard"
import TopHeader from "../components/TopHeader"

function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function HomePage() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [viewMode, setViewMode] = useState("grid") // 'grid' | 'list'
  const [importing, setImporting] = useState(false)

  const navigate = useNavigate()

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    setError(null)
    try {
      const res = await importMapProject(file)
      navigate(`/datasets/${res.dataset_id}`)
    } catch (err) {
      setError(readableApiError(err, "Failed to import project."))
    } finally {
      setImporting(false)
      e.target.value = ""
    }
  }


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

  const filteredDatasets = useMemo(() => {
    if (!searchQuery.trim()) return datasets
    const q = searchQuery.toLowerCase()
    return datasets.filter(d => 
      (d.name && d.name.toLowerCase().includes(q)) || 
      (d.filename && d.filename.toLowerCase().includes(q))
    )
  }, [datasets, searchQuery])

  const totalStorage = useMemo(() => {
    return datasets.reduce((acc, d) => acc + (d.file_size || 0), 0)
  }, [datasets])

  const tiledDatasets = useMemo(() => {
    return datasets.filter(d => d.tiling_status === "completed").length
  }, [datasets])

  return (
    <div className="flex flex-col min-h-screen">
      <TopHeader 
        breadcrumbs={[{ label: "Datasets" }]} 
        actions={
          <Link to="/upload" className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-200 text-xs font-medium transition-colors">
            <span className="material-symbols-outlined text-[15px] text-zinc-400">upload_file</span>
            <span>Upload</span>
          </Link>
        }
      />

      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6">
        {/* Top Title Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-zinc-500 mb-1">
              <span>SPATIAL ASSET REGISTRY</span>
              <span className="text-zinc-700">•</span>
              <span className="text-zinc-400">MapTiler MVP</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">Datasets &amp; Custom Tilesets</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Manage, style, georeference, and inspect vector and raster spatial datasets.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
            <input type="file" accept=".mtmap" onChange={handleImport} className="hidden" id="import-input" disabled={importing} />
            <label htmlFor="import-input" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-md bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 text-xs font-semibold shadow-sm transition-colors cursor-pointer disabled:opacity-50">
              <span className="material-symbols-outlined text-[16px]">upload</span>
              <span>{importing ? "Opening..." : "Open Project (.mtmap)"}</span>
            </label>
            <Link to="/upload" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-md bg-zinc-100 hover:bg-white text-zinc-900 text-xs font-semibold shadow-sm transition-colors">
              <span className="material-symbols-outlined text-[16px]">add</span>
              <span>Upload new dataset</span>
            </Link>
          </div>
        </div>

        {/* Metrics Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-1">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span className="font-medium">Active Datasets</span>
              <span className="material-symbols-outlined text-[16px] text-zinc-500">database</span>
            </div>
            <div className="text-2xl font-semibold text-zinc-100 tracking-tight">{loading ? '-' : datasets.length}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-1">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span className="font-medium">Storage Consumed</span>
              <span className="material-symbols-outlined text-[16px] text-zinc-500">cloud_done</span>
            </div>
            <div className="text-2xl font-semibold text-zinc-100 font-mono tracking-tight">{loading ? '-' : formatBytes(totalStorage)}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-1">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span className="font-medium">Tiled Datasets</span>
              <span className="material-symbols-outlined text-[16px] text-zinc-500">layers</span>
            </div>
            <div className="text-2xl font-semibold text-zinc-100 tracking-tight">{loading ? '-' : tiledDatasets}</div>
          </div>
        </div>

        {/* Filters & Toolbar */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <span className="material-symbols-outlined text-zinc-500 absolute left-3 top-2.5 text-[16px] pointer-events-none">search</span>
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-9 bg-zinc-900/60 text-zinc-200 text-xs pl-9 pr-3 rounded-md border border-zinc-800 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-400 focus:border-zinc-400 transition-colors" 
              placeholder="Filter by name or filename..." 
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="inline-flex h-9 p-0.5 rounded-md border border-zinc-800 bg-zinc-900/80 items-center">
              <button 
                type="button" 
                onClick={() => setViewMode('grid')}
                className={`h-full px-2 rounded-sm flex items-center justify-center transition-colors ${viewMode === 'grid' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`} 
                title="Grid View"
              >
                <span className="material-symbols-outlined text-[16px]">grid_view</span>
              </button>
              <button 
                type="button" 
                onClick={() => setViewMode('list')}
                className={`h-full px-2 rounded-sm flex items-center justify-center transition-colors ${viewMode === 'list' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`} 
                title="List View"
              >
                <span className="material-symbols-outlined text-[16px]">view_list</span>
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        {loading && <p className="text-sm text-zinc-400 text-center py-12">Loading datasets…</p>}
        {error && (
          <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-4 text-center">
            <p className="text-red-400 text-sm font-semibold">{error.message}</p>
            <p className="mt-1 text-xs text-red-400/80">{error.details}</p>
          </div>
        )}

        {!loading && !error && datasets.length === 0 && (
          <div className="rounded-lg border border-zinc-800 border-dashed py-16 text-center bg-zinc-900/20">
            <span className="material-symbols-outlined text-4xl text-zinc-600 mb-3">dataset</span>
            <p className="text-sm font-semibold text-zinc-200">No datasets yet</p>
            <p className="mt-1 text-xs text-zinc-500 mb-4">Upload your first dataset to begin mapping.</p>
            <Link to="/upload" className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md bg-zinc-100 hover:bg-white text-zinc-900 text-xs font-semibold shadow-sm transition-colors">
              Upload Dataset
            </Link>
          </div>
        )}

        {!loading && !error && datasets.length > 0 && filteredDatasets.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-zinc-400">No datasets match your search.</p>
          </div>
        )}

        {!loading && !error && filteredDatasets.length > 0 && viewMode === 'grid' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {filteredDatasets.map((dataset) => (
              <DatasetCard key={dataset.id} dataset={dataset} viewMode="grid" />
            ))}
          </div>
        )}

        {!loading && !error && filteredDatasets.length > 0 && viewMode === 'list' && (
          <div className="flex flex-col gap-2">
             {filteredDatasets.map((dataset) => (
              <DatasetCard key={dataset.id} dataset={dataset} viewMode="list" />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
