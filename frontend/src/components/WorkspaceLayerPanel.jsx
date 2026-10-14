import React, { useEffect, useMemo, useRef, useState } from "react"
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
  Building2,
  ChevronDown,
  ChevronRight,
  Database,
  GripVertical,
  Image,
  MapPin,
  MoreHorizontal,
  Move,
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

function LayerOpacitySlider({ datasetId, opacity, onUpdate }) {
  const safeOpacity = typeof opacity === "number" && Number.isFinite(opacity) ? opacity : 1
  const [localPercent, setLocalPercent] = useState(() => Math.round(safeOpacity * 100))
  const debounceTimerRef = useRef(null)
  const isDraggingRef = useRef(false)

  useEffect(() => {
    if (!isDraggingRef.current) {
      setLocalPercent(Math.round(safeOpacity * 100))
    }
  }, [safeOpacity])

  const commitUpdate = (val) => {
    const floatVal = Math.max(0, Math.min(1, val / 100))
    onUpdate(datasetId, { raster_opacity: floatVal })
  }

  const handleInput = (event) => {
    isDraggingRef.current = true
    const val = Number(event.target.value)
    setLocalPercent(val)
    const floatVal = Math.max(0, Math.min(1, val / 100))

    if (typeof window !== "undefined" && window.__maptiler_setLayerOpacity) {
      window.__maptiler_setLayerOpacity(datasetId, floatVal)
    }

    clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => {
      commitUpdate(val)
      isDraggingRef.current = false
    }, 150)
  }

  const handlePointerUp = () => {
    clearTimeout(debounceTimerRef.current)
    commitUpdate(localPercent)
    isDraggingRef.current = false
  }

  return (
    <div className="workspace-layer-opacity-control" onClick={(e) => e.stopPropagation()}>
      <label>
        <span>Raster opacity</span>
        <strong>{localPercent}%</strong>
      </label>
      <input
        type="range"
        min="0"
        max="100"
        value={localPercent}
        onInput={handleInput}
        onChange={handleInput}
        onPointerUp={handlePointerUp}
        onTouchEnd={handlePointerUp}
        aria-label="Raster opacity"
      />
    </div>
  )
}

