export function safeWorkspaceReturn(value, datasetId) {
  const fallback = `/datasets/${datasetId}/workspace?view=database`
  if (!value || !value.startsWith("/datasets/") || !value.includes("/workspace")) return fallback
  if (value.startsWith("//") || value.includes("://")) return fallback
  return value
}
