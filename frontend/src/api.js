import axios from "axios"

function requiredSetting(name) {
  const value = import.meta.env[name]
  if (!value) throw new Error(`Missing required frontend setting: ${name}`)
  return value
}

export const API_URL = requiredSetting("VITE_API_URL").replace(/\/$/, "")
export const BASEMAP_TILE_URL = requiredSetting("VITE_BASEMAP_TILE_URL")
export const BASEMAP_ATTRIBUTION = requiredSetting("VITE_BASEMAP_ATTRIBUTION")

export const SESSION_STORAGE_KEY = "maptiler_active_session_id"

export function getActiveSessionId() {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY) || sessionStorage.getItem(SESSION_STORAGE_KEY) || null
  } catch {
    return null
  }
}

export function setActiveSessionId(sessionId) {
  try {
    if (sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId)
      sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId)
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY)
      sessionStorage.removeItem(SESSION_STORAGE_KEY)
    }
  } catch {
    // Local storage access error fallback
  }
}

export function clearActiveSessionId() {
  setActiveSessionId(null)
}

const client = axios.create({ baseURL: API_URL, timeout: 30_000 })

client.interceptors.request.use((config) => {
  const sid = getActiveSessionId()
  if (sid) {
    config.headers["X-Session-ID"] = sid
  }
  return config
})

client.interceptors.response.use(
  (response) => {
    const returnedSid = response.headers?.["x-session-id"]
    if (returnedSid && returnedSid !== getActiveSessionId()) {
      setActiveSessionId(returnedSid)
    }
    return response
  },
  (error) => {
    const status = error.response?.status
    const code = error.response?.data?.error?.code
    if (status === 404 && code === "SESSION_NOT_FOUND") {
      clearActiveSessionId()
    }
    return Promise.reject(error)
  }
)

export async function createSession() {
  const response = await client.post("/sessions")
  const data = response.data.data
  if (data?.session_id) {
    setActiveSessionId(data.session_id)
  }
  return data
}

export async function getSession(sessionId) {
  const sid = sessionId || getActiveSessionId()
  if (!sid) return null
  const response = await client.get(`/sessions/${encodeURIComponent(sid)}`)
  return response.data.data
}

export async function endSession(sessionId) {
  const sid = sessionId || getActiveSessionId()
  if (!sid) return true
  try {
    await client.post(`/sessions/${encodeURIComponent(sid)}/end`)
  } finally {
    clearActiveSessionId()
  }
  return true
}

export async function getSessionMapConfig(sessionId) {
  const sid = sessionId || getActiveSessionId()
  if (!sid) return null
  const response = await client.get(`/sessions/${encodeURIComponent(sid)}/map-config`)
  return response.data.data
}

export async function saveSessionMapConfig(sessionId, configuration) {
  const sid = sessionId || getActiveSessionId()
  if (!sid) return null
  const response = await client.put(`/sessions/${encodeURIComponent(sid)}/map-config`, configuration)
  return response.data.data
}

export async function ensureActiveSession() {
  const existing = getActiveSessionId()
  if (existing) {
    try {
      const info = await getSession(existing)
      if (info && info.session_id) {
        return info.session_id
      }
    } catch {
      clearActiveSessionId()
    }
  }
  const created = await createSession()
  return created.session_id
}

export async function listDatasets(signal) {
  const response = await client.get("/datasets", { signal })
  return response.data.data.datasets
}

export async function getDataset(datasetId, signal) {
  const response = await client.get(`/datasets/${encodeURIComponent(datasetId)}`, {
    signal,
  })
  return response.data.data
}

export async function uploadDataset(file, onUploadProgress) {
  const body = new FormData()
  body.append("file", file)
  const response = await client.post("/upload", body, {
    onUploadProgress,
    timeout: 10 * 60_000,
  })
  return response.data.data
}

export async function importDatasetZip(file, onUploadProgress) {
  const body = new FormData()
  body.append("file", file)
  const response = await client.post("/datasets/import-zip", body, {
    onUploadProgress,
    timeout: 10 * 60_000,
  })
  return response.data.data
}

export async function getPbfPreview(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/pbf-preview`,
    { signal, timeout: 10 * 60_000 },
  )
  return response.data.data
}

export async function getVectorPreview(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/vector-preview`,
    { signal, timeout: 10 * 60_000 },
  )
  return response.data.data
}

export async function deleteDataset(datasetId) {
  const response = await client.delete(
    `/datasets/${encodeURIComponent(datasetId)}`,
  )
  return response.data.data
}

