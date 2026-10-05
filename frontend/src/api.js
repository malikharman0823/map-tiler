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

export async function deleteDataset(datasetId) {
  const response = await client.delete(
    `/datasets/${encodeURIComponent(datasetId)}`,
  )
  return response.data.data
}

export function datasetTileUrl(datasetId) {
  return `${API_URL}/datasets/${encodeURIComponent(datasetId)}/tiles/{z}/{x}/{y}.png`
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
