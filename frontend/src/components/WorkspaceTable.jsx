import React, { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Copy,
  Database,
  Download,
  Eye,
  EyeOff,
  Filter,
  Image,
  Layers,
  Loader2,
  MapPin,
  Maximize2,
  Navigation,
  Plus,
  Save,
  Search,
  Sparkles,
  X,
} from "lucide-react"

import { updateIconPoint } from "../api"

const SORT_FIELDS = {
  name: "name",
  kind: "kind",
  dataset_name: "dataset",
  status: "status",
  updated_at: "updated_at",
}

function formatKind(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function coordinates(record) {
  if (record.kind === "raster") {
    const bounds = record.bounds
    if (Array.isArray(bounds)) return bounds.map((value) => Number(value).toFixed(4)).join(", ")
    if (bounds && typeof bounds === "object") {
      const values = [bounds.min_x ?? bounds.left, bounds.min_y ?? bounds.bottom, bounds.max_x ?? bounds.right, bounds.max_y ?? bounds.top]
      return values.every((value) => Number.isFinite(Number(value)))
        ? values.map((value) => Number(value).toFixed(4)).join(", ")
        : "—"
    }
    return "—"
  }
  return `${Number(record.latitude).toFixed(6)}, ${Number(record.longitude).toFixed(6)}`
}

const LAYER_PALETTE = [
  "#0066cc", // action blue
  "#8b5cf6", // purple
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ec4899", // pink
  "#06b6d4", // cyan
]

function getLayerColor(datasetId, members) {
  const index = members.findIndex((m) => m.dataset_id === datasetId)
  if (index >= 0) {
    return LAYER_PALETTE[index % LAYER_PALETTE.length]
  }
  return "#64748b"
}

function RecordEditor({
  record,
  member,
  icons,
  workspaceId,
  onClose,
  onMemberSave,
  onRecordSaved,
  onDirtyChange,
  onSwitchToMap,
}) {
  const [draft, setDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [copiedKey, setCopiedKey] = useState(null)

  useEffect(() => {
    setDraft(
      record?.kind === "raster"
        ? { alias: member?.alias || member?.dataset?.filename || "" }
        : record?.kind === "icon_point"
        ? { icon_key: record.icon_key || "", description: record.description || "" }
        : {}
    )
    setError(null)
    onDirtyChange(false)
  }, [member, onDirtyChange, record])

  if (!record) return null
  const editable = record.kind === "raster" || record.kind === "icon_point"

  function copyText(key, text) {
    if (!text) return
    navigator.clipboard?.writeText(String(text))
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 1800)
  }

  function update(name, value) {
    setDraft((current) => ({ ...current, [name]: value }))
    onDirtyChange(true)
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      if (record.kind === "raster") {
        await onMemberSave(record.dataset_id, { alias: draft.alias })
      } else if (record.kind === "icon_point") {
        await updateIconPoint(record.id, {
          icon_key: draft.icon_key || null,
          description: draft.description || null,
          latitude: record.latitude,
          longitude: record.longitude,
        })
        await onRecordSaved()
      }
      onDirtyChange(false)
    } catch (requestError) {
      setError(requestError?.response?.data?.error?.message || "Unable to save this record.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <aside className="workspace-record-editor record-inspector" aria-label="Record details">
      <div className="workspace-panel-header">
        <div className="flex items-center gap-2">
          <span className={`record-badge record-badge-${record.kind}`}>
            {formatKind(record.kind)}
          </span>
          <h2 className="text-sm font-semibold truncate max-w-[200px]" title={record.name}>
            {record.name}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 hover:bg-[#f5f5f7] transition-colors"
          aria-label="Close record details"
        >
          <X className="size-4 text-[#7a7a7a]" />
        </button>
      </div>

      <div className="workspace-record-fields">
        {/* Quick Map Action */}
        <div className="flex items-center gap-2 pb-2 border-b border-[#f0f0f0]">
          {onSwitchToMap && (
            <button
              type="button"
              className="record-action-btn flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] text-xs font-medium text-[#1d1d1f] shadow-2xs transition-colors"
              onClick={() => onSwitchToMap(record.id)}
            >
              <Navigation className="size-3.5 text-[#0066cc]" />
              <span>Locate on Map</span>
            </button>
          )}
          {record.kind === "raster" && record.status === "raw" && (
            <Link
              to={`/datasets/${record.dataset_id}/georeference?returnTo=${encodeURIComponent(
                `/datasets/${workspaceId}/workspace?view=database`
              )}`}
              className="record-action-btn flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-[#0066cc] bg-[#0066cc] hover:bg-[#0071e3] text-xs font-medium text-white shadow-2xs transition-colors"
            >
              <Sparkles className="size-3.5" />
              <span>Georeference</span>
            </Link>
          )}
        </div>

        {/* Editable Fields */}
        {record.kind === "raster" && (
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-[#1d1d1f]">Layer Alias</span>
            <input
              className="w-full text-xs py-2 px-3 rounded-lg border border-[#e0e0e0] bg-[#ffffff] focus:border-[#0066cc] outline-none"
              value={draft.alias || ""}
              onChange={(event) => update("alias", event.target.value)}
              placeholder="Display name for this layer"
            />
          </label>
        )}

        {record.kind === "icon_point" && (
          <div className="space-y-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-[#1d1d1f]">Icon Marker</span>
              <select
                className="w-full text-xs py-2 px-3 rounded-lg border border-[#e0e0e0] bg-[#ffffff] focus:border-[#0066cc] outline-none"
                value={draft.icon_key || ""}
                onChange={(event) => update("icon_key", event.target.value)}
              >
                <option value="">Default pin</option>
                {icons.map((icon) => (
                  <option key={icon} value={icon}>
                    {formatKind(icon)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-[#1d1d1f]">Description / Note</span>
              <textarea
                className="w-full text-xs py-2 px-3 rounded-lg border border-[#e0e0e0] bg-[#ffffff] focus:border-[#0066cc] outline-none resize-none"
                value={draft.description || ""}
                onChange={(event) => update("description", event.target.value)}
                rows="3"
                placeholder="Annotation text"
              />
            </label>
          </div>
        )}

        {/* Read-only dataset attributes */}
        <div className="space-y-3 pt-2">
          <div className="text-[11px] font-mono uppercase tracking-wider text-[#7a7a7a] font-semibold">
            Row Attributes
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-start justify-between gap-2 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <span className="text-[#7a7a7a] shrink-0 font-mono text-[11px]">id</span>
              <div className="flex items-center gap-1 min-w-0">
                <span className="font-mono text-[11px] text-[#1d1d1f] truncate">{record.id}</span>
                <button
                  type="button"
                  onClick={() => copyText("id", record.id)}
                  className="text-[#7a7a7a] hover:text-[#0066cc]"
                  title="Copy ID"
                >
                  {copiedKey === "id" ? <Check className="size-3 text-[#34c759]" /> : <Copy className="size-3" />}
                </button>
              </div>
            </div>

            <div className="flex items-start justify-between gap-2 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <span className="text-[#7a7a7a] shrink-0 font-mono text-[11px]">layer</span>
              <span className="font-medium text-[#1d1d1f] truncate">{record.dataset_name}</span>
            </div>

            <div className="flex items-start justify-between gap-2 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <span className="text-[#7a7a7a] shrink-0 font-mono text-[11px]">status</span>
              <span className={`workspace-status status-${record.status}`}>{formatKind(record.status)}</span>
            </div>

            <div className="flex items-start justify-between gap-2 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <span className="text-[#7a7a7a] shrink-0 font-mono text-[11px]">crs</span>
              <span className="font-mono text-[11px] text-[#1d1d1f]">{record.crs || "Unprojected"}</span>
            </div>

            <div className="flex flex-col gap-1 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <div className="flex items-center justify-between">
                <span className="text-[#7a7a7a] font-mono text-[11px]">coordinates</span>
                <button
                  type="button"
                  onClick={() => copyText("coords", coordinates(record))}
                  className="text-[#7a7a7a] hover:text-[#0066cc]"
                  title="Copy coordinates"
                >
                  {copiedKey === "coords" ? <Check className="size-3 text-[#34c759]" /> : <Copy className="size-3" />}
                </button>
              </div>
              <span className="font-mono text-[11px] text-[#1d1d1f] break-all">{coordinates(record)}</span>
            </div>

            {record.kind === "control_point" && (
              <div className="flex items-start justify-between gap-2 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
                <span className="text-[#7a7a7a] shrink-0 font-mono text-[11px]">image_pixel</span>
                <span className="font-mono text-[11px] text-[#1d1d1f]">
                  X: {record.image_x}, Y: {record.image_y}
                </span>
              </div>
            )}

            <div className="flex flex-col gap-1 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
              <div className="flex items-center justify-between">
                <span className="text-[#7a7a7a] font-mono text-[11px]">local_file_loc</span>
                <button
                  type="button"
                  onClick={() => copyText("path", record.managed_path)}
                  className="text-[#7a7a7a] hover:text-[#0066cc]"
                  title="Copy path"
                >
                  {copiedKey === "path" ? <Check className="size-3 text-[#34c759]" /> : <Copy className="size-3" />}
                </button>
              </div>
              <span className="font-mono text-[11px] text-[#1d1d1f] break-all leading-tight">
                {record.managed_path}
              </span>
            </div>

            {record.georeferenced_path && (
              <div className="flex flex-col gap-1 p-2 rounded-lg bg-[#fafafc] border border-[#f0f0f0]">
                <div className="flex items-center justify-between">
                  <span className="text-[#7a7a7a] font-mono text-[11px]">georef_output_path</span>
                  <button
                    type="button"
                    onClick={() => copyText("georef", record.georeferenced_path)}
                    className="text-[#7a7a7a] hover:text-[#0066cc]"
                    title="Copy path"
                  >
                    {copiedKey === "georef" ? <Check className="size-3 text-[#34c759]" /> : <Copy className="size-3" />}
                  </button>
                </div>
                <span className="font-mono text-[11px] text-[#1d1d1f] break-all leading-tight">
                  {record.georeferenced_path}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Metadata JSON Inspector */}
        {record.metadata && Object.keys(record.metadata).length > 0 && (
          <div className="space-y-2 pt-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-wider text-[#7a7a7a] font-semibold">
                Metadata JSON
              </span>
              <button
                type="button"
                onClick={() => copyText("meta", JSON.stringify(record.metadata, null, 2))}
                className="text-[11px] text-[#0066cc] hover:underline inline-flex items-center gap-1"
              >
                {copiedKey === "meta" ? <Check className="size-3 text-[#34c759]" /> : <Copy className="size-3" />}
                <span>Copy JSON</span>
              </button>
            </div>
            <pre className="p-2.5 rounded-lg bg-[#1d1d1f] text-[#f5f5f7] text-[10px] font-mono overflow-auto max-h-40 leading-relaxed">
              {JSON.stringify(record.metadata, null, 2)}
            </pre>
          </div>
        )}

        {error && <p className="workspace-inline-error">{error}</p>}
      </div>

      {editable && (
        <div className="workspace-editor-actions flex items-center justify-end gap-2 p-3 border-t border-[#f0f0f0]">
          <button
            type="button"
            className="px-3 py-1.5 rounded-lg border border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] text-xs font-medium text-[#1d1d1f] transition-colors"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="px-3 py-1.5 rounded-lg bg-[#0066cc] hover:bg-[#0071e3] text-xs font-medium text-white transition-colors flex items-center gap-1.5"
            onClick={save}
            disabled={saving}
          >
            {saving ? <Loader2 className="size-3 animate-spin" /> : <Save className="size-3" />}
            <span>Save Changes</span>
          </button>
        </div>
      )}
    </aside>
  )
}

export default function WorkspaceTable({
  recordsData,
  filters,
  onFiltersChange,
  loading,
  members,
  icons,
  selectedRecordId,
  onSelectRecord,
  onMemberUpdate,
  onRecordsRefresh,
  onDirtyChange,
  workspaceId,
  onAddDataset,
  onSwitchToMap,
}) {
  const [columnsOpen, setColumnsOpen] = useState(false)
  const [columnVisibility, setColumnVisibility] = useState({})
  const [copiedPathId, setCopiedPathId] = useState(null)

  const selectedRecord = recordsData.records.find((record) => record.id === selectedRecordId)
  const selectedMember = members.find((member) => member.dataset_id === selectedRecord?.dataset_id)

  function handleToggleVisibility(record) {
    if (!onMemberUpdate) return
    const member = members.find((m) => m.dataset_id === record.dataset_id)
    if (!member) return

    const turnOn = !record.visible
    const parentPatch = turnOn && !member.visible ? { visible: true } : {}

    if (record.kind === "raster") {
      onMemberUpdate(record.dataset_id, { raster_visible: turnOn, ...parentPatch }).catch(() => undefined)
    } else if (record.kind === "control_point") {
      onMemberUpdate(record.dataset_id, { control_points_visible: turnOn, ...parentPatch }).catch(() => undefined)
    } else if (record.kind === "icon_point") {
      onMemberUpdate(record.dataset_id, { icon_points_visible: turnOn, ...parentPatch }).catch(() => undefined)
    }
  }

  function copyPath(id, path) {
    if (!path) return
    navigator.clipboard?.writeText(path)
    setCopiedPathId(id)
    setTimeout(() => setCopiedPathId(null), 1800)
  }

  function exportRecords(format = "json") {
    const data = recordsData.records
    if (!data.length) return

    let content = ""
    let mime = "application/json"
    let filename = `workspace_records_${new Date().toISOString().slice(0, 10)}.${format}`

    if (format === "json") {
      content = JSON.stringify(data, null, 2)
    } else if (format === "csv") {
      mime = "text/csv"
      const headers = ["id", "layer", "sublayer_type", "name", "coordinates", "local_file_loc", "crs", "status", "visible"]
      const rows = data.map((r) => [
        `"${r.id}"`,
        `"${r.dataset_name}"`,
        `"${r.kind}"`,
        `"${r.name}"`,
        `"${coordinates(r)}"`,
        `"${r.managed_path}"`,
        `"${r.crs || ""}"`,
        `"${r.status}"`,
        r.visible ? "true" : "false",
      ])
      content = [headers.join(","), ...rows.map((row) => row.join(","))].join("\n")
    }

    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const columns = useMemo(
    () => [
      {
        id: "row_number",
        header: "#",
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-[11px] font-mono text-[#7a7a7a] select-none">
            {row.index + 1 + (filters.page - 1) * filters.pageSize}
          </span>
        ),
      },
      {
        accessorKey: "name",
        header: "Name / Label",
        cell: ({ row }) => (
          <div className="workspace-name-cell flex items-center gap-2">
            <span
              className="size-2 rounded-full shrink-0"
              style={{ backgroundColor: getLayerColor(row.original.dataset_id, members) }}
              title={`Layer: ${row.original.dataset_name}`}
            />
            <span className="font-medium text-[#1d1d1f] truncate max-w-[200px]" title={row.original.name}>
              {row.original.name}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "kind",
        header: "Sublayer Type",
        cell: ({ getValue }) => {
          const kind = getValue()
          return (
            <span className={`record-badge record-badge-${kind}`}>
              {formatKind(kind)}
            </span>
          )
        },
      },
      {
        accessorKey: "dataset_name",
        header: "Layer",
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 text-xs text-[#1d1d1f] max-w-[150px] truncate">
            <span className="truncate">{row.original.dataset_name}</span>
          </div>
        ),
      },
      {
        accessorKey: "visible",
        header: "Visible",
        enableSorting: false,
        cell: ({ row }) => {
          const isVisible = row.original.visible
          return (
            <button
              type="button"
              className={`p-1 rounded-md transition-colors ${
                isVisible ? "text-[#0066cc] hover:bg-[#eaf3fc]" : "text-[#7a7a7a] hover:bg-[#f0f0f0]"
              }`}
              title={isVisible ? "Visible (click to hide)" : "Hidden (click to show)"}
              onClick={(e) => {
                e.stopPropagation()
                handleToggleVisibility(row.original)
              }}
            >
              {isVisible ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            </button>
          )
        },
      },
      {
        id: "coordinates",
        header: "Coordinates / Bounds",
        enableSorting: false,
        cell: ({ row }) => (
          <span className="font-mono text-[11px] text-[#555] truncate max-w-[200px] block" title={coordinates(row.original)}>
            {coordinates(row.original)}
          </span>
        ),
      },
      {
        accessorKey: "managed_path",
        header: "Local File Loc",
        enableSorting: false,
        cell: ({ row }) => {
          const path = row.original.managed_path
          const isCopied = copiedPathId === row.original.id
          return (
            <button
              type="button"
              className="workspace-path-cell flex items-center gap-1 text-left font-mono text-[11px] text-[#555] hover:text-[#0066cc] group max-w-[240px]"
              onClick={(event) => {
                event.stopPropagation()
                copyPath(row.original.id, path)
              }}
              title={`Click to copy: ${path}`}
            >
              <span className="truncate">{path}</span>
              {isCopied ? (
                <Check className="size-3 text-[#34c759] shrink-0" />
              ) : (
                <Copy className="size-3 opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />
              )}
            </button>
          )
        },
      },
      {
        accessorKey: "crs",
        header: "CRS",
        enableSorting: false,
        cell: ({ getValue }) => (
          <span className="font-mono text-[11px] text-[#7a7a7a] px-1.5 py-0.5 rounded bg-[#f5f5f7] border border-[#e0e0e0]">
            {getValue() || "Unprojected"}
          </span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => (
          <span className={`workspace-status status-${getValue()}`}>
            {formatKind(getValue())}
          </span>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        enableSorting: false,
        cell: ({ row }) => {
          const record = row.original
          return (
            <div className="flex items-center gap-1">
              {onSwitchToMap && (
                <button
                  type="button"
                  className="p-1 rounded hover:bg-[#eaf3fc] text-[#7a7a7a] hover:text-[#0066cc] transition-colors"
                  title="Locate on map"
                  onClick={(e) => {
                    e.stopPropagation()
                    onSwitchToMap(record.id)
                  }}
                >
                  <MapPin className="size-3.5" />
                </button>
              )}
              {record.kind === "raster" && record.status === "raw" && (
                <Link
                  to={`/datasets/${record.dataset_id}/georeference?returnTo=${encodeURIComponent(
                    `/datasets/${workspaceId}/workspace?view=database`
                  )}`}
                  className="p-1 rounded hover:bg-[#eaf3fc] text-[#0066cc] transition-colors"
                  title="Georeference this dataset"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Sparkles className="size-3.5" />
                </Link>
              )}
            </div>
          )
        },
      },
    ],
    [copiedPathId, filters.page, filters.pageSize, members, onSwitchToMap, workspaceId]
  )

  const sorting = [
    {
      id: Object.entries(SORT_FIELDS).find(([, backend]) => backend === filters.sort)?.[0] || "name",
      desc: filters.order === "desc",
    },
  ]

  const table = useReactTable({
    data: recordsData.records,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    rowCount: recordsData.total,
    state: {
      sorting,
      pagination: { pageIndex: filters.page - 1, pageSize: filters.pageSize },
      columnVisibility,
    },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater
      const [rule] = next
      onFiltersChange({
        sort: SORT_FIELDS[rule?.id] || "name",
        order: rule?.desc ? "desc" : "asc",
      })
    },
    onColumnVisibilityChange: setColumnVisibility,
  })

  // Quick sublayer type filter tabs
  const sublayerTabs = [
    { id: "", label: "All Records", icon: Database },
    { id: "raster", label: "Rasters", icon: Image },
    { id: "control_point", label: "Control Points", icon: MapPin },
    { id: "icon_point", label: "User Icons", icon: Sparkles },
  ]

  return (
    <div className="workspace-table-layout">
      <section className="workspace-table-view flex flex-col h-full bg-[#ffffff]">
        {/* Table editor header */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 border-b border-[#e0e0e0] bg-[#fafafc]">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Database className="size-4 text-[#0066cc]" />
              <span className="text-sm font-semibold text-[#1d1d1f]">Workspace Records</span>
            </div>
            <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-[#ffffff] border border-[#e0e0e0] text-[#7a7a7a]">
              {recordsData.total} {recordsData.total === 1 ? "row" : "rows"}
            </span>

            {/* Quick Sublayer Type Filter Tabs */}
            <div className="hidden md:flex items-center gap-1 ml-2 bg-[#f0f0f2] p-0.5 rounded-lg border border-[#e0e0e0]">
              {sublayerTabs.map((tab) => {
                const TabIcon = tab.icon
                const isActive = filters.kind === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => onFiltersChange({ kind: tab.id, page: 1 })}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-[#ffffff] text-[#1d1d1f] shadow-2xs font-semibold"
                        : "text-[#7a7a7a] hover:text-[#1d1d1f]"
                    }`}
                  >
                    <TabIcon className="size-3" />
                    <span>{tab.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Add / Merge Dataset button right in table header */}
            {onAddDataset && (
              <button
                type="button"
                onClick={onAddDataset}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0066cc] hover:bg-[#0071e3] text-white text-xs font-medium shadow-2xs transition-colors"
                title="Add and merge another dataset into this workspace"
              >
                <Plus className="size-3.5" />
                <span>Add Dataset</span>
              </button>
            )}

            {/* Export Menu */}
            <div className="flex items-center">
              <button
                type="button"
                onClick={() => exportRecords("csv")}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] text-[#1d1d1f] text-xs font-medium transition-colors"
                title="Export rows as CSV"
              >
                <Download className="size-3 text-[#7a7a7a]" />
                <span className="hidden sm:inline">Export</span>
              </button>
            </div>
          </div>
        </div>

        {/* Second Toolbar: Search, Filters, Column Select */}
        <div className="workspace-table-toolbar flex flex-wrap items-center gap-2.5 px-4 py-2 border-b border-[#e0e0e0] bg-[#ffffff]">
          {/* Search Bar */}
          <div className="workspace-table-search flex items-center gap-2 flex-1 min-w-[200px] max-w-sm px-2.5 py-1.5 rounded-lg border border-[#e0e0e0] bg-[#fafafc] focus-within:bg-[#ffffff] focus-within:border-[#0066cc] transition-all">
            <Search className="size-3.5 text-[#7a7a7a] shrink-0" />
            <input
              value={filters.search}
              onChange={(event) => onFiltersChange({ search: event.target.value, page: 1 })}
              placeholder="Search records by name, ID, or coords…"
              className="text-xs bg-transparent border-0 outline-none w-full placeholder:text-[#7a7a7a]"
              aria-label="Search workspace records"
            />
            {filters.search && (
              <button
                type="button"
                onClick={() => onFiltersChange({ search: "", page: 1 })}
                className="text-[#7a7a7a] hover:text-[#1d1d1f]"
              >
                <X className="size-3" />
              </button>
            )}
          </div>

          {/* Layer Filter (All Datasets or Specific Member) */}
          <div className="flex items-center gap-1.5">
            <Filter className="size-3 text-[#7a7a7a] hidden sm:inline" />
            <select
              value={filters.datasetId}
              onChange={(event) => onFiltersChange({ datasetId: event.target.value, page: 1 })}
              className="text-xs py-1.5 px-2.5 rounded-lg border border-[#e0e0e0] bg-[#fafafc] text-[#1d1d1f] outline-none"
              aria-label="Filter by dataset layer"
            >
              <option value="">All Layers ({members.length})</option>
              {members.map((member) => (
                <option key={member.dataset_id} value={member.dataset_id}>
                  {member.name} {member.is_primary ? "(Primary)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Mobile sublayer dropdown */}
          <div className="md:hidden">
            <select
              value={filters.kind}
              onChange={(event) => onFiltersChange({ kind: event.target.value, page: 1 })}
              className="text-xs py-1.5 px-2.5 rounded-lg border border-[#e0e0e0] bg-[#fafafc] text-[#1d1d1f] outline-none"
              aria-label="Filter record type"
            >
              <option value="">All Types</option>
              <option value="raster">Rasters</option>
              <option value="control_point">Control Points</option>
              <option value="icon_point">User Icons</option>
            </select>
          </div>

          {/* Status Filter */}
          <select
            value={filters.status}
            onChange={(event) => onFiltersChange({ status: event.target.value, page: 1 })}
            className="text-xs py-1.5 px-2.5 rounded-lg border border-[#e0e0e0] bg-[#fafafc] text-[#1d1d1f] outline-none"
            aria-label="Filter status"
          >
            <option value="">All Statuses</option>
            <option value="georeferenced">Georeferenced</option>
            <option value="tiled">Tiled</option>
            <option value="raw">Raw</option>
          </select>

          {/* Columns Visibility */}
          <div className="workspace-columns-menu relative ml-auto">
            <button
              type="button"
              onClick={() => setColumnsOpen((value) => !value)}
              className="flex items-center gap-1.5 text-xs py-1.5 px-2.5 rounded-lg border border-[#e0e0e0] bg-[#fafafc] text-[#7a7a7a] hover:text-[#1d1d1f] hover:bg-[#ffffff] transition-colors"
            >
              <Columns3 className="size-3.5" />
              <span>Columns</span>
            </button>
            {columnsOpen && (
              <div className="workspace-columns-popover absolute right-0 top-full mt-1.5 z-30 p-2.5 rounded-xl border border-[#e0e0e0] bg-[#ffffff] shadow-lg min-w-[180px] space-y-1.5">
                <div className="text-[11px] font-semibold text-[#7a7a7a] pb-1 border-b border-[#f0f0f0]">
                  Toggle Columns
                </div>
                {table.getAllLeafColumns().map((column) => (
                  <label
                    key={column.id}
                    className="flex items-center gap-2 text-xs text-[#1d1d1f] cursor-pointer hover:bg-[#f5f5f7] p-1 rounded"
                  >
                    <input
                      type="checkbox"
                      checked={column.getIsVisible()}
                      onChange={column.getToggleVisibilityHandler()}
                      className="accent-[#0066cc]"
                    />
                    <span>{typeof column.columnDef.header === "string" ? column.columnDef.header : column.id}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Table Body */}
        <div className="workspace-table-scroll flex-1 overflow-auto bg-[#ffffff]">
          <table className="workspace-table record-grid w-full">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-[#e0e0e0] bg-[#fafafc]">
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="py-2.5 px-3 text-left font-semibold text-xs text-[#555] border-r border-[#f0f0f0] select-none"
                    >
                      {header.isPlaceholder ? null : (
                        <button
                          type="button"
                          disabled={!header.column.getCanSort()}
                          onClick={header.column.getToggleSortingHandler()}
                          className="flex items-center gap-1 text-inherit font-inherit"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getIsSorted() === "asc"
                            ? " ↑"
                            : header.column.getIsSorted() === "desc"
                            ? " ↓"
                            : ""}
                        </button>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={columns.length} className="py-16 text-center">
                    <div className="flex flex-col items-center justify-center gap-2 text-[#7a7a7a] text-xs">
                      <Loader2 className="size-5 animate-spin text-[#0066cc]" />
                      <span>Loading workspace records…</span>
                    </div>
                  </td>
                </tr>
              ) : table.getRowModel().rows.length ? (
                table.getRowModel().rows.map((row) => {
                  const isSelected = row.original.id === selectedRecordId
                  return (
                    <tr
                      key={row.id}
                      className={`border-b border-[#f0f0f0] cursor-pointer transition-colors ${
                        isSelected ? "bg-[#eaf3fc]" : "hover:bg-[#fafafc]"
                      }`}
                      onClick={() => onSelectRecord(row.original.id)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="py-2 px-3 text-xs border-r border-[#f0f0f0]">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={columns.length} className="py-16 text-center">
                    <div className="flex flex-col items-center justify-center gap-2 text-[#7a7a7a] text-xs">
                      <Database className="size-6 text-[#cccccc]" />
                      <span className="font-medium text-[#1d1d1f]">No matching records</span>
                      <p className="text-[11px] text-[#7a7a7a]">
                        Try clearing search terms or changing your layer filter.
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Pagination */}
        <div className="workspace-table-footer flex items-center justify-between px-4 py-2.5 border-t border-[#e0e0e0] bg-[#fafafc] text-xs text-[#7a7a7a]">
          <div className="flex items-center gap-2">
            <span>
              Showing {recordsData.records.length} of {recordsData.total} records
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={filters.page <= 1}
              onClick={() => onFiltersChange({ page: filters.page - 1 })}
              className="p-1 rounded border border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] disabled:opacity-40"
              aria-label="Previous page"
            >
              <ChevronLeft className="size-3.5" />
            </button>
            <span className="font-mono text-[11px]">
              Page {filters.page} of {Math.max(recordsData.pages, 1)}
            </span>
            <button
              type="button"
              disabled={filters.page >= recordsData.pages}
              onClick={() => onFiltersChange({ page: filters.page + 1 })}
              className="p-1 rounded border border-[#e0e0e0] bg-[#ffffff] hover:bg-[#fafafc] disabled:opacity-40"
              aria-label="Next page"
            >
              <ChevronRight className="size-3.5" />
            </button>
          </div>
        </div>
      </section>

      {/* Record details drawer */}
      {selectedRecord && (
        <RecordEditor
          record={selectedRecord}
          member={selectedMember}
          icons={icons}
          workspaceId={workspaceId}
          onClose={() => onSelectRecord(null)}
          onMemberSave={onMemberUpdate}
          onRecordSaved={onRecordsRefresh}
          onDirtyChange={onDirtyChange}
          onSwitchToMap={onSwitchToMap}
        />
      )}
    </div>
  )
}