export function datasetTileUrl(datasetId, template) {
  const sid = getActiveSessionId()
  const sessionQuery = sid ? `?session_id=${encodeURIComponent(sid)}` : ""
  if (template) {
    const base = `${API_URL}${template.startsWith("/") ? "" : "/"}${template}`
    return sid ? `${base}${base.includes("?") ? "&" : "?"}session_id=${encodeURIComponent(sid)}` : base
  }
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/tiles/{z}/{x}/{y}.png${sessionQuery}`
}

export function mbtilesTileUrl(datasetId) {
  const sid = getActiveSessionId()
  const sessionQuery = sid ? `?session_id=${encodeURIComponent(sid)}` : ""
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/mbtiles/{z}/{x}/{y}${sessionQuery}`
}

export function datasetSourceImageUrl(datasetId) {
  const sid = getActiveSessionId()
  const sessionQuery = sid ? `&session_id=${encodeURIComponent(sid)}` : ""
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/source-image?t=${Date.now()}${sessionQuery}`
}

export async function listControlPoints(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/control-points`,
    { signal },
  )
  return response.data.data.points
}

export async function createControlPoint(datasetId, point) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/control-points`,
    { dataset_id: datasetId, ...point },
  )
  return response.data.data
}

export async function updateControlPoint(controlPointId, point) {
  const response = await client.put(
    `/control-points/${encodeURIComponent(controlPointId)}`,
    point,
  )
  return response.data.data
}

export async function removeControlPoint(controlPointId) {
  const response = await client.delete(
    `/control-points/${encodeURIComponent(controlPointId)}`,
  )
  return response.data.data
}

export async function georeferenceDataset(datasetId, action = "calculate") {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/georeference`,
    {
      action,
      transformation: "auto",
      output_format: "tif",
      target_crs: "EPSG:4326",
    },
    { timeout: 10 * 60_000 },
  )
  return response.data.data
}

export async function getGeoreferenceConfig(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/georeference`,
    { signal },
  )
  return response.data.data.configuration
}

export async function listIconPoints(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/icon-points`,
    { signal },
  )
  return response.data.data.points
}

export async function createIconPoint(datasetId, point) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/icon-points`,
    point,
  )
  return response.data.data
}

export async function updateIconPoint(iconPointId, point) {
  const response = await client.put(
    `/icon-points/${encodeURIComponent(iconPointId)}`,
    point,
  )
  return response.data.data
}

export async function removeIconPoint(iconPointId) {
  const response = await client.delete(
    `/icon-points/${encodeURIComponent(iconPointId)}`,
  )
  return response.data.data
}

export async function getMapProject(datasetId, signal) {
  const response = await client.get(`/datasets/${encodeURIComponent(datasetId)}/project`, { signal })
  return response.data
}

export async function updateMapProject(datasetId, name, configuration) {
  const response = await client.put(
    `/datasets/${encodeURIComponent(datasetId)}/project`,
    { name, configuration }
  )
  return response.data
}

export async function getWorkspace(datasetId, signal) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/workspace`,
    { signal },
  )
  return response.data.data
}

