import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Clock3, Plus, Trash2 } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { formatDate } from '@/lib/utils'
import { MarkdownToolbar } from '@/components/admin/MarkdownToolbar'

interface GroupOption {
  id: string
  name: string
}

interface GroupMemory {
  id: string
  group_id: string
  memory_type: string
  title: string
  content: string
  tags?: string[] | null
  topic?: string | null
  status: string
  updated_at: string
}

interface GroupMemoryRevision {
  id: string
  entry_id: string
  version: number
  title: string
  content: string
  tags?: string[] | null
  topic?: string | null
  status: string
  edited_by: string
  created_at: string
}

export function GroupMemoryPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const groupFromUrl = searchParams.get('group') || ''
  const [groups, setGroups] = useState<GroupOption[]>([])
  const [groupId, setGroupId] = useState(groupFromUrl)
  const [memories, setMemories] = useState<GroupMemory[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<GroupMemory | null>(null)
  const [saving, setSaving] = useState(false)
  const [revisionTarget, setRevisionTarget] = useState<GroupMemory | null>(null)
  const [revisions, setRevisions] = useState<GroupMemoryRevision[]>([])
  const [revisionLoading, setRevisionLoading] = useState(false)
  const [editorMode, setEditorMode] = useState<'edit' | 'preview'>('edit')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [form, setForm] = useState({
    memory_type: 'prompt',
    title: '',
    content: '',
    tags: '',
    topic: '',
    status: 'draft',
  })

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === groupId) || null,
    [groups, groupId],
  )

  const loadGroups = async () => {
    try {
      const rows = await api.get<GroupOption[]>('/groups/mine')
      setGroups(rows || [])
      const preferred = groupFromUrl || groupId
      if (preferred && rows?.some((row) => row.id === preferred)) {
        setGroupId(preferred)
      } else if (!groupId && rows?.length) {
        setGroupId(rows[0].id)
      }
    } catch {
      setGroups([])
    }
  }

  const loadMemories = async (targetGroupId: string) => {
    if (!targetGroupId) {
      setMemories([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const rows = await api.get<GroupMemory[]>(`/groups/${targetGroupId}/memories`)
      setMemories(rows || [])
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groupMemory.loadFailed'), { type: 'error' })
      setMemories([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadGroups()
  }, [])

  useEffect(() => {
    void loadMemories(groupId)
  }, [groupId])

  const openCreate = () => {
    setEditing(null)
    setEditorMode('edit')
    setForm({ memory_type: 'prompt', title: '', content: '', tags: '', topic: '', status: 'draft' })
  }

  const openEdit = (memory: GroupMemory) => {
    setEditing(memory)
    setEditorMode('edit')
    setForm({
      memory_type: memory.memory_type,
      title: memory.title,
      content: memory.content,
      tags: (memory.tags || []).join(', '),
      topic: memory.topic || '',
      status: memory.status,
    })
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!groupId) return
    setSaving(true)
    const payload = {
      memory_type: form.memory_type,
      title: form.title.trim(),
      content: form.content.trim(),
      tags: form.tags
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
      topic: form.topic.trim() || null,
      status: form.status,
    }
    try {
      if (editing) {
        await api.patch(`/groups/${groupId}/memories/${editing.id}`, payload)
        toast(t('groupMemory.saved'), { type: 'success' })
      } else {
        await api.post(`/groups/${groupId}/memories`, payload)
        toast(t('groupMemory.created'), { type: 'success' })
      }
      setEditing(null)
      openCreate()
      await loadMemories(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groupMemory.saveFailed'), { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (memory: GroupMemory) => {
    if (!window.confirm(t('groupMemory.deleteConfirm', { name: memory.title }))) return
    try {
      await api.delete(`/groups/${groupId}/memories/${memory.id}`)
      toast(t('groupMemory.deleted'), { type: 'success' })
      await loadMemories(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groupMemory.deleteFailed'), { type: 'error' })
    }
  }

  const openRevisions = async (memory: GroupMemory) => {
    setRevisionTarget(memory)
    setRevisionLoading(true)
    try {
      const rows = await api.get<GroupMemoryRevision[]>(`/groups/${groupId}/memories/${memory.id}/revisions`)
      setRevisions(rows || [])
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groupMemory.revisionsLoadFailed'), { type: 'error' })
      setRevisions([])
    } finally {
      setRevisionLoading(false)
    }
  }

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate('/admin/groups')}
            className="mb-2 -ml-2"
          >
            {t('groups.backToList')}
          </Button>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('groupMemory.title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {selectedGroup
              ? t('groupMemory.subtitleForGroup', { name: selectedGroup.name })
              : t('groupMemory.subtitle')}
          </p>
        </div>
        <div className="w-64">
          <Select
            label={t('groupMemory.groupLabel')}
            value={groupId}
            options={groups.map((group) => ({ value: group.id, label: group.name }))}
            onChange={(e) => setGroupId(e.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 flex-1 min-h-0">
        <Card>
          <CardHeader>{editing ? t('groupMemory.editTitle') : t('groupMemory.createTitle')}</CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSave}>
              <Select
                label={t('groupMemory.typeLabel')}
                value={form.memory_type}
                options={[
                  { value: 'prompt', label: 'Prompt' },
                  { value: 'playbook', label: 'Playbook' },
                  { value: 'faq', label: 'FAQ' },
                  { value: 'decision', label: 'Decision' },
                  { value: 'example', label: 'Example' },
                ]}
                onChange={(e) => setForm((prev) => ({ ...prev, memory_type: e.target.value }))}
              />
              <Input label={t('groupMemory.titleLabel')} value={form.title} onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))} />
              <Input label={`${t('groupMemory.topicLabel')} (${t('common.optional')})`} value={form.topic} onChange={(e) => setForm((prev) => ({ ...prev, topic: e.target.value }))} placeholder={t('groupMemory.topicPlaceholder')} />
              <Input label={`${t('groupMemory.tagsLabel')} (${t('common.optional')})`} value={form.tags} onChange={(e) => setForm((prev) => ({ ...prev, tags: e.target.value }))} placeholder={t('groupMemory.tagsPlaceholder')} />
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{t('groupMemory.contentLabel')}</label>
                  <div className="flex gap-1 rounded-lg border border-gray-200 dark:border-gray-700 p-1 bg-gray-50 dark:bg-gray-800">
                    <button
                      type="button"
                      className={`px-2 py-1 text-xs rounded ${editorMode === 'edit' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'}`}
                      onClick={() => setEditorMode('edit')}
                    >
                      {t('groupMemory.editorTab')}
                    </button>
                    <button
                      type="button"
                      className={`px-2 py-1 text-xs rounded ${editorMode === 'preview' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'}`}
                      onClick={() => setEditorMode('preview')}
                    >
                      {t('groupMemory.previewTab')}
                    </button>
                  </div>
                </div>
                <MarkdownToolbar
                  textareaRef={textareaRef}
                  value={form.content}
                  onChange={(value) => setForm((prev) => ({ ...prev, content: value }))}
                />
                {editorMode === 'edit' ? (
                  <textarea
                    ref={textareaRef}
                    className="mt-2 w-full min-h-64 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-mono dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                    value={form.content}
                    aria-label={t('groupMemory.contentLabel')}
                    title={t('groupMemory.contentLabel')}
                    placeholder={t('groupMemory.contentPlaceholder')}
                    onChange={(e) => setForm((prev) => ({ ...prev, content: e.target.value }))}
                  />
                ) : (
                  <div className="mt-2 min-h-64 rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 prose prose-sm max-w-none dark:prose-invert">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {form.content || t('groupMemory.previewEmpty')}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
              <Select
                label={t('groupMemory.statusLabel')}
                value={form.status}
                options={[
                  { value: 'draft', label: t('groupMemory.statusDraft') },
                  { value: 'verified', label: t('groupMemory.statusVerified') },
                  { value: 'archived', label: t('groupMemory.statusArchived') },
                ]}
                onChange={(e) => setForm((prev) => ({ ...prev, status: e.target.value }))}
              />
              <div className="flex justify-end gap-2">
                {editing ? <Button type="button" variant="ghost" onClick={openCreate}>{t('common.cancel')}</Button> : null}
                <Button type="submit" isLoading={saving} leftIcon={<Plus className="w-4 h-4" />}>{editing ? t('common.save') : t('groupMemory.createAction')}</Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="min-h-0 flex flex-col">
          <CardHeader>{t('groupMemory.listTitle', { name: selectedGroup?.name || t('groupMemory.listTitleFallback') })}</CardHeader>
          <CardContent className="space-y-3 overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-10"><Spinner size="lg" /></div>
            ) : memories.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('groupMemory.empty')}</p>
            ) : (
              memories.map((memory) => (
                <div key={memory.id} className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">{memory.title}</h3>
                        <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{memory.memory_type}</span>
                        <span className="text-xs px-2 py-0.5 rounded bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300">{memory.status}</span>
                      </div>
                      {memory.topic ? <p className="text-xs text-gray-500 mt-1">{memory.topic}</p> : null}
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-2 whitespace-pre-wrap line-clamp-4">{memory.content}</p>
                      {!!memory.tags?.length && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {memory.tags.map((tag) => (
                            <span key={tag} className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button size="sm" variant="outline" leftIcon={<Clock3 className="w-4 h-4" />} onClick={() => void openRevisions(memory)}>
                        {t('groupMemory.revisions')}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openEdit(memory)}>{t('common.edit')}</Button>
                      <Button size="sm" variant="ghost" leftIcon={<Trash2 className="w-4 h-4" />} onClick={() => void handleDelete(memory)}>{t('common.delete')}</Button>
                    </div>
                  </div>
                  <p className="text-xs text-gray-400">{formatDate(memory.updated_at)}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={!!revisionTarget} onClose={() => setRevisionTarget(null)} title={t('groupMemory.revisionsTitle', { name: revisionTarget?.title || '' })} size="lg">
        {revisionLoading ? (
          <div className="flex justify-center py-10"><Spinner size="lg" /></div>
        ) : revisions.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('groupMemory.revisionsEmpty')}</p>
        ) : (
          <div className="space-y-3">
            {revisions.map((revision) => (
              <div key={revision.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">v{revision.version} · {revision.title}</p>
                  <p className="text-xs text-gray-400">{formatDate(revision.created_at)}</p>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{revision.content}</p>
              </div>
            ))}
          </div>
        )}
      </Dialog>
    </div>
  )
}