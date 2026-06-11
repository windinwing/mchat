import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, MessageSquare, RotateCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Conversation, Message } from '@/stores/chat'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Dialog } from '@/components/ui/Dialog'
import { formatDate, parseDate, truncate } from '@/lib/utils'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { MessageBubble } from '@/components/chat/MessageBubble'
import { normalizeMessageMedia } from '@/lib/mediaUrl'

interface ConversationListProps {
  onSelect?: (conversation: Conversation) => void
  onStatsChange?: (stats: ConversationStats) => void
}

export interface ConversationStats {
  total: number
  active: number
  closed: number
}

export function ConversationList({ onSelect, onStatsChange }: ConversationListProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyConversation, setHistoryConversation] = useState<Conversation | null>(null)
  const [historyMessages, setHistoryMessages] = useState<Message[]>([])

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('conversations.statusAll') },
      { value: 'active', label: t('conversations.statusActive') },
      { value: 'closed', label: t('conversations.statusClosed') },
    ],
    [t],
  )

  const statusLabels = useMemo(
    (): Record<string, { label: string; variant: 'success' | 'warning' | 'default' }> => ({
      active: { label: t('conversations.statusActive'), variant: 'success' },
      closed: { label: t('conversations.statusClosed'), variant: 'default' },
    }),
    [t],
  )

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  useEffect(() => {
    loadConversations()
  }, [page, pageSize, statusFilter, search])

  const loadConversations = async (showLoading = true) => {
    if (showLoading) {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    try {
      const params = new URLSearchParams()
      params.set('skip', String((page - 1) * pageSize))
      params.set('limit', String(pageSize))
      if (statusFilter) {
        params.set('status_filter', statusFilter)
      }
      if (search.trim()) {
        params.set('search', search.trim())
      }

      const [data, stats] = await Promise.all([
        api.get<{ items: Conversation[]; total: number }>(`/chat/conversations?${params.toString()}`),
        api.get<ConversationStats>('/chat/conversations/stats'),
      ])

      const totalCount = data.total || 0
      const maxPage = Math.max(1, Math.ceil(totalCount / pageSize))
      if (page > maxPage) {
        setPage(maxPage)
        return
      }

      setConversations(data.items || [])
      setTotal(totalCount)
      onStatsChange?.(stats)
    } catch (err) {
      console.error('Failed to load conversations:', err)
    } finally {
      if (showLoading) {
        setLoading(false)
      } else {
        setRefreshing(false)
      }
    }
  }

  const handleRefresh = async () => {
    await loadConversations(false)
  }

  const handleApplySearch = () => {
    const nextSearch = searchInput.trim()
    if (nextSearch === search) {
      return
    }
    setPage(1)
    setSearch(nextSearch)
  }

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      const conv = await api.post<Conversation>('/chat/conversations', { title: newTitle.trim() })
      toast(t('conversations.toastCreateSuccess'), { type: 'success' })
      setShowCreate(false)
      setNewTitle('')
      setPage(1)
      navigate(`/chat/${conv.id}`)
    } catch (err: any) {
      toast(t('conversations.toastCreateFailed'), { type: 'error', message: err.message })
    } finally {
      setCreating(false)
    }
  }

  const openHistory = async (conv: Conversation) => {
    setHistoryOpen(true)
    setHistoryLoading(true)
    setHistoryConversation(conv)
    try {
      const detail = await api.get<Conversation & { messages?: Message[] }>(`/chat/conversations/${conv.id}`)
      setHistoryMessages((detail.messages || []).map(normalizeMessageMedia))
      setHistoryConversation(detail)
    } catch (err: any) {
      toast(t('conversations.toastLoadHistoryFailed'), { type: 'error', message: err?.message })
      setHistoryMessages([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleCloseConversation = async (convId: string) => {
    try {
      await api.post(`/chat/conversations/${convId}/close`)
      toast(t('conversations.toastCloseSuccess'), { type: 'success' })
      await loadConversations()
      if (historyConversation?.id === convId) {
        setHistoryOpen(false)
      }
    } catch (err: any) {
      toast(t('conversations.toastCloseFailed'), { type: 'error', message: err?.message })
    }
  }

  const filtered = [...conversations].sort(
    (a, b) =>
      parseDate(b.updated_at || b.created_at).getTime() -
      parseDate(a.updated_at || a.created_at).getTime(),
  )

  const typeLabel = (type?: string) => {
    if (type === 'widget') return t('conversations.typeWidget')
    if (type === 'wechat') return t('conversations.typeWechat')
    if (type === 'visitor') return t('conversations.typeVisitor')
    if (type === 'admin') return t('conversations.typeAdmin')
    return t('conversations.typeChat')
  }

  const scopeLabel = (conv: Conversation) => {
    if (conv.scope_type === 'group') {
      return conv.scope_name
        ? t('conversations.scopeGroupNamed', { name: conv.scope_name })
        : t('conversations.scopeGroup')
    }
    return t('conversations.scopePersonal')
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="md" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <Input
            placeholder={t('conversations.searchPlaceholder')}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
              if (e.key === 'Enter') {
                handleApplySearch()
              }
            }}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <Button
          variant="outline"
          size="action"
          leftIcon={<Search className="w-4 h-4" />}
          onClick={handleApplySearch}
        >
          {t('common.search')}
        </Button>
        <div className="w-40">
          <Select
            options={statusOptions}
            value={statusFilter}
            onChange={(e: any) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            placeholder={t('conversations.statusAll')}
          />
        </div>
        <Button
          variant="secondary"
          size="action"
          leftIcon={<RotateCw className="w-4 h-4" />}
          onClick={handleRefresh}
          isLoading={refreshing}
        >
          {t('common.refresh')}
        </Button>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent>
            <div className="flex flex-col items-center justify-center py-12 text-gray-400">
              <MessageSquare className="w-12 h-12 mb-3 opacity-50" />
              <p className="text-sm mb-4">{t('conversations.emptyList')}</p>
              <Button variant="outline" onClick={() => setShowCreate(true)}>
                {t('conversations.createFirst')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {filtered.map((conv) => {
            const userCount = conv.user_message_count ?? 0
            const aiCount = conv.ai_message_count ?? 0
            const totalCount = conv.total_message_count ?? userCount + aiCount

            return (
            <Card
              key={conv.id}
              hover
              onClick={() => onSelect?.(conv)}
            >
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="default" size="sm">
                          {typeLabel(conv.conversation_type)}
                        </Badge>
                        <Badge variant={conv.scope_type === 'group' ? 'warning' : 'info'} size="sm">
                          {scopeLabel(conv)}
                        </Badge>
                        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {conv.title || conv.visitor_id || t('conversations.untitled')}
                        </h3>
                        <Badge
                          variant={statusLabels[conv.status]?.variant || 'default'}
                          size="sm"
                        >
                          {statusLabels[conv.status]?.label || conv.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        {conv.username && (
                          <span className="text-xs text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/30 px-1.5 py-0.5 rounded">
                            {conv.username}
                          </span>
                        )}
                        {conv.contact_info && (
                          <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                            {truncate(conv.contact_info, 30)}
                          </span>
                        )}
                      </div>
                      {conv.first_user_message_preview && (
                        <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 truncate">
                          {conv.first_user_message_preview}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 ml-4">
                    {conv.visitor_id && (
                      <span className="text-xs text-gray-400 font-mono">
                        {conv.visitor_id.slice(0, 12)}…
                      </span>
                    )}
                    {conv.client_ip && (
                      <span className="text-xs text-blue-600 dark:text-blue-400 whitespace-nowrap">
                        {t('conversations.ipTag', { ip: conv.client_ip })}
                      </span>
                    )}
                    <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {t('conversations.messageCountSummary', {
                        user: userCount,
                        ai: aiCount,
                        total: totalCount,
                      })}
                    </span>
                    <span className="text-xs text-gray-400 whitespace-nowrap">
                      {formatDate(conv.updated_at || conv.created_at)}
                    </span>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation()
                          openHistory(conv)
                        }}
                      >
                        {t('conversations.viewHistory')}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/chat/${conv.id}`)
                        }}
                      >
                        {t('conversations.openChat')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleCloseConversation(conv.id)
                        }}
                        disabled={conv.status === 'closed'}
                      >
                        {t('conversations.closeConversation')}
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
            )
          })}
        </div>
      )}

      {total > 0 && (
        <div className="flex items-center justify-between pt-1">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t('conversations.pageSummary', {
              current: page,
              totalPages,
              total,
            })}
          </p>
          <div className="flex items-center gap-2">
            <div className="w-24">
              <Select
                value={String(pageSize)}
                options={[
                  { value: '20', label: '20' },
                  { value: '50', label: '50' },
                  { value: '100', label: '100' },
                ]}
                onChange={(e: any) => {
                  setPageSize(parseInt(e.target.value, 10))
                  setPage(1)
                }}
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              {t('conversations.prevPage')}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              {t('conversations.nextPage')}
            </Button>
          </div>
        </div>
      )}

      <Dialog
        open={showCreate}
        onClose={() => { setShowCreate(false); setNewTitle('') }}
        title={t('conversations.dialogCreateTitle')}
      >
        <div className="space-y-4 pt-2">
          <Input
            label={t('conversations.titleLabel')}
            value={newTitle}
            onChange={(e: any) => setNewTitle(e.target.value)}
            placeholder={t('conversations.titlePlaceholder')}
            onKeyDown={(e: any) => e.key === 'Enter' && handleCreate()}
          />
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={() => { setShowCreate(false); setNewTitle('') }}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreate} isLoading={creating} disabled={!newTitle.trim()}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={historyOpen}
        onClose={() => {
          setHistoryOpen(false)
          setHistoryMessages([])
          setHistoryConversation(null)
        }}
        title={historyConversation?.title || t('conversations.historyTitle')}
        size="xl"
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-center gap-3">
              <span>{t('conversations.historyConversationId', { id: historyConversation?.id || '-' })}</span>
              {historyConversation?.client_ip && (
                <span>{t('conversations.ipTag', { ip: historyConversation.client_ip })}</span>
              )}
            </div>
            <span>{t('conversations.historyMessageCount', { count: historyMessages.length })}</span>
          </div>

          {historyLoading ? (
            <div className="flex items-center justify-center py-10">
              <Spinner size="md" />
            </div>
          ) : historyMessages.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-6 text-center">
              {t('conversations.emptyHistory')}
            </p>
          ) : (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {historyMessages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} compact />
              ))}
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
