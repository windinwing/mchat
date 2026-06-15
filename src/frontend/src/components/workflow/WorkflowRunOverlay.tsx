import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, CheckCircle2, XCircle, Clock, FileOutput, X, RotateCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'

interface RunItem {
  id: string
  status: string
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
  trigger_type?: string | null
  error?: string | null
  output_payload?: Record<string, unknown> | null
}

interface WorkflowRunOverlayProps {
  open: boolean
  onClose: () => void
  workflowId?: string
}

function statusIcon(status: string) {
  if (status === 'success') return <CheckCircle2 className="w-4 h-4 text-green-500" />
  if (status === 'failed') return <XCircle className="w-4 h-4 text-red-500" />
  if (status === 'running') return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
  if (status === 'paused') return <Clock className="w-4 h-4 text-amber-500" />
  return <Clock className="w-4 h-4 text-gray-400" />
}

export function WorkflowRunOverlay({ open, onClose, workflowId }: WorkflowRunOverlayProps) {
  const { t } = useTranslation()
  const [runs, setRuns] = useState<RunItem[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedRun, setSelectedRun] = useState<RunItem | null>(null)
  const [rerunning, setRerunning] = useState(false)

  const load = useCallback(async () => {
    if (!workflowId) return
    setLoading(true)
    try {
      const data = await api.get<{ items: RunItem[] }>('/workflows/runs/list', {
        limit: '30',
        workflow_id: workflowId,
      })
      setRuns(data.items || [])
    } catch {
      setRuns([])
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    if (open) {
      void load()
      setSelectedRun(null)
    }
  }, [open, load])

  // Auto-refresh while runs are active
  useEffect(() => {
    if (!open) return
    const hasActive = runs.some((r) => r.status === 'running' || r.status === 'paused')
    if (!hasActive) return
    const timer = setInterval(() => void load(), 5000)
    return () => clearInterval(timer)
  }, [open, runs, load])

  const handleRerun = async (run: RunItem) => {
    if (!workflowId) return
    setRerunning(true)
    try {
      await api.post(`/workflows/runs/${run.id}/resume`, {})
      await load()
    } catch {
      // ignore
    } finally {
      setRerunning(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90]" onMouseDown={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="absolute right-0 top-0 h-full w-full max-w-md bg-white dark:bg-gray-900 shadow-2xl flex flex-col"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 dark:border-gray-800 px-4 py-3">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-primary-500" />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {selectedRun ? t('workflows.sidebarResults', 'Results') : t('workflows.sidebarHistory', 'History')}
            </h2>
          </div>
          <div className="flex items-center gap-1">
            {selectedRun && (
              <button
                type="button"
                onClick={() => setSelectedRun(null)}
                className="rounded-lg px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                ← {t('common.back', 'Back')}
              </button>
            )}
            <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : selectedRun ? (
            <RunDetail run={selectedRun} />
          ) : runs.length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-400">{t('workflows.noRuns', 'No runs yet')}</p>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <div
                  key={run.id}
                  className={cn(
                    'flex items-center gap-3 rounded-xl border p-3 cursor-pointer transition-colors',
                    'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800',
                  )}
                  onClick={() => setSelectedRun(run)}
                >
                  {statusIcon(run.status)}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-gray-700 dark:text-gray-300">
                      {run.trigger_type || 'manual'}
                    </p>
                    <p className="text-[10px] text-gray-400">
                      {new Date(run.started_at).toLocaleString()}
                      {run.duration_ms != null && ` · ${(run.duration_ms / 1000).toFixed(1)}s`}
                    </p>
                  </div>
                  {run.status === 'paused' && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleRerun(run)
                      }}
                      disabled={rerunning}
                      className="flex items-center gap-1 rounded-md bg-amber-100 dark:bg-amber-900/30 px-2 py-1 text-[10px] font-medium text-amber-700 dark:text-amber-400 hover:bg-amber-200"
                    >
                      <RotateCw className="w-3 h-3" />
                      {t('workflows.resume', 'Resume')}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function RunDetail({ run }: { run: RunItem }) {
  const { t } = useTranslation()
  const payload = run.output_payload as Record<string, unknown> | null
  const nodes = (payload?.nodes || payload?.node_runs || {}) as Record<string, unknown>

  return (
    <div className="space-y-3">
      {/* Status bar */}
      <div className="flex items-center gap-2 rounded-lg bg-gray-50 dark:bg-gray-800/50 p-3">
        {statusIcon(run.status)}
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{run.status}</p>
          <p className="text-xs text-gray-400">{new Date(run.started_at).toLocaleString()}</p>
        </div>
        {run.duration_ms != null && (
          <span className="text-xs text-gray-400">{(run.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </div>

      {/* Error */}
      {run.error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-3">
          <p className="text-xs text-red-600 dark:text-red-400">{run.error}</p>
        </div>
      )}

      {/* Node outputs */}
      {Object.keys(nodes).length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase text-gray-400">
            <FileOutput className="inline w-3.5 h-3.5 mr-1" />
            {t('workflows.nodeOutputs', 'Node Outputs')}
          </p>
          <div className="space-y-2">
            {Object.entries(nodes).map(([nodeId, data]) => {
              const result = (data as Record<string, unknown>)?.result ?? data
              const text =
                typeof result === 'string'
                  ? result
                  : typeof result === 'object'
                    ? JSON.stringify(result, null, 2)
                    : String(result || '')
              const isLong = text.length > 200
              return (
                <div key={nodeId} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
                  <div className="border-b border-gray-100 dark:border-gray-700 px-3 py-1.5">
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{nodeId}</p>
                  </div>
                  <pre className={cn(
                    'p-3 text-[11px] text-gray-600 dark:text-gray-400 overflow-x-auto whitespace-pre-wrap break-words',
                    isLong && 'max-h-40 overflow-y-auto',
                  )}>
                    {text.slice(0, 2000)}
                    {text.length > 2000 && '\n…(truncated)'}
                  </pre>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
