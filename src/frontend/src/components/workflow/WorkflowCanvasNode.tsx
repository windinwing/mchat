import React, { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import {
  BarChart3,
  CirclePlay,
  GitMerge,
  Search,
  ShieldCheck,
  Split,
  Square,
  Wrench,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import type { GraphNodeType } from '@/lib/workflowSkillMeta'
import { NODE_COLORS } from '@/lib/workflowSkillMeta'

type WorkflowCanvasNodeData = {
  label: string
  nodeType: GraphNodeType
  config?: Record<string, unknown>
  skillLabel?: string
  categoryLabel?: string
  skillMissing?: boolean
}

const ICONS: Partial<Record<GraphNodeType, React.ComponentType<{ className?: string }>>> = {
  start: CirclePlay,
  skill: Wrench,
  condition: Split,
  approval: ShieldCheck,
  merge: GitMerge,
  end: Square,
}

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  search: Search,
  analyze: BarChart3,
  visualize: BarChart3,
  export: Square,
}

function WorkflowCanvasNodeComponent({ data, selected }: NodeProps) {
  const d = data as WorkflowCanvasNodeData
  const nodeType = d.nodeType || 'skill'
  const color = NODE_COLORS[nodeType] || NODE_COLORS.skill
  const Icon = ICONS[nodeType] || Wrench
  const role = String(d.config?.workflow_role || '')
  const CategoryIcon = CATEGORY_ICONS[role]

  return (
    <div
      className={cn(
        'min-w-[168px] max-w-[220px] rounded-xl border-2 bg-white px-3 py-2 shadow-sm dark:bg-gray-900',
        selected && 'ring-2 ring-primary-400 ring-offset-1 dark:ring-offset-gray-950',
      )}
      style={{ borderColor: color }}
    >
      {nodeType !== 'start' && (
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !bg-gray-400" />
      )}
      <div className="flex items-start gap-2">
        <div
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
          style={{ backgroundColor: `${color}22`, color }}
        >
          {nodeType === 'skill' && CategoryIcon ? (
            <CategoryIcon className="h-4 w-4" />
          ) : (
            <Icon className="h-4 w-4" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-gray-900 dark:text-gray-100">{d.label}</p>
          {nodeType === 'skill' && d.skillLabel ? (
            <p className="truncate text-[10px] text-gray-500 dark:text-gray-400">{d.skillLabel}</p>
          ) : (
            <p className="text-[10px] uppercase tracking-wide text-gray-400">{nodeType}</p>
          )}
          {nodeType === 'skill' && d.skillMissing ? (
            <p className="mt-0.5 text-[10px] text-amber-600 dark:text-amber-400">⚠</p>
          ) : null}
          {d.categoryLabel ? (
            <span
              className="mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium"
              style={{ backgroundColor: `${color}18`, color }}
            >
              {d.categoryLabel}
            </span>
          ) : null}
        </div>
      </div>
      {nodeType !== 'end' && (
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !bg-gray-400" />
      )}
    </div>
  )
}

export const WorkflowCanvasNode = memo(WorkflowCanvasNodeComponent)

export const workflowNodeTypes = {
  workflowNode: WorkflowCanvasNode,
}
