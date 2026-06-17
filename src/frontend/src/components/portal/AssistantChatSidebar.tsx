import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MessageSquare, Plus, Trash2 } from 'lucide-react'
import api from '@/lib/api'
import { Conversation } from '@/stores/chat'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/Toast'

interface ScopeOption {
  value: string
  label: string
}

interface AssistantChatSidebarProps {
  channelId?: string
  activeConversationId?: string
  channelName?: string
  chatBasePath?: string
  scopeType?: 'personal' | 'group'
  scopeId?: string
  scopeOptions?: ScopeOption[]
  scopeValue?: string
  onScopeChange?: (value: string) => void
}

function buildChatUrl(
  chatBasePath: string,
  conversationId: string,
  channelId?: string,
  scopeType?: 'personal' | 'group',
  scopeId?: string,
): string {
  const params = new URLSearchParams()
  // Group conversations have no channel; never append a stale channel param.
  if (channelId && scopeType !== 'group') params.set('channel', channelId)
  if (scopeType === 'group' && scopeId) {
    params.set('scope', 'group')
    params.set('group', scopeId)
  }
  const query = params.toString()
  return query ? `${chatBasePath}/${conversationId}?${query}` : `${chatBasePath}/${conversationId}`
}

export function AssistantChatSidebar({
  channelId,
  activeConversationId,
  channelName,
  chatBasePath = '/chat',
  scopeType = 'personal',
  scopeId,
  scopeOptions,
  scopeValue,
  onScopeChange,
}: AssistantChatSidebarProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [items, setItems] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<{ items: Conversation[]; total: number }>(
        '/chat/conversations',
        {
          limit: '200',
          scope_type: scopeType,
          ...(scopeId ? { scope_id: scopeId } : {}),
          // Group conversations have customer_id = NULL; sending a stale
          // channel id here would filter them all out of the sidebar.
          ...(channelId && scopeType !== 'group' ? { customer_id: channelId } : {}),
        },
      )
      setItems(data.items || [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [channelId, scopeType, scopeId])

  useEffect(() => {
    load()
  }, [load, activeConversationId])

  const handleDelete = async (conv: Conversation) => {
    if (!window.confirm(t('portal.deleteChatConfirm', 'Delete this conversation?'))) return
    try {
      await api.delete(`/chat/conversations/${conv.id}`)
      if (conv.id === activeConversationId) {
        navigate(buildChatUrl(chatBasePath, 'new', channelId, scopeType, scopeId))
      }
      await load()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.deleteChatFailed'), { type: 'error' })
    }
  }

  const handleNewChat = async () => {
    setCreating(true)
    try {
      let conv: Conversation
      if (scopeType === 'group' && scopeId) {
        conv = await api.post<Conversation>(`/groups/${scopeId}/chat/resume`, {
          title: t('portal.newChatTitle', 'New chat'),
          force_new: true,
        })
      } else {
        conv = await api.post<Conversation>('/chat/conversations', {
          title: t('portal.newChatTitle', 'New chat'),
          customer_id: channelId,
          scope_type: scopeType,
          scope_id: scopeType === 'group' ? scopeId : null,
        })
      }
      await load()
      navigate(buildChatUrl(chatBasePath, conv.id, channelId, scopeType, scopeId))
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.newChatFailed', 'Failed to start chat'), { type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  return (
    <aside className="flex w-56 sm:w-64 lg:w-72 shrink-0 flex-col border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
      <div className="p-3 border-b border-gray-100 dark:border-gray-700">
        {scopeOptions && scopeOptions.length > 1 && onScopeChange && (
          <Select
            className="mb-3"
            value={scopeValue}
            options={scopeOptions}
            onChange={(event) => onScopeChange(event.target.value)}
            aria-label={t('chat.scopeLabel', '聊天作用域')}
          />
        )}
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {t('portal.chatHistory', 'History')}
        </p>
        {channelName && (
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate mt-1">
            {channelName}
          </p>
        )}
        <Button
          type="button"
          size="sm"
          className="w-full mt-3 gap-1.5"
          onClick={handleNewChat}
          isLoading={creating}
        >
          <Plus className="w-4 h-4" />
          {t('portal.newChat', 'New chat')}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading && (
          <div className="flex justify-center py-8">
            <Spinner size="sm" />
          </div>
        )}
        {!loading && items.length === 0 && (
          <p className="text-xs text-gray-400 px-2 py-4 text-center">
            {t('portal.noChatHistory', 'No conversations yet')}
          </p>
        )}
        {items.map((conv) => {
          const active = conv.id === activeConversationId
          const label =
            conv.first_user_message_preview ||
            conv.title ||
            t('portal.untitledChat', 'Untitled')
          return (
            <button
              key={conv.id}
              type="button"
              onClick={() =>
                navigate(buildChatUrl(chatBasePath, conv.id, channelId, scopeType, scopeId))
              }
              className={cn(
                'w-full text-left rounded-lg px-3 py-2.5 text-sm transition-colors flex gap-2 items-start group',
                active
                  ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-800 dark:text-primary-200'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50',
              )}
            >
              <MessageSquare className="w-4 h-4 shrink-0 mt-0.5 opacity-60" />
              <span className="line-clamp-2 leading-snug flex-1">{label}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  handleDelete(conv)
                }}
                title={t('common.delete')}
                className="shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-400 hover:text-red-600 transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
