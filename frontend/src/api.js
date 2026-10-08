import axios from "axios"

function requiredSetting(name) {
  const value = import.meta.env[name]
  if (!value) throw new Error(`Missing required frontend setting: ${name}`)
  return value
}

export const API_URL = requiredSetting("VITE_API_URL").replace(/\/$/, "")
export const BASEMAP_TILE_URL = requiredSetting("VITE_BASEMAP_TILE_URL")
export const BASEMAP_ATTRIBUTION = requiredSetting("VITE_BASEMAP_ATTRIBUTION")

const client = axios.create({ baseURL: API_URL, timeout: 30_000 })

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
  if (template) {
    return `${API_URL}${template.startsWith("/") ? "" : "/"}${template}`
  }
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/tiles/{z}/{x}/{y}.png`
}

export function mbtilesTileUrl(datasetId) {
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/mbtiles/{z}/{x}/{y}`
}

export function datasetSourceImageUrl(datasetId) {
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/source-image?t=${Date.now()}`
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

export async function importMapProject(file, onUploadProgress) {
  const body = new FormData()
  body.append("file", file)
  const response = await client.post("/map-projects/import", body, {
    onUploadProgress,
    timeout: 10 * 60_000,
  })
  return response.data
}

export function exportProjectUrl(datasetId, format) {
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/export/${encodeURIComponent(format)}`
}

const EXPORT_EXTENSIONS = {
  mtmap: "mtmap",
  gpkg: "gpkg",
  geojson: "geojson",
  tif: "tif",
  json: "json",
  mbtiles: "mbtiles",
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

export async function downloadProjectExport(datasetId, format, projectName) {
  const normalizedFormat = String(format).toLowerCase()
  const extension = EXPORT_EXTENSIONS[normalizedFormat]
  if (!extension) throw new Error(`Unsupported export format: ${format}`)
  let response
  try {
    response = await client.get(
      `/datasets/${encodeURIComponent(datasetId)}/export/${encodeURIComponent(normalizedFormat)}`,
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

  const fallback = `${safeDownloadStem(projectName)}.${extension}`
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
