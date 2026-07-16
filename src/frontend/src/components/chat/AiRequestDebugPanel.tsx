import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Bug, ChevronDown, ChevronRight } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import type { Message } from '@/stores/chat'
import { cn } from '@/lib/utils'

interface DebugRequest {
  provider?: string
  model?: string
  max_tokens?: number
  temperature?: number
  message_count?: number
  tool_count?: number
  tool_names?: string[]
  knowledge_hit_count?: number
  rag_top_k?: number | null
  estimated_prompt_tokens?: number
  estimated_total_tokens?: number
  context_limit?: number
  over_context_limit?: boolean
  system_prompt_length?: number
  timestamp?: string
}

interface AiRequestDebugPanelProps {
  open: boolean
  onClose: () => void
  messages: Message[]
}

/** Collapsible row for a single assistant message's debug info. */
function DebugMessageRow({ message }: { message: Message }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const d = (message.extra_data?.debug_request ?? {}) as DebugRequest
  if (!d || !d.model) return null

  const overLimit = d.over_context_limit === true
  const preview =
    (message.content || '').slice(0, 60).replace(/\n/g, ' ') + (message.content.length > 60 ? '…' : '')

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 shrink-0 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 shrink-0 text-gray-400" />
        )}
        <span className="text-xs font-mono text-gray-600 dark:text-gray-400 truncate flex-1">
          {preview}
        </span>
        <span className="text-xs text-gray-400 shrink-0">
          ~{d.estimated_total_tokens ?? '?'}tok
        </span>
        {overLimit && (
          <span className="shrink-0 text-[10px] text-red-600 dark:text-red-400 font-medium">
            {t('chat.debugOverLimit')}
          </span>
        )}
      </button>
      {expanded && (
        <div className="px-3 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/30 space-y-1.5">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <Field label={t('chat.debugProvider')} value={d.provider ?? '-'} />
            <Field label={t('chat.debugModel')} value={d.model ?? '-'} />
            <Field
              label={t('chat.debugPromptTokens')}
              value={String(d.estimated_prompt_tokens ?? '?')}
            />
            <Field
              label={t('chat.debugMaxTokens')}
              value={String(d.max_tokens ?? '?')}
            />
            <Field
              label={t('chat.debugTotalTokens')}
              value={`${d.estimated_total_tokens ?? '?'} / ${d.context_limit ?? '?'}`}
              danger={overLimit}
            />
            <Field label={t('chat.debugMessages')} value={String(d.message_count ?? 0)} />
            <Field label={t('chat.debugTools')} value={String(d.tool_count ?? 0)} />
            <Field
              label={t('chat.debugRagHits')}
              value={String(d.knowledge_hit_count ?? 0)}
            />
            <Field
              label={t('chat.debugRagTopK')}
              value={d.rag_top_k == null ? t('chat.debugRagTopKConfig') : String(d.rag_top_k)}
            />
            <Field
              label={t('chat.debugSysPromptLen')}
              value={`${d.system_prompt_length ?? 0}`}
            />
          </div>
          {d.tool_names && d.tool_names.length > 0 && (
            <div className="pt-1">
              <p className="text-[10px] text-gray-400 mb-1">{t('chat.debugToolNames')}</p>
              <div className="flex flex-wrap gap-1">
                {d.tool_names.map((name) => (
                  <span
                    key={name}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] text-gray-400 pt-1">
            {t('chat.debugFullPayloadHint')}
          </p>
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  danger,
}: {
  label: string
  value: string
  danger?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-gray-400">{label}</span>
      <span
        className={cn(
          'font-mono',
          danger ? 'text-red-600 dark:text-red-400 font-semibold' : 'text-gray-700 dark:text-gray-300',
        )}
      >
        {value}
      </span>
    </div>
  )
}

export function AiRequestDebugPanel({ open, onClose, messages }: AiRequestDebugPanelProps) {
  const { t } = useTranslation()
  const debugMessages = messages.filter(
    (m) => m.role === 'assistant' && m.extra_data?.debug_request,
  )
  const overLimitCount = debugMessages.filter(
    (m) => (m.extra_data?.debug_request as DebugRequest)?.over_context_limit,
  ).length

  return (
    <Dialog open={open} onClose={onClose} title={t('chat.debugPanelTitle')} size="lg">
      <div className="space-y-4">
        <div
          className={cn(
            'rounded-lg p-3 text-sm flex items-start gap-2',
            overLimitCount > 0
              ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
              : 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',
          )}
        >
          {overLimitCount > 0 ? (
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          ) : (
            <Bug className="w-4 h-4 shrink-0 mt-0.5" />
          )}
          <span>
            {overLimitCount > 0
              ? t('chat.debugSummaryOver', { count: overLimitCount, total: debugMessages.length })
              : t('chat.debugSummaryOk', { count: debugMessages.length })}
          </span>
        </div>

        {debugMessages.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">
            {t('chat.debugEmpty')}
          </p>
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-y-auto">
            {debugMessages.map((m) => (
              <DebugMessageRow key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>
    </Dialog>
  )
}
