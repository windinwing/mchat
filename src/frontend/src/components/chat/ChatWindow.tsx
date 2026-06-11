import React, { useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { MessageSquare } from 'lucide-react'
import { GithubLink } from '@/components/common/GithubLink'
import { MessageBubble } from './MessageBubble'
import { ChatInput } from './ChatInput'
import { ChatSendOptions, Message, ModelCapabilities } from '@/stores/chat'
import { attachmentAcceptForCapabilities } from '@/lib/modelCapabilities'
import { cn } from '@/lib/utils'

interface ChatWindowProps {
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
  onSend: (content: string, options?: ChatSendOptions) => void
  onStop: () => void
  title?: string
  emptyMessage?: string
  disabled?: boolean
  loading?: boolean
  accentColor?: string
  headerStyle?: React.CSSProperties
  /** Floating widget: tighter padding, wider assistant bubbles */
  embedded?: boolean
  speechTranscribeUrl?: string
  speechConfigUrl?: string
  showGithubLink?: boolean
  allowAssistantMode?: boolean
  allowOutboundLinks?: boolean
  defaultSendRole?: 'user' | 'assistant'
  /** Kimi/DeepSeek-style centered thread (portal chat) */
  variant?: 'default' | 'studio'
  modelCapabilities?: ModelCapabilities | null
  customerId?: string
}

export function ChatWindow({
  messages,
  isStreaming,
  streamingContent,
  onSend,
  onStop,
  title,
  emptyMessage,
  disabled = false,
  loading = false,
  accentColor,
  headerStyle,
  embedded = false,
  speechTranscribeUrl,
  speechConfigUrl,
  showGithubLink = true,
  allowAssistantMode = false,
  allowOutboundLinks = false,
  defaultSendRole = 'user',
  variant = 'default',
  modelCapabilities = null,
  customerId,
}: ChatWindowProps) {
  const studio = variant === 'studio'
  const embed = embedded && !studio
  const allowAttachments = modelCapabilities?.supports_attachments !== false
  const attachmentAccept = attachmentAcceptForCapabilities(modelCapabilities)
  const { t } = useTranslation()
  const resolvedEmpty = emptyMessage ?? t('chat.emptyStart')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const forceScrollRef = useRef(false)

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: 'end' })
  }

  const handleSend = (content: string, options?: ChatSendOptions) => {
    forceScrollRef.current = true
    onSend(content, options)
    requestAnimationFrame(() => scrollToBottom('auto'))
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container || !messagesEndRef.current) return
    if (forceScrollRef.current) {
      scrollToBottom(isStreaming ? 'auto' : 'smooth')
      if (!isStreaming) forceScrollRef.current = false
      return
    }
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    if (distanceFromBottom < 160) {
      scrollToBottom(isStreaming ? 'auto' : 'smooth')
    }
  }, [messages, streamingContent, isStreaming])

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      {title && (
        <div
          className="shrink-0 border-b border-gray-200 dark:border-gray-700 px-6 py-4 text-white"
          style={headerStyle}
        >
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 opacity-90 shrink-0" />
            <h2 className="text-lg font-semibold flex-1 truncate">{title}</h2>
            {showGithubLink && (
              <GithubLink onDark className="shrink-0 ml-auto" />
            )}
          </div>
        </div>
      )}

      {/* Messages area */}
      <div
        ref={containerRef}
        className={cn(
          'flex-1 overflow-y-auto w-full scrollbar-thin',
          studio ? 'px-4 pt-6 pb-2' : embed ? 'px-2 py-2' : 'px-4 py-6',
        )}
      >
        <div
          className={cn(
            'w-full min-w-0',
            studio && 'mx-auto max-w-3xl space-y-8',
            embed && 'flex flex-col gap-3',
            !studio && !embed && 'flex flex-col gap-4',
          )}
        >
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            {t('chat.loadingHistory')}
          </div>
        ) : messages.length === 0 && !isStreaming ? (
          <div
            className={cn(
              'flex flex-col text-gray-400 dark:text-gray-500',
              embedded
                ? 'items-start pt-2'
                : 'items-center justify-center h-full',
            )}
          >
            <MessageSquare className={cn('opacity-50', embedded ? 'w-8 h-8 mb-2' : 'w-12 h-12 mb-3')} />
            <p className={cn('text-sm', embedded && 'text-left leading-relaxed')}>{resolvedEmpty}</p>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                accentColor={accentColor}
                compact={embedded}
                variant={studio ? 'studio' : 'default'}
                customerId={customerId}
              />
            ))}
            {isStreaming && (
              <MessageBubble
                message={{
                  id: 'streaming',
                  conversation_id: '',
                  role: 'assistant',
                  content: streamingContent,
                  content_type: 'text',
                  created_at: new Date().toISOString(),
                }}
                isStreaming
                streamingContent={streamingContent}
                accentColor={accentColor}
                compact={embedded}
                variant={studio ? 'studio' : 'default'}
                customerId={customerId}
              />
            )}
          </>
        )}
        <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div
        className={cn(
          studio && 'bg-gray-50 dark:bg-gray-900 shrink-0',
          embed && 'shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
          !studio && !embed && 'shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
        )}
      >
        <div
          className={cn(
            studio && 'mx-auto w-full max-w-3xl px-4 pt-3 pb-4',
            embed && 'px-2 py-2',
            !studio && !embed && 'px-4 pt-3 pb-5',
          )}
        >
      <ChatInput
        onSend={handleSend}
        onStop={onStop}
        isStreaming={isStreaming}
        disabled={disabled}
        compact={embed}
        singleLine={embed}
        variant={studio ? 'studio' : embed ? 'embedded' : 'default'}
        speechTranscribeUrl={speechTranscribeUrl}
        speechConfigUrl={speechConfigUrl}
        allowAssistantMode={allowAssistantMode}
        allowOutboundLinks={allowOutboundLinks}
        defaultSendRole={defaultSendRole}
        allowAttachments={allowAttachments}
        attachmentAccept={attachmentAccept}
      />
        </div>
      </div>
    </div>
  )
}
