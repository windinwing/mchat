import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Puzzle, Check, Trash2, ExternalLink } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'

export interface SkillDraftExtra {
  type?: string
  draft_id: string
  group_id?: string | null
  name: string
  description?: string | null
  skill_type?: string
  preview?: string
  file_count?: number
  status?: string
  saved_skill?: SavedSkill | null
}

interface SavedSkill {
  id: string
  name: string
}

const readSavedSkill = (draft: SkillDraftExtra): SavedSkill | null => {
  if (draft.saved_skill?.id && draft.saved_skill?.name) {
    return draft.saved_skill
  }
  if (draft.status === 'committed' && draft.name) {
    return { id: draft.draft_id, name: draft.name }
  }
  return null
}

interface SkillDraftCardProps {
  draft: SkillDraftExtra
  customerId?: string
  onCommitted?: () => void
}

export function SkillDraftCard({ draft, customerId, onCommitted }: SkillDraftCardProps) {
  const { t } = useTranslation()
  const [committing, setCommitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [savedSkill, setSavedSkill] = useState<SavedSkill | null>(() => readSavedSkill(draft))

  useEffect(() => {
    setSavedSkill(readSavedSkill(draft))
  }, [draft])

  const handleCommit = async () => {
    setCommitting(true)
    try {
      const skill = await api.post<SavedSkill>(`/skills/drafts/${draft.draft_id}/commit`, {
        customer_id: customerId || null,
        bind_channel: Boolean(customerId),
        group_id: draft.group_id || null,
      })
      setSavedSkill(skill)
      toast(t('skillDraft.commitSuccess', { name: skill.name }), { type: 'success' })
      onCommitted?.()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('skillDraft.commitFailed')
      toast(msg, { type: 'error' })
    } finally {
      setCommitting(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await api.delete(`/skills/drafts/${draft.draft_id}`, draft.group_id ? { group_id: draft.group_id } : undefined)
      toast(t('skillDraft.discardSuccess'), { type: 'success' })
      onCommitted?.()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('skillDraft.discardFailed')
      toast(msg, { type: 'error' })
    } finally {
      setDeleting(false)
    }
  }

  if (savedSkill) {
    return (
      <div className="mt-3 rounded-xl border border-green-200 dark:border-green-800/60 bg-green-50/80 dark:bg-green-950/30 p-4 space-y-2">
        <div className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/50 px-2 py-1 text-xs font-medium text-green-700 dark:text-green-300">
          {t('skillDraft.savedStatus')}
        </div>
        <p className="text-sm text-gray-800 dark:text-gray-200">
          {t('skillDraft.savedHint', { name: savedSkill.name })}
        </p>
        <Link
          to="/admin/skills"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          {t('skillDraft.openSkills')}
        </Link>
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-xl border border-amber-200 dark:border-amber-800/60 bg-amber-50/80 dark:bg-amber-950/30 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/40 shrink-0">
          <Puzzle className="w-5 h-5 text-amber-700 dark:text-amber-300" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 dark:text-gray-100">{draft.name}</p>
          {draft.description && (
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">{draft.description}</p>
          )}
          <p className="text-xs text-gray-500 mt-1">
            {t('skillDraft.meta', { count: draft.file_count ?? 0 })}
          </p>
          {draft.group_id && (
            <p className="text-xs text-primary-600 dark:text-primary-400 mt-1">
              {t('skillDraft.sharedDraftHint', '群组共享草稿')}
            </p>
          )}
          <p className="text-xs text-gray-500 mt-1">{t('skillDraft.saveLocationHint')}</p>
        </div>
      </div>
      {draft.preview && (
        <pre className="text-xs bg-white/70 dark:bg-gray-900/50 rounded-lg p-3 overflow-x-auto max-h-40 whitespace-pre-wrap border border-amber-100 dark:border-amber-900/40">
          {draft.preview}
        </pre>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={handleCommit} isLoading={committing} leftIcon={<Check className="w-3.5 h-3.5" />}>
          {t('skillDraft.commit')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleDelete}
          isLoading={deleting}
          leftIcon={<Trash2 className="w-3.5 h-3.5" />}
        >
          {t('skillDraft.discard')}
        </Button>
      </div>
    </div>
  )
}
