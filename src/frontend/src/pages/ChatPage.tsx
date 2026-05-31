import React, { useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Plus } from 'lucide-react'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { AssistantChatSidebar } from '@/components/portal/AssistantChatSidebar'
import { useChat } from '@/hooks/useChat'
import { ChatSendOptions } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { portalApi } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'

const PORTAL_CHANNEL_KEY = 'mchat_portal_channel_id'

function readChannelIdFromUrl(): string | undefined {
  if (typeof window === 'undefined') return undefined
  return new URLSearchParams(window.location.search).get('channel') || undefined
}

export function ChatPage() {
  const { t } = useTranslation()
  const { conversationId } = useParams<{ conversationId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const chat = useChat(conversationId)
  const [startingNewChat, setStartingNewChat] = useState(false)

  const channelFromUrl =
    searchParams.get('channel') || readChannelIdFromUrl() || undefined
  const channelFromStore =
    typeof window !== 'undefined'
      ? sessionStorage.getItem(PORTAL_CHANNEL_KEY) || undefined
      : undefined
  const channelId =
    channelFromUrl ||
    chat.currentConversation?.customer_id ||
    channelFromStore ||
    undefined

  if (channelId && typeof window !== 'undefined') {
    sessionStorage.setItem(PORTAL_CHANNEL_KEY, channelId)
  }

  const isPortalChat = Boolean(channelId)
  const isPortalStudio = user?.role === 'user' && isPortalChat
  const title =
    chat.currentConversation?.title || t('chat.defaultTitle')
  const messageCount =
    chat.currentConversation?.total_message_count ?? chat.messages.length

  const handleSend = (content: string, options?: ChatSendOptions) => {
    if (conversationId) {
      chat.sendMessage(conversationId, content, options)
    }
  }

  const handleNewChat = async () => {
    if (!channelId) return
    setStartingNewChat(true)
    chat.setError(null)
    try {
      const conv = await portalApi.resumeChannelChat(channelId, {
        title: t('portal.newChatTitle', 'New chat'),
        forceNew: true,
      })
      navigate(`/chat/${conv.id}?channel=${channelId}`)
    } catch (e: any) {
      chat.setError(e.message || t('portal.rentFailed'))
    } finally {
      setStartingNewChat(false)
    }
  }

  const backPath = isPortalChat
    ? '/portal/channels'
    : user?.role === 'user'
      ? '/portal/channels'
      : '/admin/conversations'

  return (
    <div className="h-screen flex bg-gray-50 dark:bg-gray-900">
      {isPortalChat && channelId && (
        <AssistantChatSidebar
          channelId={channelId}
          activeConversationId={conversationId}
          channelName={title}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <header className="shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate(backPath)}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title={
              isPortalChat
                ? t('portal.backToAssistants', 'Back to my assistants')
                : t('chat.backToConversations')
            }
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 truncate">
              {title}
            </h1>
            {isPortalChat && (
              <p className="text-xs text-gray-500 truncate">
                {t('portal.chatSubtitle', {
                  count: messageCount,
                  defaultValue: '{{count}} messages',
                })}
              </p>
            )}
          </div>
          {isPortalStudio && channelId && (
            <Button
              onClick={handleNewChat}
              isLoading={startingNewChat}
              size="sm"
              variant="outline"
              className="gap-1 shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              {t('portal.newChat', 'New')}
            </Button>
          )}
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
            disabled={chat.isStreaming}
            loading={chat.isLoading}
            emptyMessage={
              isPortalChat
                ? t(
                    'portal.chatEmpty',
                    'Ask anything — your history is saved for this assistant.',
                  )
                : t('chat.emptyMessage')
            }
            speechConfigUrl="/api/speech/config"
            speechTranscribeUrl="/api/speech/transcribe"
            allowAssistantMode={!isPortalChat}
            allowOutboundLinks={!isPortalChat}
            defaultSendRole="user"
            variant={isPortalChat ? 'studio' : 'default'}
            showGithubLink={!isPortalChat}
            modelCapabilities={chat.currentConversation?.ai_capabilities ?? null}
          />
        </div>
      </div>
    </div>
  )
}
