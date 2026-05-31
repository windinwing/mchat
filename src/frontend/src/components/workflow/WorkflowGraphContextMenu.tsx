import React, { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

export type GraphContextMenuState =
  | { kind: 'node'; x: number; y: number; nodeId: string }
  | { kind: 'edge'; x: number; y: number; edgeId: string }
  | { kind: 'pane'; x: number; y: number; flowX: number; flowY: number }
  | null

interface Props {
  menu: GraphContextMenuState
  onClose: () => void
  onDeleteNode: (nodeId: string) => void
  onDuplicateNode: (nodeId: string) => void
  onDeleteEdge: (edgeId: string) => void
  onSetEdgeCondition: (edgeId: string, condition: string) => void
  onAddControlAt: (nodeType: string, position: { x: number; y: number }) => void
}

export function WorkflowGraphContextMenu({
  menu,
  onClose,
  onDeleteNode,
  onDuplicateNode,
  onDeleteEdge,
  onSetEdgeCondition,
  onAddControlAt,
}: Props) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menu) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [menu, onClose])

  if (!menu) return null

  const itemClass =
    'block w-full px-3 py-1.5 text-left text-xs text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800'

  return (
    <div
      ref={ref}
      className="fixed z-[100] min-w-[160px] rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-900"
      style={{ left: menu.x, top: menu.y }}
    >
      {menu.kind === 'node' ? (
        <>
          <button type="button" className={itemClass} onClick={() => { onDuplicateNode(menu.nodeId); onClose() }}>
            {t('workflows.ctxDuplicateNode')}
          </button>
          <button type="button" className={`${itemClass} text-red-600 dark:text-red-400`} onClick={() => { onDeleteNode(menu.nodeId); onClose() }}>
            {t('workflows.ctxDeleteNode')}
          </button>
        </>
      ) : null}
      {menu.kind === 'edge' ? (
        <>
          <button type="button" className={itemClass} onClick={() => { onSetEdgeCondition(menu.edgeId, ''); onClose() }}>
            {t('workflows.graphEdgeDefault')}
          </button>
          <button type="button" className={itemClass} onClick={() => { onSetEdgeCondition(menu.edgeId, 'true'); onClose() }}>
            true
          </button>
          <button type="button" className={itemClass} onClick={() => { onSetEdgeCondition(menu.edgeId, 'false'); onClose() }}>
            false
          </button>
          <button type="button" className={`${itemClass} text-red-600 dark:text-red-400`} onClick={() => { onDeleteEdge(menu.edgeId); onClose() }}>
            {t('workflows.ctxDeleteEdge')}
          </button>
        </>
      ) : null}
      {menu.kind === 'pane' ? (
        <>
          <p className="px-3 py-1 text-[10px] font-semibold uppercase text-gray-400">{t('workflows.ctxAddNode')}</p>
          {(
            [
              ['start', 'workflows.graphNodeStart'],
              ['merge', 'workflows.graphNodeMerge'],
              ['condition', 'workflows.graphNodeCondition'],
              ['approval', 'workflows.graphNodeApproval'],
              ['end', 'workflows.graphNodeEnd'],
            ] as const
          ).map(([type, labelKey]) => (
            <button
              key={type}
              type="button"
              className={itemClass}
              onClick={() => {
                onAddControlAt(type, { x: menu.flowX, y: menu.flowY })
                onClose()
              }}
            >
              {t(labelKey)}
            </button>
          ))}
        </>
      ) : null}
    </div>
  )
}
