import React from "react"
import { Button } from "@/components/ui/button"

function coordinateText(value, digits = 5) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : "—"
}

function CoordinateField({ label, value }) {
  return (
    <label className="grid min-w-0 grid-cols-[auto_1fr] items-center gap-2 text-[12px] text-muted">
      <span>{label}</span>
      <span className="h-9 min-w-0 rounded-lg border border-hairline bg-pearl px-2 py-2 text-right tabular-nums text-ink outline-none">
        {coordinateText(value)}
      </span>
    </label>
  )
}

export default function ControlPointList({
  points,
  draft,
  selectedId,
  onSelect,
  onDelete,
  readOnly = false,
}) {
  return (
    <section className="overflow-hidden rounded-utility border border-hairline bg-white">
      <header className="flex min-h-14 items-center justify-between border-b border-hairline px-5">
        <div>
          <h2 className="text-[13px] font-semibold tracking-[0.08em] text-ink">CONTROL POINTS</h2>
          <p className="mt-0.5 text-[12px] text-muted">Select or remove a paired location</p>
        </div>
        <span className="text-[13px] tabular-nums text-muted">{points.length} / 10</span>
      </header>
      <div className="divide-y divide-hairline">
        {points.length === 0 && !draft && (
          <p className="px-5 py-6 text-[14px] text-muted">Click a distinct location on the source image to begin point 1.</p>
        )}
        {points.map((point, index) => (
          <article
            key={point.id}
            className={`grid cursor-pointer gap-3 px-4 py-3 transition-colors tablet:grid-cols-[36px_1fr_1fr_auto] tablet:items-center${selectedId === point.id ? " bg-[#eaf3ff]" : " hover:bg-pearl"}`}
            onClick={() => onSelect(point.id)}
          >
            <div className="flex items-center gap-2 text-[14px] font-semibold tabular-nums">
              <span className={`h-2.5 w-2.5 rounded-full${selectedId === point.id ? " bg-[#004c99]" : " bg-primary"}`} />
              {index + 1}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <CoordinateField label="x" value={point.image_x} />
              <CoordinateField label="y" value={point.image_y} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <CoordinateField label="lon" value={point.longitude} />
              <CoordinateField label="lat" value={point.latitude} />
            </div>
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 rounded-full px-3 text-[13px] text-muted hover:bg-[#f5f5f7] hover:text-ink"
              disabled={readOnly}
              onClick={(event) => {
                event.stopPropagation()
                onDelete(point.id)
              }}
            >
              Delete
            </Button>
          </article>
        ))}
        {draft && (
          <article className="grid gap-2 bg-[#fff8e6] px-4 py-3 text-[14px] tablet:grid-cols-[36px_1fr] tablet:items-center">
            <span className="font-semibold tabular-nums">{points.length + 1}</span>
            <p className="text-muted">Image: {Math.round(draft.image_x)}, {Math.round(draft.image_y)} · Waiting for a map location</p>
          </article>
        )}
      </div>
    </section>
  )
}