function BuildingFloorItem({
  member,
  isActiveFloor,
  onSelectFloor,
  onSelect,
  onUpdate,
  onDetach,
  onOpenBgRemoval,
  onOpenTransform,
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const level = member.floor_level ?? 0
  const badgeLabel = level === -1 ? "B1" : level === 0 ? "G" : `${level}`
  const badgeClass = level < 0 ? "badge-basement" : level === 0 ? "badge-ground" : "badge-upper"

  return (
    <div
      className={`workspace-floor-item ${isActiveFloor ? "is-active" : ""}`}
      onClick={() => {
        if (member.dataset?.georeference_status !== "completed") {
          const returnTo = window.location.pathname + window.location.search
          window.location.href = `/datasets/${member.dataset_id}/georeference?returnTo=${encodeURIComponent(returnTo)}`
        } else {
          if (onSelectFloor) onSelectFloor(level)
          onSelect(member.dataset_id, "raster")
        }
      }}
    >
      <LayerCheckbox
        checked={member.visible && member.raster_visible}
        label={member.floor_label || member.name}
        onChange={(checked) => {
          onUpdate(member.dataset_id, { visible: checked, raster_visible: checked })
        }}
      />
      <span className={`workspace-floor-badge ${badgeClass}`}>{badgeLabel}</span>
      <div className="workspace-floor-info">
        <span className="workspace-floor-name" title={member.floor_label || member.name}>
          {member.floor_label || member.name}
        </span>
        {isActiveFloor && <span className="workspace-floor-active-tag">Active Floor</span>}
      </div>
      <div className="workspace-floor-actions" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="workspace-floor-tool-btn"
          title="Transform raster placement"
          onClick={() => {
            if (onOpenTransform) onOpenTransform(member)
          }}
        >
          <Move />
        </button>
        <div className="workspace-layer-menu-wrap">
          <button
            type="button"
            className="workspace-floor-tool-btn"
            title="More actions"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <MoreHorizontal />
          </button>
          {menuOpen && (
            <div className="workspace-layer-popover">
              <LayerOpacitySlider
                datasetId={member.dataset_id}
                opacity={member.raster_opacity}
                onUpdate={onUpdate}
              />
              <button
                type="button"
                className="workspace-layer-feature-btn"
                onClick={() => {
                  if (onOpenTransform) onOpenTransform(member)
                  setMenuOpen(false)
                }}
              >
                <Move />
                <span>Transform Raster</span>
              </button>
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
              {member.dataset?.georeference_status !== "completed" && (
                <button
                  type="button"
                  className="workspace-layer-feature-btn text-amber-600"
                  onClick={() => {
                    const returnTo = window.location.pathname + window.location.search
                    window.location.href = `/datasets/${member.dataset_id}/georeference?returnTo=${encodeURIComponent(returnTo)}`
                  }}
                >
                  <MapPin />
                  <span>Georeference Floor</span>
                </button>
              )}
              {!member.is_primary && (
                <button
                  type="button"
                  className="workspace-danger-action"
                  onClick={() => onDetach(member)}
                >
                  <Trash2 /> Detach floor
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BuildingGroup({
  buildingName,
  floors,
  activeFloorLevel,
  onSelectFloor,
  onSelect,
  onUpdate,
  onDetach,
  onOpenBgRemoval,
  onOpenTransform,
}) {
  const [expanded, setExpanded] = useState(true)
  const isGeoreferenced = floors.some(
    (f) => f.dataset?.georeference_status === "completed" || f.dataset?.map_layer
  )
  const allVisible = floors.some((f) => f.visible)
  const primaryFloor = floors.find((f) => f.floor_level === 0) || floors[0]

  const sortedFloors = useMemo(() => {
    return [...floors].sort((a, b) => (a.floor_level ?? 0) - (b.floor_level ?? 0))
  }, [floors])

  function toggleMasterVisibility(checked) {
    floors.forEach((f) => {
      onUpdate(f.dataset_id, { visible: checked })
    })
  }

  return (
    <div className="workspace-building-container">
      <div className="workspace-building-header">
        <button
          type="button"
          className="workspace-layer-disclosure"
          aria-label={`${expanded ? "Collapse" : "Expand"} ${buildingName}`}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown /> : <ChevronRight />}
        </button>
        <Building2 className="size-4 text-blue-600 shrink-0" />
        <LayerCheckbox
          checked={allVisible}
          label={buildingName}
          onChange={toggleMasterVisibility}
        />
        <div className="workspace-building-title" title={buildingName}>
          <span>{buildingName}</span>
          <span className="workspace-building-badge">{floors.length} Floors</span>
        </div>
        <div>
          {!isGeoreferenced ? (
            <button
              type="button"
              className="text-[11px] text-amber-600 font-semibold hover:underline"
              onClick={() => {
                const targetId = primaryFloor?.dataset_id || floors[0]?.dataset_id
                const returnTo = window.location.pathname + window.location.search
                window.location.href = `/datasets/${targetId}/georeference?returnTo=${encodeURIComponent(returnTo)}`
              }}
            >
              Georeference →
            </button>
          ) : (
            <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
              Georeferenced
            </span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="workspace-building-floors">
          {sortedFloors.map((member) => (
            <BuildingFloorItem
              key={member.dataset_id}
              member={member}
              isActiveFloor={activeFloorLevel === member.floor_level}
              onSelectFloor={onSelectFloor}
              onSelect={onSelect}
              onUpdate={onUpdate}
              onDetach={onDetach}
              onOpenBgRemoval={onOpenBgRemoval}
              onOpenTransform={onOpenTransform}
            />
          ))}
        </div>
      )}
    </div>
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
  onOpenTransform,
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
          onClick={() => {
            if (member.dataset?.georeference_status !== "completed") {
              const returnTo = window.location.pathname + window.location.search
              window.location.href = `/datasets/${member.dataset_id}/georeference?returnTo=${encodeURIComponent(returnTo)}`
            } else {
              onSelect(member.dataset_id, "")
            }
          }}
        >
          <span>{member.name}</span>
          <small className={member.dataset?.georeference_status !== "completed" ? "text-amber-600 font-medium cursor-pointer" : ""}>
            {member.dataset?.georeference_status === "completed" ? "Georeferenced" : "Needs georeferencing →"}
          </small>
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
              <LayerOpacitySlider
                datasetId={member.dataset_id}
                opacity={member.raster_opacity}
                onUpdate={onUpdate}
              />
              {member.dataset?.georeference_status !== "completed" && (
                <button
                  type="button"
                  className="workspace-layer-feature-btn text-amber-600"
                  onClick={() => {
                    const returnTo = window.location.pathname + window.location.search
                    window.location.href = `/datasets/${member.dataset_id}/georeference?returnTo=${encodeURIComponent(returnTo)}`
                  }}
                >
                  <MapPin />
                  <span>Georeference Layer</span>
                </button>
              )}
              <button
                type="button"
                className="workspace-layer-feature-btn"
                onClick={() => {
                  if (onOpenTransform) onOpenTransform(member)
                  setMenuOpen(false)
                }}
              >
                <Move />
                <span>Transform Raster</span>
              </button>
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
                  {sublayer.kind !== "raster" && <small>{sublayer.count}</small>}
                </button>
                {sublayer.kind === "raster" && (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      className="workspace-sublayer-tool"
                      title="Transform raster placement (Move, Scale, Rotate, Free Transform)"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (onOpenTransform) onOpenTransform(member)
                      }}
                    >
                      <Move />
                    </button>
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
                  </div>
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
  onOpenTransform,
  activeFloorLevel = 0,
  onSelectFloor,
}) {
  const [bgRemovalMember, setBgRemovalMember] = useState(null)
  const sortedMembers = useMemo(
    () => [...members].sort((a, b) => a.sort_order - b.sort_order),
    [members],
  )

  const { buildingGroups, standaloneMembers } = useMemo(() => {
    const groups = new Map()
    const standalone = []

    sortedMembers.forEach((member) => {
      if (member.is_building_floor || member.building_name) {
        const bName = member.building_name || "Building"
        if (!groups.has(bName)) groups.set(bName, [])
        groups.get(bName).push(member)
      } else {
        standalone.push(member)
      }
    })

    return { buildingGroups: groups, standaloneMembers: standalone }
  }, [sortedMembers])

  const [orderedIds, setOrderedIds] = useState(standaloneMembers.map((member) => member.dataset_id))
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  useEffect(() => {
    setOrderedIds(standaloneMembers.map((member) => member.dataset_id))
  }, [standaloneMembers])

  function finishDrag(event) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = orderedIds.indexOf(active.id)
    const newIndex = orderedIds.indexOf(over.id)
    const next = arrayMove(orderedIds, oldIndex, newIndex)
    setOrderedIds(next)
    onReorder(next)
  }

  const memberById = new Map(standaloneMembers.map((member) => [member.dataset_id, member]))

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
        {/* Render building groups */}
        {Array.from(buildingGroups.entries()).map(([bName, floors]) => (
          <BuildingGroup
            key={bName}
            buildingName={bName}
            floors={floors}
            activeFloorLevel={activeFloorLevel}
            onSelectFloor={onSelectFloor}
            onSelect={onSelect}
            onUpdate={onUpdate}
            onDetach={onDetach}
            onOpenBgRemoval={setBgRemovalMember}
            onOpenTransform={onOpenTransform}
          />
        ))}

        {/* Render standalone datasets (e.g. 2nd dataset) */}
        {standaloneMembers.length > 0 && (
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
                    onOpenTransform={onOpenTransform}
                  />
                ) : null
              })}
            </SortableContext>
          </DndContext>
        )}
      </div>

      {bgRemovalMember && (
        <BackgroundRemovalDialog
          open={Boolean(bgRemovalMember)}
          datasetId={bgRemovalMember.dataset_id}
          datasetName={bgRemovalMember.name}
          isGeoreferenced={bgRemovalMember.dataset?.georeference_status === "completed" || Boolean(bgRemovalMember.dataset?.map_layer)}
          onClose={() => setBgRemovalMember(null)}
          onApplied={() => {
            if (onLayerChanged) onLayerChanged()
          }}
        />
      )}
    </aside>
  )
}

