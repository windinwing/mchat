import type React from 'react'
import { Hand, Map, Maximize2, MousePointer2, ZoomIn, ZoomOut } from 'lucide-react'
import { Panel } from '@xyflow/react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export type CanvasTool = 'pointer' | 'pan'

function ToolbarButton({
  title,
  onClick,
  active,
  disabled,
  children,
}: {
  title: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-md transition-colors',
        active
          ? 'bg-primary-600 text-white shadow-sm dark:bg-primary-500'
          : 'text-gray-600 hover:bg-gray-200/90 dark:text-gray-300 dark:hover:bg-gray-700/90',
        'disabled:cursor-not-allowed disabled:opacity-40',
      )}
    >
      {children}
    </button>
  )
}

interface Props {
  canvasTool: CanvasTool
  onCanvasToolChange: (tool: CanvasTool) => void
  spacePanActive: boolean
  zoom: number
  showMinimap: boolean
  onToggleMinimap: () => void
  onZoomIn: () => void
  onZoomOut: () => void
  onFitView: () => void
  onResetZoom: () => void
}

export function WorkflowCanvasToolbar({
  canvasTool,
  onCanvasToolChange,
  spacePanActive,
  zoom,
  showMinimap,
  onToggleMinimap,
  onZoomIn,
  onZoomOut,
  onFitView,
  onResetZoom,
}: Props) {
  const { t } = useTranslation()
  const zoomPct = Math.round(zoom * 100)
  const pointerActive = canvasTool === 'pointer' && !spacePanActive
  const panActive = canvasTool === 'pan' || spacePanActive

  return (
    <Panel position="top-left" className="!m-3 flex flex-col gap-1">
      <div
        className={cn(
          'flex flex-col items-center gap-0.5 rounded-lg border border-gray-200/90 bg-white/95 p-1 shadow-lg backdrop-blur-sm',
          'dark:border-gray-700/90 dark:bg-gray-900/95',
        )}
      >
        <ToolbarButton
          title={t('workflows.canvasToolPointer')}
          active={pointerActive}
          onClick={() => onCanvasToolChange('pointer')}
        >
          <MousePointer2 className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          title={
            spacePanActive
              ? t('workflows.canvasSpacePanActive')
              : t('workflows.canvasToolPan')
          }
          active={panActive}
          onClick={() => onCanvasToolChange('pan')}
        >
          <Hand className="h-4 w-4" />
        </ToolbarButton>

        <div className="my-0.5 h-px bg-gray-200 dark:bg-gray-700" />

        <ToolbarButton title={t('workflows.canvasZoomIn')} onClick={onZoomIn}>
          <ZoomIn className="h-4 w-4" />
        </ToolbarButton>
        <button
          type="button"
          title={t('workflows.canvasResetZoom')}
          aria-label={t('workflows.canvasResetZoom')}
          onClick={onResetZoom}
          className="min-h-[28px] rounded-md px-1 text-[11px] font-medium tabular-nums text-gray-700 hover:bg-gray-200/90 dark:text-gray-200 dark:hover:bg-gray-700/90"
        >
          {zoomPct}%
        </button>
        <ToolbarButton title={t('workflows.canvasZoomOut')} onClick={onZoomOut}>
          <ZoomOut className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton title={t('workflows.canvasFitView')} onClick={onFitView}>
          <Maximize2 className="h-4 w-4" />
        </ToolbarButton>

        <div className="my-0.5 h-px bg-gray-200 dark:bg-gray-700" />

        <ToolbarButton
          title={t('workflows.canvasToggleMinimap')}
          active={showMinimap}
          onClick={onToggleMinimap}
        >
          <Map className="h-4 w-4" />
        </ToolbarButton>
      </div>
    </Panel>
  )
}
