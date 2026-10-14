import { useCallback, useEffect, useRef, useState } from "react"

import {
  attachWorkspaceDataset,
  detachWorkspaceDataset,
  getWorkspace,
  getWorkspaceRecords,
  patchWorkspaceMember,
  patchWorkspaceState,
  readableApiError,
} from "../api"


const DEFAULT_FILTERS = {
  page: 1,
  pageSize: 25,
  search: "",
  datasetId: "",
  kind: "",
  status: "",
  sort: "name",
  order: "asc",
}

export default function useWorkspace(primaryDatasetId) {
  const [manifest, setManifest] = useState(null)
  const [records, setRecords] = useState({ records: [], total: 0, page: 1, page_size: 25, pages: 0 })
  const [mapRecords, setMapRecords] = useState([])
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS)
  const [loading, setLoading] = useState(true)
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [saveState, setSaveState] = useState("saved")
  const [selectedRecordId, setSelectedRecordId] = useState(null)
  const mutationChainRef = useRef(Promise.resolve())

  const loadManifest = useCallback(async (signal) => {
    const next = await getWorkspace(primaryDatasetId, signal)
    setManifest(next)
    return next
  }, [primaryDatasetId])

  const refreshRecords = useCallback(async (signal) => {
    setRecordsLoading(true)
    try {
      const next = await getWorkspaceRecords(primaryDatasetId, filters, signal)
      setRecords(next)
      return next
    } catch (requestError) {
      if (requestError.code !== "ERR_CANCELED") {
        setError(readableApiError(requestError, "Unable to load workspace records."))
      }
      return null
    } finally {
      setRecordsLoading(false)
    }
  }, [filters, primaryDatasetId])

  const refreshMapRecords = useCallback(async (signal) => {
    const collected = []
    let page = 1
    let pages = 1
    do {
      const response = await getWorkspaceRecords(
        primaryDatasetId,
        { page, pageSize: 100, sort: "name", order: "asc" },
        signal,
      )
      collected.push(...response.records)
      pages = response.pages
      page += 1
    } while (page <= pages)
    setMapRecords(collected)
    return collected
  }, [primaryDatasetId])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    loadManifest(controller.signal)
      .catch((requestError) => {
        if (requestError.code !== "ERR_CANCELED") {
          setError(readableApiError(requestError, "Unable to load the dataset workspace."))
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [loadManifest])

  useEffect(() => {
    if (!manifest) return undefined
    const controller = new AbortController()
    refreshRecords(controller.signal)
    return () => controller.abort()
  }, [manifest?.id, refreshRecords])

  useEffect(() => {
    if (!manifest) return undefined
    const controller = new AbortController()
    refreshMapRecords(controller.signal).catch((requestError) => {
      if (requestError.code !== "ERR_CANCELED") {
        setError(readableApiError(requestError, "Unable to load workspace map points."))
      }
    })
    return () => controller.abort()
  }, [manifest?.id, refreshMapRecords])

  const setFilters = useCallback((patch) => {
    setFiltersState((current) => ({
      ...current,
      ...patch,
      page: Object.prototype.hasOwnProperty.call(patch, "page") ? patch.page : 1,
    }))
  }, [])

  const runMutation = useCallback((mutation, fallbackMessage) => {
    setSaveState("saving")
    const operation = mutationChainRef.current
      .catch(() => undefined)
      .then(mutation)
      .then((nextManifest) => {
        if (nextManifest) setManifest(nextManifest)
        setSaveState("saved")
        return Promise.all([refreshRecords(), refreshMapRecords()])
      })
      .catch((requestError) => {
        setSaveState("failed")
        setError(readableApiError(requestError, fallbackMessage))
        throw requestError
      })
    mutationChainRef.current = operation
    return operation
  }, [refreshMapRecords, refreshRecords])

  const updateMember = useCallback((datasetId, patch) => {
    setManifest((current) => {
      if (!current) return current
      return {
        ...current,
        members: current.members.map((member) =>
          member.dataset_id === datasetId ? { ...member, ...patch } : member
        ),
      }
    })
    setSaveState("saving")
    const operation = mutationChainRef.current
      .catch(() => undefined)
      .then(() => patchWorkspaceMember(primaryDatasetId, datasetId, patch))
      .then((nextManifest) => {
        if (nextManifest) setManifest(nextManifest)
        setSaveState("saved")
      })
      .catch((requestError) => {
        setSaveState("failed")
        setError(readableApiError(requestError, "Unable to save the layer settings."))
        throw requestError
      })
    mutationChainRef.current = operation
    return operation
  }, [primaryDatasetId])

  const reorderMembers = useCallback((orderedDatasetIds) => runMutation(async () => {
    let nextManifest = manifest
    for (const [sortOrder, datasetId] of orderedDatasetIds.entries()) {
      const current = manifest?.members.find((member) => member.dataset_id === datasetId)
      if (current?.sort_order !== sortOrder) {
        nextManifest = await patchWorkspaceMember(primaryDatasetId, datasetId, {
          sort_order: sortOrder,
        })
      }
    }
    return nextManifest
  }, "Unable to save the layer order."), [manifest, primaryDatasetId, runMutation])

  const updateState = useCallback((patch) => runMutation(
    () => patchWorkspaceState(primaryDatasetId, patch),
    "Unable to save the workspace view.",
  ), [primaryDatasetId, runMutation])

  const attachDataset = useCallback((datasetId) => runMutation(
    async () => {
      try {
        return await attachWorkspaceDataset(primaryDatasetId, datasetId)
      } catch (requestError) {
        if (requestError?.response?.status === 409) {
          return await getWorkspace(primaryDatasetId)
        }
        throw requestError
      }
    },
    "Unable to attach the dataset.",
  ), [primaryDatasetId, runMutation])

  const detachDataset = useCallback((datasetId) => runMutation(
    () => detachWorkspaceDataset(primaryDatasetId, datasetId),
    "Unable to detach the dataset.",
  ), [primaryDatasetId, runMutation])

  const retrySave = useCallback(() => {
    setError(null)
    setSaveState("saved")
    return loadManifest().then(() => Promise.all([refreshRecords(), refreshMapRecords()]))
  }, [loadManifest, refreshMapRecords, refreshRecords])

  return {
    manifest,
    records,
    mapRecords,
    filters,
    loading,
    recordsLoading,
    error,
    saveState,
    selectedRecordId,
    setSelectedRecordId,
    setFilters,
    setError,
    updateMember,
    reorderMembers,
    updateState,
    attachDataset,
    detachDataset,
    refreshManifest: loadManifest,
    refreshRecords,
    refreshMapRecords,
    retrySave,
  }
}
