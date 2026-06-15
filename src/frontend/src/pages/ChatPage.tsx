import React, { useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { AppModeSwitch } from '@/components/common/AppModeSwitch'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { AssistantChatSidebar } from '@/components/portal/AssistantChatSidebar'
import { useChat } from '@/hooks/useChat'
import { ChatSendOptions } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { portalApi } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { ToastContainer } from '@/components/ui/Toast'
import api from '@/lib/api'
import { isCloudEdition } from '@/lib/edition'
import {
  readStoredChannelId,
  getPreferredStaffMode,
  readStoredChatScope,
  setPreferredStaffMode,
  writeStoredChannelId,
  writeStoredChatScope,
} from '@/lib/appPreferences'

interface GroupOption {
  id: string
  name: string
}

function readChannelIdFromUrl(): string | undefined {
  if (typeof window === 'undefined') return undefined
  return new URLSearchParams(window.location.search).get('channel') || undefined
}

export function ChatPage() {
  const { t } = useTranslation()
  const { conversationId } = useParams<{ conversationId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user, isAuthenticated } = useAuthStore()
  const chat = useChat(conversationId)
  const [startingNewChat, setStartingNewChat] = useState(false)
  const [groupOptions, setGroupOptions] = useState<GroupOption[]>([])

  const channelFromUrl =
    searchParams.get('channel') || readChannelIdFromUrl() || undefined
  const channelFromStore =
    typeof window !== 'undefined' ? readStoredChannelId(user?.role) : undefined
  const scopeFromUrl = searchParams.get('scope') || undefined
  const groupFromUrl = searchParams.get('group') || undefined
  const storedScope = readStoredChatScope(user?.role)
  const scopeType =
    scopeFromUrl === 'group'
      ? 'group'
      : chat.currentConversation?.scope_type === 'group'
        ? 'group'
        : storedScope.type
  const scopeId =
    groupFromUrl ||
    chat.currentConversation?.scope_id ||
    storedScope.groupId ||
    undefined
  const isGroupChat = scopeType === 'group' && Boolean(scopeId)
  // Group conversations never carry a customer_id. A stale personal channel
  // lingering in sessionStorage must not leak into the group sidebar query,
  // otherwise the backend filters out every group conversation (customer_id IS NULL).
  const channelId = isGroupChat
    ? undefined
    : channelFromUrl || chat.currentConversation?.customer_id || channelFromStore || undefined

  if (channelId) writeStoredChannelId(user?.role, channelId)

  const isPortalUser = user?.role === 'user'
  const hasChannel = Boolean(channelId)
  const showStudioChat = hasChannel || isGroupChat
  const groupName =
    isGroupChat && scopeId
      ? groupOptions.find((group) => group.id === scopeId)?.name
      : undefined
  const title =
    groupName || chat.currentConversation?.title || t('chat.defaultTitle')
  const messageCount =
    chat.currentConversation?.total_message_count ?? chat.messages.length
  const showModeSwitch =
    user?.role === 'agent' ||
    user?.role === 'admin' ||
    (isPortalUser && isCloudEdition) ||
    (isAuthenticated && !user && getPreferredStaffMode() === 'chat')

  React.useEffect(() => {
    if (user?.role === 'agent' || user?.role === 'admin') {
      setPreferredStaffMode('chat')
    }
  }, [user?.role])

  React.useEffect(() => {
    api
      .get<Array<{ id: string; name: string }>>('/groups/mine')
      .then((rows) => setGroupOptions(rows || []))
      .catch(() => setGroupOptions([]))
  }, [])

  // Listen for action links in chat messages (generic, not skill-specific)
  React.useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as string
      if (detail && conversationId) {
        handleSend(detail)
      }
    }
    window.addEventListener('mchat:action', handler)
    return () => window.removeEventListener('mchat:action', handler)
  }, [conversationId, chat.isStreaming])

  const handleSend = (content: string, options?: ChatSendOptions) => {
    if (conversationId) {
      chat.sendMessage(conversationId, content, options)
    }
  }

  const buildChatUrl = (convId: string) => {
    const params = new URLSearchParams()
    if (channelId) params.set('channel', channelId)
    if (isGroupChat && scopeId) {
      params.set('scope', 'group')
      params.set('group', scopeId)
    }
    const query = params.toString()
    return query ? `/chat/${convId}?${query}` : `/chat/${convId}`
  }

  const handleNewChat = async () => {
    if (!showStudioChat) return
    setStartingNewChat(true)
    chat.setError(null)
    try {
      let conv: { id: string }
      if (isGroupChat && scopeId) {
        conv = await api.post<{ id: string }>(`/groups/${scopeId}/chat/resume`, {
          title: t('portal.newChatTitle', 'New chat'),
          force_new: true,
        })
      } else if (channelId) {
        conv =
          isPortalUser && isCloudEdition
            ? await portalApi.resumeChannelChat(channelId, {
                title: t('portal.newChatTitle', 'New chat'),
                forceNew: true,
              })
            : await api.post<{ id: string }>('/chat/conversations/resume', {
                customer_id: channelId,
                title: t('portal.newChatTitle', 'New chat'),
                force_new: true,
                scope_type: scopeType,
                scope_id: scopeType === 'group' ? scopeId || null : null,
              })
      } else {
        return
      }
      navigate(buildChatUrl(conv.id))
    } catch (e: any) {
      chat.setError(e.message || t('portal.rentFailed'))
    } finally {
      setStartingNewChat(false)
    }
  }

  const handleStop = () => {
    chat.endStream()
  }

  const handleScopeChange = (value: string) => {
    if (value === 'personal') {
      writeStoredChatScope(user?.role, { type: 'personal' })
      navigate('/chat')
      return
    }
    const [, groupId] = value.split(':')
    writeStoredChatScope(user?.role, { type: 'group', groupId })
    navigate('/chat')
  }

  return (
    <div className="h-screen flex bg-gray-50 dark:bg-gray-900">
      {showStudioChat && (
        <AssistantChatSidebar
          channelId={channelId}
          activeConversationId={conversationId}
          channelName={title}
          chatBasePath="/chat"
          scopeType={scopeType}
          scopeId={scopeId}
          scopeOptions={[
            { value: 'personal', label: t('chat.scopePersonal', '个人空间') },
            ...groupOptions.map((group) => ({
              value: `group:${group.id}`,
              label: `${t('chat.scopeGroup', '群组')}: ${group.name}`,
            })),
          ]}
          scopeValue={
            scopeType === 'group' && scopeId ? `group:${scopeId}` : 'personal'
          }
          onScopeChange={handleScopeChange}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <header className="shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center gap-3">
          {showModeSwitch && (
            <div className="shrink-0">
              <AppModeSwitch
                variant={isPortalUser ? 'portal' : 'agent'}
                active="chat"
              />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 truncate">
              {title}
            </h1>
            {showStudioChat && (
              <p className="text-xs text-gray-500 truncate">
                {t('portal.chatSubtitle', {
                  count: messageCount,
                  defaultValue: '{{count}} messages',
                })}
              </p>
            )}
          </div>
          <LanguageSwitcher variant="ghost" />
        </header>

        {chat.error && (
          <div className="shrink-0 mx-4 mt-2 px-4 py-2 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
            {chat.error}
            <button
              onClick={() => chat.setError(null)}
              className="ml-2 underline hover:no-underline"
            >
              {t('common.close')}
            </button>
          </div>
        )}

        <div className="flex-1 min-h-0 w-full">
          <ChatWindow
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            streamingContent={chat.streamingContent}
            onSend={handleSend}
            onStop={handleStop}
            disabled={chat.isStreaming}
            loading={chat.isLoading}
            emptyMessage={
              showStudioChat
                ? t(
                    'portal.chatEmpty',
                    'Ask anything — your history is saved for this assistant.',
                  )
                : t('chat.emptyMessage')
            }
            speechConfigUrl="/api/speech/config"
            speechTranscribeUrl="/api/speech/transcribe"
            allowAssistantMode={!showStudioChat}
            allowOutboundLinks={!showStudioChat}
            defaultSendRole="user"
            variant={showStudioChat ? 'studio' : 'default'}
            showGithubLink={!showStudioChat}
            modelCapabilities={chat.currentConversation?.ai_capabilities ?? null}
            customerId={channelId}
          />
        </div>
      </div>
      <ToastContainer />
    </div>
  )
}
