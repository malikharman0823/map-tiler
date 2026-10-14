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

export default function BackgroundRemovalDialog({
  open,
  datasetId,
  datasetName = "Raster Layer",
  isGeoreferenced = true,
  onClose,
  onApplied,
}) {
  const [color, setColor] = useState("#ffffff")
  const [threshold, setThreshold] = useState(30)
  const [edgeSoftness, setEdgeSoftness] = useState(10)

  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [error, setError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  const previewDebounceRef = useRef(null)

  useEffect(() => {
    if (!open || !datasetId) return
    let active = true
    setLoading(true)
    setError(null)
    setSuccessMessage(null)

    getBackgroundRemoval(datasetId)
      .then((data) => {
        if (!active) return
        if (data.color) setColor(data.color)
        if (typeof data.threshold === "number") setThreshold(data.threshold)
        if (typeof data.edge_softness === "number") setEdgeSoftness(data.edge_softness)
        setLoading(false)
        loadPreview(data.color || "#ffffff", data.threshold ?? 30, data.edge_softness ?? 10)
      })
      .catch((err) => {
        if (!active) return
        setLoading(false)
        setError(readableApiError(err, "Failed to load background removal settings."))
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
              {!isGeoreferenced && (
                <div className="bg-removal-alert is-error" style={{ marginBottom: "12px" }}>
                  <AlertCircle />
                  <div>
                    <strong>Layer needs georeferencing</strong>
                    <span>To display transparency on the map tiles, georeference this raster layer first.</span>
                  </div>
                </div>
              )}

              {/* Background Color Picker */}
              <div className="bg-removal-section">
                <label className="bg-removal-label">
                  <span>Background Color to Remove</span>
                  <span className="text-xs font-mono text-gray-500 uppercase">{color}</span>
                </label>
                <div className="flex items-center gap-2">
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
              </div>

              {/* Edge Softness Slider */}
              <div className="bg-removal-section">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="bg-removal-label mb-0">
                    <span>Edge Softness</span>
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
              </div>
            </div>

            {/* Right Column: Visual Preview */}
            <div className="bg-removal-preview-wrap">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5 text-gray-500" />
                  <span>Transparency Preview</span>
                  {previewing && <Loader2 className="w-3 h-3 animate-spin text-blue-600" />}
                </span>
              </div>

              {/* Preview Stage with Checkerboard background */}
              <div className="bg-removal-stage">
                {previewData?.preview_data_url ? (
                  <img
                    src={previewData.preview_data_url}
                    alt="Transparent preview"
                    className="bg-removal-stage-img"
                  />
                ) : (
                  <div className="bg-removal-stage-placeholder">
                    {previewing ? <Loader2 className="animate-spin" /> : <span>No preview available</span>}
                  </div>
                )}
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
