import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen, ChevronRight, FileText, Pencil, Plus, Trash2, Upload, Users } from 'lucide-react'
import api from '@/lib/api'
import { writeStoredChatScope } from '@/lib/appPreferences'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { MarkdownToolbar } from '@/components/admin/MarkdownToolbar'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface GroupOption {
  id: string
  name: string
  description?: string | null
  member_count?: number
}

interface GroupMemory {
  id: string
  memory_type: string
  title: string
  content: string
  topic?: string | null
  tags?: string[] | null
  status: string
}

interface KnowledgeBaseRow {
  id: string
  name: string
  description?: string | null
  document_count?: number
}

const memoryTypeOptions = [
  { value: 'prompt', label: 'Prompt' },
  { value: 'playbook', label: 'Playbook' },
  { value: 'faq', label: 'FAQ' },
  { value: 'decision', label: 'Decision' },
  { value: 'example', label: 'Example' },
]

export function PortalGroupsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [groups, setGroups] = useState<GroupOption[]>([])
  const [groupId, setGroupId] = useState('')
  const [memories, setMemories] = useState<GroupMemory[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseRow[]>([])
  const [loading, setLoading] = useState(true)
  const [creatingKb, setCreatingKb] = useState(false)
  const [newKbName, setNewKbName] = useState('')
  const [uploadingKbId, setUploadingKbId] = useState<string | null>(null)
  const [memoryDialogOpen, setMemoryDialogOpen] = useState(false)
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null)
  const [savingMemory, setSavingMemory] = useState(false)
  const [memoryMode, setMemoryMode] = useState<'edit' | 'preview'>('edit')
  const [memoryForm, setMemoryForm] = useState({
    memory_type: 'prompt',
    title: '',
    content: '',
    topic: '',
    tags: '',
    status: 'draft',
  })
  const memoryTextareaRef = useRef<HTMLTextAreaElement | null>(null)
  const kbFileInputRefs = useRef<Record<string, HTMLInputElement | null>>({})

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === groupId) || null,
    [groups, groupId],
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const rows = await api.get<GroupOption[]>('/groups/mine')
        if (cancelled) return
        setGroups(rows || [])
        if ((rows || []).length > 0) {
          setGroupId((current) => current || rows[0].id)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!groupId) {
      setMemories([])
      setKnowledgeBases([])
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        const [memoryRows, kbRows] = await Promise.all([
          api.get<GroupMemory[]>(`/groups/${groupId}/memories`),
          api.get<KnowledgeBaseRow[]>('/knowledge/bases', { group_id: groupId }),
        ])
        if (cancelled) return
        setMemories(memoryRows || [])
        setKnowledgeBases(kbRows || [])
      } catch {
        if (cancelled) return
        setMemories([])
        setKnowledgeBases([])
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [groupId])

  const openGroupChat = () => {
    if (!groupId) return
    writeStoredChatScope(user?.role, { type: 'group', groupId })
    navigate('/chat')
  }

  const reloadGroupAssets = async (targetGroupId: string) => {
    const [memoryRows, kbRows] = await Promise.all([
      api.get<GroupMemory[]>(`/groups/${targetGroupId}/memories`),
      api.get<KnowledgeBaseRow[]>('/knowledge/bases', { group_id: targetGroupId }),
    ])
    setMemories(memoryRows || [])
    setKnowledgeBases(kbRows || [])
  }

  const handleCreateKnowledgeBase = async () => {
    if (!groupId || !newKbName.trim()) return
    setCreatingKb(true)
    try {
      await api.post('/knowledge/bases', {
        name: newKbName.trim(),
        group_id: groupId,
      })
      setNewKbName('')
      toast(t('portal.groupKnowledgeCreated', '群组知识库已创建'), { type: 'success' })
      await reloadGroupAssets(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.groupKnowledgeCreateFailed', '创建群组知识库失败'), { type: 'error' })
    } finally {
      setCreatingKb(false)
    }
  }

  const handleUploadKnowledgeFile = async (kbId: string, file?: File) => {
    if (!groupId || !file) return
    setUploadingKbId(kbId)
    try {
      const form = new FormData()
      form.append('file', file)
      await api.upload(`/knowledge/bases/${kbId}/import-file`, form)
      toast(t('portal.groupKnowledgeUploaded', '文档已上传'), { type: 'success' })
      await reloadGroupAssets(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.groupKnowledgeUploadFailed', '上传群组知识文档失败'), { type: 'error' })
    } finally {
      setUploadingKbId(null)
      if (kbFileInputRefs.current[kbId]) {
        kbFileInputRefs.current[kbId]!.value = ''
      }
    }
  }

  const openCreateMemory = () => {
    setEditingMemoryId(null)
    setMemoryMode('edit')
    setMemoryForm({
      memory_type: 'prompt',
      title: '',
      content: '',
      topic: '',
      tags: '',
      status: 'draft',
    })
    setMemoryDialogOpen(true)
  }

  const openEditMemory = (memory: GroupMemory) => {
    setEditingMemoryId(memory.id)
    setMemoryMode('edit')
    setMemoryForm({
      memory_type: memory.memory_type,
      title: memory.title,
      content: memory.content,
      topic: memory.topic || '',
      tags: (memory.tags || []).join(', '),
      status: memory.status,
    })
    setMemoryDialogOpen(true)
  }

  const handleSaveMemory = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!groupId) return
    setSavingMemory(true)
    const payload = {
      memory_type: memoryForm.memory_type,
      title: memoryForm.title.trim(),
      content: memoryForm.content.trim(),
      topic: memoryForm.topic.trim() || null,
      tags: memoryForm.tags
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      status: memoryForm.status,
    }
    try {
      if (editingMemoryId) {
        await api.patch(`/groups/${groupId}/memories/${editingMemoryId}`, payload)
      } else {
        await api.post(`/groups/${groupId}/memories`, payload)
      }
      setMemoryDialogOpen(false)
      toast(t('portal.groupMemorySaved', '群组记忆已保存'), { type: 'success' })
      await reloadGroupAssets(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.groupMemorySaveFailed', '保存群组记忆失败'), { type: 'error' })
    } finally {
      setSavingMemory(false)
    }
  }

  const handleDeleteMemory = async (memory: GroupMemory) => {
    if (!groupId) return
    if (!window.confirm(t('portal.groupMemoryDeleteConfirm', { name: memory.title, defaultValue: `确定删除记忆 ${memory.title}？` }))) {
      return
    }
    try {
      await api.delete(`/groups/${groupId}/memories/${memory.id}`)
      toast(t('portal.groupMemoryDeleted', '群组记忆已删除'), { type: 'success' })
      await reloadGroupAssets(groupId)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.groupMemoryDeleteFailed', '删除群组记忆失败'), { type: 'error' })
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-none">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            {t('portal.groupsTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('portal.groupsSubtitle')}
          </p>
        </div>
        {groups.length > 0 && (
          <div className="w-72 max-w-full">
            <Select
              label={t('portal.groupSelectLabel')}
              value={groupId}
              options={groups.map((group) => ({ value: group.id, label: group.name }))}
              onChange={(e) => setGroupId(e.target.value)}
            />
          </div>
        )}
      </div>

      {groups.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center space-y-2">
            <Users className="w-10 h-10 mx-auto text-gray-300 dark:text-gray-600" />
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('portal.groupsEmpty')}</p>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto leading-relaxed">
              {t('portal.groupsInviteOnlyHint')}
            </p>
          </CardContent>
        </Card>
      ) : !selectedGroup ? (
        <Card>
          <CardContent>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.groupsEmpty')}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="py-5 flex items-center justify-between gap-4 flex-wrap">
              <div>
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-gray-400" />
                  <h2 className="font-semibold text-gray-900 dark:text-gray-100">{selectedGroup.name}</h2>
                </div>
                {selectedGroup.description ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{selectedGroup.description}</p>
                ) : null}
              </div>
              <Button onClick={openGroupChat} rightIcon={<ChevronRight className="w-4 h-4" />}>
                {t('portal.openGroupChat')}
              </Button>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <Card>
              <CardHeader>{t('portal.groupKnowledgeTitle')}</CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2 items-end flex-wrap">
                  <div className="flex-1 min-w-[14rem]">
                    <Input
                      label={t('portal.groupKnowledgeNameLabel', '新知识库名称')}
                      value={newKbName}
                      onChange={(e) => setNewKbName(e.target.value)}
                    />
                  </div>
                  <Button isLoading={creatingKb} leftIcon={<Plus className="w-4 h-4" />} onClick={handleCreateKnowledgeBase}>
                    {t('common.create')}
                  </Button>
                </div>
                {knowledgeBases.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.groupKnowledgeEmpty')}</p>
                ) : (
                  knowledgeBases.map((kb) => (
                    <div key={kb.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <div className="flex items-center gap-2">
                        <BookOpen className="w-4 h-4 text-gray-400" />
                        <p className="font-medium text-gray-900 dark:text-gray-100">{kb.name}</p>
                      </div>
                      {kb.description ? <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{kb.description}</p> : null}
                      <p className="text-xs text-gray-400 mt-2">{t('portal.groupKnowledgeDocCount', { count: kb.document_count || 0 })}</p>
                      <div className="mt-3">
                        <input
                          ref={(el) => {
                            kbFileInputRefs.current[kb.id] = el
                          }}
                          type="file"
                          className="hidden"
                          aria-label={t('portal.uploadDocument', 'Upload')}
                          title={t('portal.uploadDocument', 'Upload')}
                          accept=".txt,.md,.pdf,.docx,.html"
                          onChange={(e) => handleUploadKnowledgeFile(kb.id, e.target.files?.[0])}
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          leftIcon={<Upload className="w-4 h-4" />}
                          isLoading={uploadingKbId === kb.id}
                          onClick={() => kbFileInputRefs.current[kb.id]?.click()}
                        >
                          {t('portal.uploadDocument', 'Upload')}
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <span>{t('portal.groupMemoryTitle')}</span>
                  <Button size="sm" leftIcon={<Plus className="w-4 h-4" />} onClick={openCreateMemory}>
                    {t('portal.groupMemoryCreate', '新建记忆')}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {memories.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.groupMemoryEmpty')}</p>
                ) : (
                  memories.map((memory) => (
                    <div key={memory.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                          <p className="font-medium text-gray-900 dark:text-gray-100 truncate">{memory.title}</p>
                          <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-200">{memory.memory_type}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Button size="sm" variant="ghost" leftIcon={<Pencil className="w-4 h-4" />} onClick={() => openEditMemory(memory)}>
                            {t('common.edit')}
                          </Button>
                          <Button size="sm" variant="ghost" leftIcon={<Trash2 className="w-4 h-4" />} onClick={() => void handleDeleteMemory(memory)}>
                            {t('common.delete')}
                          </Button>
                        </div>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-2 whitespace-pre-wrap line-clamp-4">{memory.content}</p>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <Dialog open={memoryDialogOpen} onClose={() => setMemoryDialogOpen(false)} title={editingMemoryId ? t('portal.groupMemoryEditTitle', '编辑群组记忆') : t('portal.groupMemoryCreateTitle', '新建群组记忆')} size="lg">
            <form className="space-y-4" onSubmit={handleSaveMemory}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Select
                  label={t('groupMemory.typeLabel')}
                  value={memoryForm.memory_type}
                  options={memoryTypeOptions}
                  onChange={(e) => setMemoryForm((prev) => ({ ...prev, memory_type: e.target.value }))}
                />
                <Select
                  label={t('groupMemory.statusLabel')}
                  value={memoryForm.status}
                  options={[
                    { value: 'draft', label: t('groupMemory.statusDraft') },
                    { value: 'verified', label: t('groupMemory.statusVerified') },
                    { value: 'archived', label: t('groupMemory.statusArchived') },
                  ]}
                  onChange={(e) => setMemoryForm((prev) => ({ ...prev, status: e.target.value }))}
                />
              </div>
              <Input label={t('groupMemory.titleLabel')} value={memoryForm.title} onChange={(e) => setMemoryForm((prev) => ({ ...prev, title: e.target.value }))} />
              <Input label={`${t('groupMemory.topicLabel')} (${t('common.optional')})`} value={memoryForm.topic} onChange={(e) => setMemoryForm((prev) => ({ ...prev, topic: e.target.value }))} placeholder={t('groupMemory.topicPlaceholder')} />
              <Input label={`${t('groupMemory.tagsLabel')} (${t('common.optional')})`} value={memoryForm.tags} onChange={(e) => setMemoryForm((prev) => ({ ...prev, tags: e.target.value }))} placeholder={t('groupMemory.tagsPlaceholder')} />
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{t('groupMemory.contentLabel')}</label>
                  <div className="flex gap-1 rounded-lg border border-gray-200 dark:border-gray-700 p-1 bg-gray-50 dark:bg-gray-800">
                    <button type="button" className={`px-2 py-1 text-xs rounded ${memoryMode === 'edit' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'}`} onClick={() => setMemoryMode('edit')}>{t('groupMemory.editorTab')}</button>
                    <button type="button" className={`px-2 py-1 text-xs rounded ${memoryMode === 'preview' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'}`} onClick={() => setMemoryMode('preview')}>{t('groupMemory.previewTab')}</button>
                  </div>
                </div>
                <MarkdownToolbar
                  textareaRef={memoryTextareaRef}
                  value={memoryForm.content}
                  onChange={(value) => setMemoryForm((prev) => ({ ...prev, content: value }))}
                />
                {memoryMode === 'edit' ? (
                  <textarea
                    ref={memoryTextareaRef}
                    className="mt-2 w-full min-h-64 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-mono dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                    value={memoryForm.content}
                    aria-label={t('groupMemory.contentLabel')}
                    title={t('groupMemory.contentLabel')}
                    placeholder={t('groupMemory.contentPlaceholder')}
                    onChange={(e) => setMemoryForm((prev) => ({ ...prev, content: e.target.value }))}
                  />
                ) : (
                  <div className="mt-2 min-h-64 rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 prose prose-sm max-w-none dark:prose-invert">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {memoryForm.content || t('groupMemory.previewEmpty')}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setMemoryDialogOpen(false)}>{t('common.cancel')}</Button>
                <Button type="submit" isLoading={savingMemory}>{t('common.save')}</Button>
              </div>
            </form>
          </Dialog>
        </>
      )}
    </div>
  )
}