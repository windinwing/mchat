import { memo, useState, useCallback } from 'react'
import { NodeProps, NodeResizer, type Node } from '@xyflow/react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

const GROUP_COLORS = [
  '#64748b',
  '#3b82f6',
  '#22c55e',
  '#f59e0b',
  '#a855f7',
  '#ef4444',
  '#06b6d4',
  '#ec4899',
]

type GroupNodeData = {
  label: string
  config?: { color?: string; collapsed?: boolean }
  groupChildCount?: number
}

function WorkflowGroupNodeComponent({ id, data, selected }: NodeProps) {
  const d = data as GroupNodeData
  const color = d.config?.color || '#64748b'
  const collapsed = d.config?.collapsed || false
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(d.label)

  const toggleCollapse = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      // Dispatch a custom event the editor listens to
      window.dispatchEvent(
        new CustomEvent('mchat-group-toggle', { detail: { groupId: id } }),
      )
    },
    [id],
  )

  const cycleColor = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    const current = d.config?.color || '#64748b'
    const idx = GROUP_COLORS.indexOf(current)
    const next = GROUP_COLORS[(idx + 1) % GROUP_COLORS.length]
    window.dispatchEvent(
      new CustomEvent('mchat-group-color', { detail: { groupId: id, color: next } }),
    )
  }, [id, d.config?.color])

  const commitLabel = useCallback(() => {
    setEditing(false)
    if (label !== d.label) {
      window.dispatchEvent(
        new CustomEvent('mchat-group-rename', { detail: { groupId: id, label } }),
      )
    }
  }, [id, label, d.label])

  return (
    <>
      {!collapsed && (
        <NodeResizer
          isVisible={selected}
          minWidth={160}
          minHeight={100}
          lineClassName="!border-primary-400"
          handleClassName="!h-2.5 !w-2.5 !rounded !border !border-primary-500 !bg-white"
        />
      )}
      <div
        className={cn(
          'h-full w-full rounded-xl border-2 transition-colors',
          collapsed ? 'border-solid' : 'border-dashed',
          selected && 'ring-2 ring-primary-400 ring-offset-1',
        )}
        style={{
          borderColor: color,
          backgroundColor: `${color}0d`,
        }}
      >
        {/* Title bar */}
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded-t-xl select-none"
          style={{ backgroundColor: `${color}1a` }}
          onDoubleClick={(e) => {
            e.stopPropagation()
            setEditing(true)
          }}
        >
          <button
            type="button"
            onClick={toggleCollapse}
            className="shrink-0 rounded p-0.5 hover:bg-black/5 dark:hover:bg-white/10"
            title={collapsed ? 'Expand' : 'Collapse'}
          >
            {collapsed ? (
              <ChevronRight className="w-3.5 h-3.5" style={{ color }} />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" style={{ color }} />
            )}
          </button>

          {editing ? (
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onBlur={commitLabel}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitLabel()
                if (e.key === 'Escape') {
                  setLabel(d.label)
                  setEditing(false)
                }
              }}
              onClick={(e) => e.stopPropagation()}
              className="flex-1 min-w-0 bg-transparent border-b border-primary-400 text-xs font-semibold outline-none"
              style={{ color }}
              autoFocus
            />
          ) : (
            <p
              className="flex-1 min-w-0 truncate text-xs font-semibold cursor-text"
              style={{ color }}
              onDoubleClick={(e) => {
                e.stopPropagation()
                setEditing(true)
              }}
            >
              {d.label || 'Group'}
            </p>
          )}

          <button
            type="button"
            onClick={cycleColor}
            className="shrink-0 h-3.5 w-3.5 rounded-full border border-white/50 shadow-sm"
            style={{ backgroundColor: color }}
            title="Cycle color"
          />

          {d.groupChildCount != null && d.groupChildCount > 0 && (
            <span className="shrink-0 text-[10px] text-gray-400">
              {d.groupChildCount}
            </span>
          )}
        </div>
      </div>
    </>
  )
}

export const WorkflowGroupNode = memo(WorkflowGroupNodeComponent)

export const groupNodeTypes = {
  workflowGroup: WorkflowGroupNode,
}

/** Calculate bounding box of nodes for group creation */
export function computeGroupBounds(
  nodes: Node[],
  padding = 40,
): { x: number; y: number; width: number; height: number } {
  if (nodes.length === 0) return { x: 0, y: 0, width: 200, height: 120 }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes) {
    const w = (n.style as any)?.width || n.width || 180
    const h = (n.style as any)?.height || n.height || 60
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + w)
    maxY = Math.max(maxY, n.position.y + h)
  }
  return {
    x: minX - padding,
    y: minY - padding - 24, // extra for title bar
    width: maxX - minX + padding * 2,
    height: maxY - minY + padding * 2 + 24,
  }
}
