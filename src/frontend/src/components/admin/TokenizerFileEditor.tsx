import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Save } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

export type GlobalTokenizerKey = 'stop_words' | 'suffix_chars'

export interface TokenizerFileTarget {
  scope: 'global' | 'kb'
  key: GlobalTokenizerKey | 'user_dict'
  knowledgeBaseId?: string
  title: string
  hint: string
  filename: string
}

interface Props {
  target: TokenizerFileTarget | null
  onClose: () => void
  onSaved?: () => void
}

export function TokenizerFileEditor({ target, onClose, onSaved }: Props) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [content, setContent] = useState('')

  useEffect(() => {
    if (!target) return
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        let data: { content: string }
        if (target.scope === 'global') {
          data = await api.get<{ content: string }>(`/settings/tokenizer/${target.key}`)
        } else if (target.knowledgeBaseId) {
          data = await api.get<{ content: string }>(
            `/knowledge/bases/${target.knowledgeBaseId}/tokenizer/user_dict`,
          )
        } else {
          return
        }
        if (!cancelled) setContent(data.content ?? '')
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : t('common.failed')
        toast(t('knowledge.toastTokenizerLoadFailed'), { type: 'error', message })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [target, t])

  const save = async () => {
    if (!target) return
    setSaving(true)
    try {
      if (target.scope === 'global') {
        await api.put(`/settings/tokenizer/${target.key}`, { content })
      } else if (target.knowledgeBaseId) {
        await api.put(`/knowledge/bases/${target.knowledgeBaseId}/tokenizer/user_dict`, {
          content,
        })
      }
      toast(t('knowledge.toastTokenizerSaved'), { type: 'success' })
      onSaved?.()
      onClose()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastSaveFailed'), { type: 'error', message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={Boolean(target)}
      onClose={onClose}
      title={target?.title}
      size="lg"
    >
      <div className="space-y-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">{target?.hint}</p>
        <p className="text-[11px] font-mono text-gray-400 dark:text-gray-500">{target?.filename}</p>
        {loading ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={16}
            spellCheck={false}
            className={
              'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-mono ' +
              'text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 ' +
              'dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100'
            }
            placeholder={t('knowledge.tokenizerFilePlaceholder')}
          />
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={save} isLoading={saving} disabled={loading}>
            <Save className="w-4 h-4 mr-1" />
            {t('common.save')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
