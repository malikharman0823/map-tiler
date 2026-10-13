import React, { useEffect, useState } from "react"
import { ChevronsUpDown } from "lucide-react"

function coordinateText(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(6) : "—"
}

export default function IconPointForm({
  coordinate,
  initialDescription = "",
  initialIconKey = "",
  icons = [],
  submitLabel = "Save Point",
  title = "CREATE ICON POINT",
  onCancel,
  onSubmit,
}) {
  const [description, setDescription] = useState(initialDescription || "")
  const [iconKey, setIconKey] = useState(initialIconKey || "")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setDescription(initialDescription || "")
    setIconKey(initialIconKey || "")
  }, [initialDescription, initialIconKey, coordinate])

  async function submit(event) {
    event.preventDefault()
    if (!coordinate) return
    setSubmitting(true)
    try {
      await onSubmit({
        description: description.trim() || null,
        icon_key: iconKey || null,
      })
    } finally {
      setSubmitting(false)
    }
  }

  if (!coordinate) return null

  return (
    <form className="space-y-3" onSubmit={submit}>
      <p className="text-[11px] font-semibold text-ink">{title}</p>
      
      <div className="flex justify-between items-center text-xs">
         <span className="text-muted">Lat: <span className="text-ink font-mono">{coordinateText(coordinate.latitude)}</span></span>
         <span className="text-muted">Lng: <span className="text-ink font-mono">{coordinateText(coordinate.longitude)}</span></span>
      </div>

      {icons.length > 0 && (
        <div className="mt-2 space-y-1">
          <label className="block text-[11px] text-muted">Select Icon</label>
          <div className="relative">
            <select 
              value={iconKey || "default"} 
              onChange={(e) => setIconKey(e.target.value === "default" ? "" : e.target.value)}
              className="w-full bg-white border border-[#c0c0c0] rounded-md py-1.5 px-3 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-[#808080] appearance-none pr-8 cursor-pointer"
            >
              <option value="default">Default icon</option>
              {icons.map((ic) => (
                <option key={ic} value={ic}>{ic}</option>
              ))}
            </select>
            <ChevronsUpDown className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted pointer-events-none size-4" />
          </div>
        </div>
      )}

      <div className="mt-2 space-y-1">
        <label className="block text-[11px] text-muted">
          Description
        </label>
        <input 
          className="w-full bg-white border border-[#c0c0c0] rounded-md py-1.5 px-3 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-[#808080] placeholder:text-muted/60" 
          maxLength="500" 
          autoFocus 
          placeholder="Main entrance" 
          value={description} 
          onChange={(event) => setDescription(event.target.value)} 
        />
      </div>
      
      <div className="grid grid-cols-2 gap-2 mt-4 pt-1">
        <button type="button" disabled={submitting} onClick={onCancel} className="px-3 py-1.5 text-xs font-medium rounded border border-hairline hover:bg-pearl text-ink transition-colors disabled:opacity-50">Cancel</button>
        <button type="submit" disabled={submitting} className="px-3 py-1.5 text-xs font-medium rounded bg-ink hover:bg-[#202020] text-white transition-colors disabled:opacity-50 shadow-sm">{submitting ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  )
}
