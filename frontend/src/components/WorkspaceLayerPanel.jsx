import React, { useEffect, useMemo, useState } from "react"
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core"
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import {
  ChevronDown,
  ChevronRight,
  Database,
  GripVertical,
  Image,
  MapPin,
  MoreHorizontal,
  Sparkles,
  Trash2,
  X,
} from "lucide-react"

import BackgroundRemovalDialog from "./BackgroundRemovalDialog"


const SUBLAYER_ICONS = {
  raster: Image,
  control_point: MapPin,
  icon_point: Database,
}

const VISIBILITY_FIELDS = {
  raster: "raster_visible",
  control_point: "control_points_visible",
  icon_point: "icon_points_visible",
}

function LayerCheckbox({ checked, label, onChange }) {
  return (
    <label className="workspace-layer-checkbox" title={`${checked ? "Hide" : "Show"} ${label}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span aria-hidden="true" />
    </label>
  )
}

function SortableMember({
  member,
  selectedDatasetId,
  selectedKind,
  onSelect,
  onUpdate,
  onDetach,
  onOpenBgRemoval,
}) {
  const [expanded, setExpanded] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const sortable = useSortable({ id: member.dataset_id })
  const style = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  }

  return (
    <div
      ref={sortable.setNodeRef}
      style={style}
      className={`workspace-layer-group${sortable.isDragging ? " is-dragging" : ""}`}
    >
      <div className={`workspace-layer-parent${selectedDatasetId === member.dataset_id && !selectedKind ? " is-selected" : ""}`}>
        <button
          type="button"
          className="workspace-layer-disclosure"
          aria-label={`${expanded ? "Collapse" : "Expand"} ${member.name}`}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronDown /> : <ChevronRight />}
        </button>
        <button
          type="button"
          className="workspace-layer-drag"
          aria-label={`Reorder ${member.name}`}
          ref={sortable.setActivatorNodeRef}
          {...sortable.attributes}
          {...sortable.listeners}
        >
          <GripVertical />
        </button>
        <LayerCheckbox
          checked={member.visible}
          label={member.name}
          onChange={(visible) => onUpdate(member.dataset_id, { visible })}
        />
        <button
          type="button"
          className="workspace-layer-title"
          onClick={() => onSelect(member.dataset_id, "")}
        >
          <span>{member.name}</span>
          <small>{member.dataset.georeference_status === "completed" ? "Georeferenced" : "Needs georeferencing"}</small>
        </button>
        <div className="workspace-layer-menu-wrap">
          <button
            type="button"
            className="workspace-layer-menu"
            aria-label={`Actions for ${member.name}`}
            onClick={() => setMenuOpen((value) => !value)}
          >
            <MoreHorizontal />
          </button>
          {menuOpen && (
            <div className="workspace-layer-popover">
              <label>
                <span>Raster opacity</span>
                <strong>{Math.round(member.raster_opacity * 100)}%</strong>
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={Math.round(member.raster_opacity * 100)}
                onChange={(event) => onUpdate(member.dataset_id, {
                  raster_opacity: Number(event.target.value) / 100,
                })}
              />
              <button
                type="button"
                className="workspace-layer-feature-btn"
                onClick={() => {
                  if (onOpenBgRemoval) onOpenBgRemoval(member)
                  setMenuOpen(false)
                }}
              >
                <Sparkles />
                <span>Remove Background</span>
              </button>
              {!member.is_primary && (
                <button
                  type="button"
                  className="workspace-danger-action"
                  onClick={() => onDetach(member)}
                >
                  <Trash2 /> Detach dataset
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {expanded && (
        <div className="workspace-sublayers">
          {member.sublayers.map((sublayer) => {
            const Icon = SUBLAYER_ICONS[sublayer.kind]
            const field = VISIBILITY_FIELDS[sublayer.kind]
            const selected = selectedDatasetId === member.dataset_id && selectedKind === sublayer.kind
            return (
              <div key={sublayer.kind} className={`workspace-sublayer${selected ? " is-selected" : ""}`}>
                <LayerCheckbox
                  checked={member[field]}
                  label={`${member.name} ${sublayer.label}`}
                  onChange={(visible) => onUpdate(member.dataset_id, { [field]: visible })}
                />
                <button type="button" onClick={() => onSelect(member.dataset_id, sublayer.kind)}>
                  <Icon />
                  <span>{sublayer.label}</span>
                  <small>{sublayer.count}</small>
                </button>
                {sublayer.kind === "raster" && (
                  <button
                    type="button"
                    className="workspace-sublayer-tool"
                    title="Remove raster background"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (onOpenBgRemoval) onOpenBgRemoval(member)
                    }}
                  >
                    <Sparkles />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function WorkspaceLayerPanel({
  members = [],
  selectedDatasetId,
  selectedKind,
  onSelect,
  onUpdate,
  onReorder,
  onDetach,
  onClose,
  onLayerChanged,
}) {
  const [bgRemovalMember, setBgRemovalMember] = useState(null)
  const sortedMembers = useMemo(
    () => [...members].sort((a, b) => a.sort_order - b.sort_order),
    [members],
  )
  const [orderedIds, setOrderedIds] = useState(sortedMembers.map((member) => member.dataset_id))
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  useEffect(() => {
    setOrderedIds(sortedMembers.map((member) => member.dataset_id))
  }, [sortedMembers])

  function finishDrag(event) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = orderedIds.indexOf(active.id)
    const newIndex = orderedIds.indexOf(over.id)
    const next = arrayMove(orderedIds, oldIndex, newIndex)
    setOrderedIds(next)
    onReorder(next)
  }

  const memberById = new Map(sortedMembers.map((member) => [member.dataset_id, member]))

  return (
    <aside className="workspace-layer-panel" aria-label="Workspace layers">
      <div className="workspace-panel-header">
        <div>
          <span className="workspace-eyebrow">Layer stack</span>
          <h2>Datasets</h2>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Close layers">
            <X />
          </button>
        )}
      </div>
      <div className="workspace-layer-scroll">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={finishDrag}>
          <SortableContext items={orderedIds} strategy={verticalListSortingStrategy}>
            {orderedIds.map((id) => {
              const member = memberById.get(id)
              return member ? (
                <SortableMember
                  key={id}
                  member={member}
                  selectedDatasetId={selectedDatasetId}
                  selectedKind={selectedKind}
                  onSelect={onSelect}
                  onUpdate={onUpdate}
                  onDetach={onDetach}
                  onOpenBgRemoval={setBgRemovalMember}
                />
              ) : null
            })}
          </SortableContext>
        </DndContext>
      </div>

      {bgRemovalMember && (
        <BackgroundRemovalDialog
          open={Boolean(bgRemovalMember)}
          datasetId={bgRemovalMember.dataset_id}
          datasetName={bgRemovalMember.name}
          onClose={() => setBgRemovalMember(null)}
          onApplied={() => {
            if (onLayerChanged) onLayerChanged()
          }}
        />
      )}
    </aside>
  )
}
