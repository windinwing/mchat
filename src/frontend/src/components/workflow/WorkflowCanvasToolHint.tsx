import { Panel } from '@xyflow/react'

import { cn } from '@/lib/utils'

interface Props {
  label: string | null
}

/** ComfyUI-style transient tool mode indicator (bottom center of canvas). */
export function WorkflowCanvasToolHint({ label }: Props) {
  return (
    <Panel position="bottom-center" className="pointer-events-none !mb-5">
      <div
        className={cn(
          'rounded-lg border border-gray-700/40 bg-gray-900/90 px-4 py-2 text-sm font-medium text-white shadow-xl backdrop-blur-sm',
          'transition-all duration-300 ease-out',
          'dark:border-gray-600/50 dark:bg-gray-950/90',
          label ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0',
        )}
        aria-live="polite"
        aria-hidden={!label}
      >
        {label || '\u00a0'}
      </div>
    </Panel>
  )
}
