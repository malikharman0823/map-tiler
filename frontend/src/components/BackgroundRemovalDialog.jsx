import React, { useEffect, useRef, useState } from "react"
import {
  AlertCircle,
  Check,
  Eye,
  Loader2,
  RefreshCw,
  Sliders,
  Sparkles,
  Undo2,
  X,
} from "lucide-react"

import {
  applyBackgroundRemoval,
  getBackgroundRemoval,
  previewBackgroundRemoval,
  readableApiError,
  resetBackgroundRemoval,
} from "../api"

const COLOR_PRESETS = [
  { label: "White", value: "#ffffff" },
  { label: "Off-White", value: "#f8f9fa" },
  { label: "Parchment", value: "#faf7ee" },
  { label: "Blueprint", value: "#1e3a8a" },
]

export default function BackgroundRemovalDialog({
  open,
  datasetId,
  datasetName = "Raster Layer",
  onClose,
  onApplied,
}) {
  const [enabled, setEnabled] = useState(false)
  const [color, setColor] = useState("#ffffff")
  const [threshold, setThreshold] = useState(30)
  const [edgeSoftness, setEdgeSoftness] = useState(10)

  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [activeTab, setActiveTab] = useState("processed") // 'processed' | 'original'
  const [error, setError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  const previewDebounceRef = useRef(null)

  // Load initial status when opened
  useEffect(() => {
    if (!open || !datasetId) return
    let active = true
    setLoading(true)
    setError(null)
    setSuccessMessage(null)

    getBackgroundRemoval(datasetId)
      .then((data) => {
        if (!active) return
        setEnabled(Boolean(data.enabled))
        if (data.color) setColor(data.color)
        if (typeof data.threshold === "number") setThreshold(data.threshold)
        if (typeof data.edge_softness === "number") setEdgeSoftness(data.edge_softness)
        setLoading(false)
        // Auto-fetch preview
        loadPreview(data.color || "#ffffff", data.threshold ?? 30, data.edge_softness ?? 10)
      })
      .catch((err) => {
        if (!active) return
        setLoading(false)
        // Fallback default
        loadPreview("#ffffff", 30, 10)
      })

    return () => {
      active = false
      if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
    }
  }, [open, datasetId])

  function loadPreview(targetColor, targetThresh, targetSoft) {
    if (!datasetId) return
    setPreviewing(true)
    setError(null)

    previewBackgroundRemoval(datasetId, {
      color: targetColor,
      threshold: targetThresh,
      edgeSoftness: targetSoft,
    })
      .then((res) => {
        setPreviewData(res)
        setPreviewing(false)
      })
      .catch((err) => {
        setError(readableApiError(err, "Failed to generate preview."))
        setPreviewing(false)
      })
  }

  function handleColorChange(newColor) {
    setColor(newColor)
    setSuccessMessage(null)
    if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
    previewDebounceRef.current = setTimeout(() => {
      loadPreview(newColor, threshold, edgeSoftness)
    }, 300)
  }

  function handleThresholdChange(newThresh) {
    setThreshold(newThresh)
    setSuccessMessage(null)
    if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
    previewDebounceRef.current = setTimeout(() => {
      loadPreview(color, newThresh, edgeSoftness)
    }, 250)
  }

  function handleSoftnessChange(newSoft) {
    setEdgeSoftness(newSoft)
    setSuccessMessage(null)
    if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
    previewDebounceRef.current = setTimeout(() => {
      loadPreview(color, threshold, newSoft)
    }, 250)
  }

  async function handleApply() {
    if (!datasetId || processing) return
    setProcessing(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const res = await applyBackgroundRemoval(datasetId, {
        color,
        threshold,
        edgeSoftness,
      })
      setEnabled(true)
      setProcessing(false)
      setSuccessMessage("Background removal applied to map layer.")
      if (onApplied) onApplied(res)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to apply background removal."))
    }
  }

  async function handleReset() {
    if (!datasetId || processing) return
    setProcessing(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const res = await resetBackgroundRemoval(datasetId)
      setEnabled(false)
      setProcessing(false)
      setSuccessMessage("Original raster restored.")
      if (onApplied) onApplied(res)
      loadPreview(color, threshold, edgeSoftness)
    } catch (err) {
      setProcessing(false)
      setError(readableApiError(err, "Failed to reset background removal."))
    }
  }

  if (!open) return null

  return (
    <div className="bg-removal-backdrop" role="presentation">
      <div className="bg-removal-modal" role="dialog" aria-modal="true" aria-labelledby="bg-removal-title">
        {/* Header */}
        <div className="bg-removal-header">
          <div className="flex items-center gap-2">
            <span className="bg-removal-icon">
              <Sparkles />
            </span>
            <div>
              <h2 id="bg-removal-title" className="text-base font-bold text-gray-900 leading-tight">
                Remove Floor Plan Background
              </h2>
              <p className="text-xs text-gray-500">{datasetName}</p>
            </div>
          </div>
          <button
            type="button"
            className="bg-removal-close"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X />
          </button>
        </div>

        {/* Status / Alert Banners */}
        {error && (
          <div className="bg-removal-alert is-error">
            <AlertCircle />
            <div>
              <strong>{error.message}</strong>
              <span>{error.details}</span>
            </div>
          </div>
        )}
        {successMessage && (
          <div className="bg-removal-alert is-success">
            <Check />
            <div>
              <strong>Success</strong>
              <span>{successMessage}</span>
            </div>
          </div>
        )}

        {/* Content Body */}
        {loading ? (
          <div className="bg-removal-loading">
            <Loader2 className="animate-spin" />
            <span>Loading raster properties…</span>
          </div>
        ) : (
          <div className="bg-removal-grid">
            {/* Left Column: Controls */}
            <div className="bg-removal-controls">
              {/* Enable / Status Toggle */}
              <div className="bg-removal-section bg-gray-50/80 p-3 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-semibold text-gray-900">Background Transparency</span>
                    <p className="text-[11px] text-gray-500">
                      {enabled ? "Active on map layer" : "Disabled (showing original raster)"}
                    </p>
                  </div>
                  <label className="bg-removal-switch" title="Toggle background removal">
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => {
                        if (e.target.checked) {
                          handleApply()
                        } else {
                          handleReset()
                        }
                      }}
                      disabled={processing}
                    />
                    <span className="slider round" />
                  </label>
                </div>
              </div>

              {/* Background Color Picker */}
              <div className="bg-removal-section">
                <label className="bg-removal-label">
                  <span>Background Color to Remove</span>
                  <span className="text-xs font-mono text-gray-500 uppercase">{color}</span>
                </label>
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="color"
                    value={color}
                    onChange={(e) => handleColorChange(e.target.value)}
                    className="bg-removal-color-input"
                    title="Pick background color"
                  />
                  <input
                    type="text"
                    value={color}
                    onChange={(e) => handleColorChange(e.target.value)}
                    className="bg-removal-hex-input"
                    placeholder="#ffffff"
                    maxLength={7}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {COLOR_PRESETS.map((preset) => (
                    <button
                      key={preset.value}
                      type="button"
                      className={`bg-removal-swatch-btn ${color.toLowerCase() === preset.value.toLowerCase() ? "is-active" : ""}`}
                      onClick={() => handleColorChange(preset.value)}
                    >
                      <span className="swatch-circle" style={{ backgroundColor: preset.value }} />
                      <span>{preset.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Threshold Slider */}
              <div className="bg-removal-section">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="bg-removal-label mb-0">
                    <span>Background Threshold</span>
                  </label>
                  <span className="text-xs font-semibold text-blue-600">{threshold}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={threshold}
                  onChange={(e) => handleThresholdChange(Number(e.target.value))}
                  className="bg-removal-slider"
                />
                <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
                  <span>Strict (Exact color)</span>
                  <span>Lenient (Off-white / scans)</span>
                </div>
              </div>

              {/* Edge Softness Slider (Antialiasing) */}
              <div className="bg-removal-section">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="bg-removal-label mb-0">
                    <span>Edge Softness (Antialiasing)</span>
                  </label>
                  <span className="text-xs font-semibold text-blue-600">{edgeSoftness}px</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="40"
                  step="1"
                  value={edgeSoftness}
                  onChange={(e) => handleSoftnessChange(Number(e.target.value))}
                  className="bg-removal-slider"
                />
                <p className="text-[10px] text-gray-400 mt-0.5">
                  Preserves fine architectural lines and antialiased drawings without harsh pixelation.
                </p>
              </div>
            </div>

            {/* Right Column: Visual Preview */}
            <div className="bg-removal-preview-wrap">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5 text-gray-500" />
                  <span>Preview</span>
                  {previewing && <Loader2 className="w-3 h-3 animate-spin text-blue-600" />}
                </span>
                <div className="bg-removal-tab-group">
                  <button
                    type="button"
                    className={`bg-removal-tab ${activeTab === "processed" ? "is-active" : ""}`}
                    onClick={() => setActiveTab("processed")}
                  >
                    Transparent
                  </button>
                  <button
                    type="button"
                    className={`bg-removal-tab ${activeTab === "original" ? "is-active" : ""}`}
                    onClick={() => setActiveTab("original")}
                  >
                    Original
                  </button>
                </div>
              </div>

              {/* Preview Stage with Checkerboard background */}
              <div className="bg-removal-stage">
                {activeTab === "processed" ? (
                  previewData?.preview_data_url ? (
                    <img
                      src={previewData.preview_data_url}
                      alt="Transparent preview"
                      className="bg-removal-stage-img"
                    />
                  ) : (
                    <div className="bg-removal-stage-placeholder">
                      {previewing ? <Loader2 className="animate-spin" /> : <span>No preview available</span>}
                    </div>
                  )
                ) : (
                  previewData?.original_data_url ? (
                    <img
                      src={previewData.original_data_url}
                      alt="Original preview"
                      className="bg-removal-stage-img"
                    />
                  ) : (
                    <div className="bg-removal-stage-placeholder">
                      {previewing ? <Loader2 className="animate-spin" /> : <span>No preview available</span>}
                    </div>
                  )
                )}
                <div className="bg-removal-stage-badge">
                  {activeTab === "processed" ? "Checkerboard = Transparent" : "Original Raster"}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="bg-removal-footer">
          <button
            type="button"
            className="bg-removal-btn-reset"
            onClick={handleReset}
            disabled={processing || loading}
            title="Restore original raster and disable background removal"
          >
            <Undo2 className="w-3.5 h-3.5" />
            <span>Reset to Original</span>
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="bg-removal-btn-cancel"
              onClick={onClose}
              disabled={processing}
            >
              Close
            </button>
            <button
              type="button"
              className="bg-removal-btn-apply"
              onClick={handleApply}
              disabled={processing || loading}
            >
              {processing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Processing Tiles…</span>
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  <span>Apply to Layer</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