export async function attachWorkspaceDataset(primaryDatasetId, datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(primaryDatasetId)}/workspace/members`,
    { dataset_id: datasetId },
  )
  return response.data.data
}

export async function patchWorkspaceMember(primaryDatasetId, datasetId, patch) {
  const response = await client.patch(
    `/datasets/${encodeURIComponent(primaryDatasetId)}/workspace/members/${encodeURIComponent(datasetId)}`,
    patch,
  )
  return response.data.data
}

export async function detachWorkspaceDataset(primaryDatasetId, datasetId) {
  const response = await client.delete(
    `/datasets/${encodeURIComponent(primaryDatasetId)}/workspace/members/${encodeURIComponent(datasetId)}`,
  )
  return response.data.data
}

export async function patchWorkspaceState(primaryDatasetId, patch) {
  const response = await client.patch(
    `/datasets/${encodeURIComponent(primaryDatasetId)}/workspace/state`,
    patch,
  )
  return response.data.data
}

export async function getWorkspaceRecords(primaryDatasetId, options = {}, signal) {
  const params = new URLSearchParams()
  const values = {
    page: options.page || 1,
    page_size: options.pageSize || 25,
    search: options.search,
    member_dataset_id: options.datasetId,
    kind: options.kind,
    status: options.status,
    sort: options.sort || "name",
    order: options.order || "asc",
  }
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value))
    }
  })
  const response = await client.get(
    `/datasets/${encodeURIComponent(primaryDatasetId)}/workspace/records?${params}`,
    { signal },
  )
  return response.data.data
}

export async function importMapProject(file, onUploadProgress) {
  const body = new FormData()
  body.append("file", file)
  const response = await client.post("/map-projects/import", body, {
    onUploadProgress,
    timeout: 10 * 60_000,
  })
  return response.data
}

export async function importProjectFolder(files, onUploadProgress) {
  const body = new FormData()
  for (const file of files) {
    body.append("files", file, file.name)
    body.append("paths", file.webkitRelativePath || file.name)
  }
  const response = await client.post("/map-projects/import-folder", body, {
    onUploadProgress,
    timeout: 10 * 60_000,
  })
  return response.data
}

function safeDownloadStem(value) {
  const stem = String(value || "map_project")
    .replace(/[^A-Za-z0-9._-]+/g, "_")
    .replace(/^[._-]+|[._-]+$/g, "")
    .slice(0, 80)
  return stem || "map_project"
}

function responseFilename(disposition) {
  if (!disposition) return null
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      return encoded
    }
  }
  return disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]?.trim()
    || null
}

function safeDownloadFilename(value, fallback) {
  const basename = String(value || "").replace(/\\/g, "/").split("/").pop()
  const safe = basename?.replace(/[<>:"/\\|?*\u0000-\u001F]/g, "_").trim()
  return safe && safe !== "." && safe !== ".." ? safe : fallback
}

export async function downloadProjectExport(datasetId, projectName) {
  let response
  try {
    response = await client.get(
      `/datasets/${encodeURIComponent(datasetId)}/export`,
      { responseType: "blob", timeout: 10 * 60_000 },
    )
  } catch (error) {
    if (error.response?.data instanceof Blob) {
      try {
        error.response.data = JSON.parse(await error.response.data.text())
      } catch {
        // Keep the original Blob when the server did not return JSON.
      }
    }
    throw error
  }

  if (!response.data || (response.data instanceof Blob && response.data.size === 0)) {
    throw new Error("The exported file is empty or invalid.")
  }

  const fallback = `${safeDownloadStem(projectName)}.zip`
  const filename = safeDownloadFilename(
    responseFilename(response.headers.get?.("content-disposition") || response.headers["content-disposition"]),
    fallback,
  )
  const objectUrl = URL.createObjectURL(response.data)
  try {
    const link = document.createElement("a")
    link.href = objectUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
  }
  return filename
}



export async function listIcons(signal) {
  const response = await client.get(`/icons`, { signal })
  return response.data.icons
}

export async function processRasterDataset(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/process-raster`,
    { target_crs: "EPSG:3857" },
    { timeout: 10 * 60_000 },
  )
  return response.data.data
}

export async function generateDatasetTiles(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/generate-tiles`,
    { min_zoom: 0, max_zoom: 22 },
    { timeout: 10 * 60_000 },
  )
  return response.data.data
}

export async function getBackgroundRemoval(datasetId) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/background-removal`,
  )
  return response.data.data
}

export async function previewBackgroundRemoval(datasetId, { color = "#ffffff", threshold = 30, edgeSoftness = 10 } = {}) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/background-removal`,
    {
      action: "preview",
      color,
      threshold,
      edge_softness: edgeSoftness,
    },
  )
  return response.data.data
}

export async function applyBackgroundRemoval(datasetId, { color = "#ffffff", threshold = 30, edgeSoftness = 10 } = {}) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/background-removal`,
    {
      action: "apply",
      color,
      threshold,
      edge_softness: edgeSoftness,
    },
  )
  return response.data.data
}

export async function resetBackgroundRemoval(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/background-removal`,
    {
      action: "reset",
    },
  )
  return response.data.data
}

export async function getRasterTransform(datasetId) {
  const response = await client.get(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
  )
  return response.data.data
}

export async function previewRasterTransform(datasetId, { corners, mode = "free", rotationAngle = null, lockAspectRatio = false } = {}) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
    {
      action: "preview",
      mode,
      corners,
      rotation_angle: rotationAngle,
      lock_aspect_ratio: lockAspectRatio,
    },
  )
  return response.data.data
}

export async function applyRasterTransform(datasetId, { corners, mode = "free", rotationAngle = null, lockAspectRatio = false, resampling = "bilinear" } = {}) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
    {
      action: "apply",
      mode,
      corners,
      rotation_angle: rotationAngle,
      lock_aspect_ratio: lockAspectRatio,
      resampling,
    },
  )
  return response.data.data
}

export async function undoRasterTransform(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
    { action: "undo" },
  )
  return response.data.data
}

export async function redoRasterTransform(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
    { action: "redo" },
  )
  return response.data.data
}

export async function resetRasterTransform(datasetId) {
  const response = await client.post(
    `/datasets/${encodeURIComponent(datasetId)}/transform`,
    { action: "reset" },
  )
  return response.data.data
}

export function readableApiError(error, fallbackMessage) {
  const apiError = error.response?.data?.error
  if (apiError) {
    return {
      message: apiError.message || fallbackMessage,
      details: apiError.details || "Please try again.",
    }
  }
  if (!error.response) {
    return {
      message: "Unable to reach the server.",
      details: "Check that the backend is running, then try again.",
    }
  }
  return {
    message: fallbackMessage,
    details: "The request could not be completed.",
  }
}
