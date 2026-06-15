import React, { memo, useEffect, useRef, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useTranslation } from 'react-i18next'
import {
  BarChart3,
  CirclePlay,
  GitMerge,
  Repeat,
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
  batchListPath?: string
  batchChildCount?: number
  batchChildLabels?: string[]
}

const ICONS: Partial<Record<GraphNodeType, React.ComponentType<{ className?: string }>>> = {
  start: CirclePlay,
  skill: Wrench,
  condition: Split,
  approval: ShieldCheck,
  merge: GitMerge,
  batch: Repeat,
  end: Square,
}

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  search: Search,
  analyze: BarChart3,
  visualize: BarChart3,
  export: Square,
}

function WorkflowCanvasNodeComponent({ id, data, selected }: NodeProps) {
  const { t } = useTranslation()
  const d = data as WorkflowCanvasNodeData
  const nodeType = d.nodeType || 'skill'
  const color = NODE_COLORS[nodeType] || NODE_COLORS.skill
  const Icon = ICONS[nodeType] || Wrench
  const role = String(d.config?.workflow_role || '')
  const CategoryIcon = CATEGORY_ICONS[role]
  const [isDragOver, setIsDragOver] = useState(false)
  const [pulse, setPulse] = useState(false)
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (pulseTimer.current) clearTimeout(pulseTimer.current)
    }
  }, [])

  const triggerPulse = () => {
    setPulse(true)
    if (pulseTimer.current) clearTimeout(pulseTimer.current)
    pulseTimer.current = setTimeout(() => setPulse(false), 600)
  }

  const handleBatchDragEnter = (e: React.DragEvent) => {
    if (nodeType !== 'batch') return
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'move'
    if (!isDragOver) setIsDragOver(true)
  }

  const handleBatchDragOver = (e: React.DragEvent) => {
    if (nodeType !== 'batch') return
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'move'
    if (!isDragOver) setIsDragOver(true)
  }

  const handleBatchDragLeave = (e: React.DragEvent) => {
    if (nodeType !== 'batch') return
    e.preventDefault()
    e.stopPropagation()
    const related = e.relatedTarget as Node | null
    if (!related || !e.currentTarget.contains(related)) {
      setIsDragOver(false)
    }
  }

  const handleBatchDrop = (e: React.DragEvent) => {
    if (nodeType !== 'batch') return
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
    const raw = e.dataTransfer.getData('application/mchat-workflow')
    if (!raw) return
    triggerPulse()
    window.dispatchEvent(new CustomEvent('mchat-batch-drop', { detail: { raw, batchNodeId: id } }))
  }

  return (
    <div
      className={cn(
        nodeType === 'batch'
          ? cn(
              'relative w-full h-full rounded-xl border-2 border-dashed px-3 py-1.5 transition-all duration-150',
              isDragOver
                ? 'bg-cyan-100/80 ring-4 ring-cyan-400 border-cyan-500 dark:bg-cyan-900/50 dark:ring-cyan-500'
                : cn(
                    'bg-cyan-50/40 dark:bg-cyan-950/20',
                    selected && 'ring-2 ring-primary-400 ring-offset-1 dark:ring-offset-gray-950',
                  ),
              pulse && 'mchat-batch-pulse',
            )
          : cn(
              'min-w-[168px] max-w-[220px] rounded-xl border-2 bg-white px-3 py-2 shadow-sm dark:bg-gray-900',
              selected && 'ring-2 ring-primary-400 ring-offset-1 dark:ring-offset-gray-950',
            ),
      )}
      style={{ borderColor: color }}
    >
      {nodeType === 'batch' ? (
        <div
          className="w-full h-full"
          data-batch-container="true"
          data-batch-id={id}
          onDragEnter={handleBatchDragEnter}
          onDragOver={handleBatchDragOver}
          onDragLeave={handleBatchDragLeave}
          onDrop={handleBatchDrop}
        >
          <div className="flex items-center gap-1.5">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded" style={{ backgroundColor: `${color}22`, color }}>
              <Repeat className="h-3.5 w-3.5" />
            </div>
            <p className="text-[11px] font-semibold text-gray-900 dark:text-gray-100">{d.label}</p>
            {d.batchChildCount ? (
              <span className="text-[10px] text-cyan-600 dark:text-cyan-400">↳ {d.batchChildCount} 节点</span>
            ) : (
              <span className="text-[10px] text-gray-400">{t('workflows.batchDropHint')}</span>
            )}
          </div>
          {d.batchListPath ? (
            <p className="text-[9px] text-gray-400 mt-0.5">← {d.batchListPath}</p>
          ) : null}
          {d.batchChildLabels && d.batchChildLabels.length > 0 ? (
            <div className="mt-1 space-y-0.5">
              {d.batchChildLabels.slice(0, 5).map((name, idx) => (
                <p key={idx} className="text-[9px] text-gray-500 dark:text-gray-400 truncate">• {name}</p>
              ))}
              {d.batchChildLabels.length > 5 && (
                <p className="text-[9px] text-gray-400">…还有 {d.batchChildLabels.length - 5} 个</p>
              )}
            </div>
          ) : null}
          <div className="absolute left-0 right-0 bottom-0 top-8 flex items-center justify-center pointer-events-none">
            {!d.batchChildCount && (
              <span className="text-[10px] text-gray-300 dark:text-gray-600">{t('workflows.batchDropZone')}</span>
            )}
          </div>
        </div>
      ) : (
        <>
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
        </>
      )}
      {nodeType === 'batch' && (
        <>
          <Handle type="target" position={Position.Left} className="!h-2 !w-2 !bg-gray-400" />
          <Handle type="source" position={Position.Right} className="!h-2 !w-2 !bg-gray-400" />
        </>
      )}
    </div>
  )
}

export const WorkflowCanvasNode = memo(WorkflowCanvasNodeComponent)

export const workflowNodeTypes = {
  workflowNode: WorkflowCanvasNode,
}
