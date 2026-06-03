import React, { useCallback, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Minus, MessageCircle, Loader2, Maximize2, Minimize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useWidgetConfig } from '@/hooks/useWidgetConfig'
import { useWidgetChat } from '@/hooks/useWidgetChat'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { WidgetButton } from './WidgetButton'
import { PreChatForm } from './PreChatForm'
import { GithubLink } from '@/components/common/GithubLink'

const PRECHAT_KEY_PREFIX = 'mchat_prechat_done_'

interface WidgetProps {
  agentId: string
  apiUrl: string
  wsUrl: string
  variant?: 'floating' | 'page' | 'iframe'
  defaultOpen?: boolean
  position?: 'right' | 'left'
  primaryColor?: string
  welcomeMessage?: string
  botName?: string
  skillId?: string
  launcherIcon?: string
  launcherText?: string
  themeOverride?: {
    position?: 'right' | 'left'
    primaryColor?: string
    welcomeMessage?: string
    botName?: string
    launcherIcon?: string
    launcherText?: string
  }
}

export function Widget({
  agentId,
  apiUrl,
  wsUrl: _wsUrl,
  variant = 'floating',
  defaultOpen = false,
  position = 'right',
  primaryColor = '#3b82f6',
  welcomeMessage,
  botName,
  skillId,
  launcherIcon = 'chat',
  launcherText = '',
  themeOverride,
}: WidgetProps) {
  const { t } = useTranslation()
  const isPage = variant === 'page'
  const isIframe = variant === 'iframe'
  const defaultWelcome = welcomeMessage ?? t('customerAgents.defaultWelcome')
  const defaultBotName = botName ?? t('customerAgents.defaultBotName')
  const { config: remoteConfig, loading: configLoading, error: configError } =
    useWidgetConfig(agentId, apiUrl)

  const resolved = useMemo(
    () => ({
      position:
        themeOverride?.position ??
        (remoteConfig?.position as 'right' | 'left') ??
        position,
      primaryColor:
        themeOverride?.primaryColor ??
        remoteConfig?.theme?.primaryColor ??
        primaryColor,
      welcomeMessage:
        themeOverride?.welcomeMessage ??
        remoteConfig?.welcome_message ??
        defaultWelcome,
      botName:
        themeOverride?.botName ??
        remoteConfig?.theme?.botName ??
        defaultBotName,
      launcherIcon:
        themeOverride?.launcherIcon ??
        remoteConfig?.theme?.launcherIcon ??
        launcherIcon,
      launcherText:
        themeOverride?.launcherText ??
        remoteConfig?.theme?.launcherText ??
        launcherText,
      subscriptionActive: remoteConfig?.subscription_active !== false,
      offlineNotice:
        remoteConfig?.subscription_active === false
          ? remoteConfig?.offline_message ||
            t('portal.subscriptionExpiredWidget', '订阅已到期，暂无法对话。')
          : null,
    }),
    [
      remoteConfig,
      t,
      position,
      primaryColor,
      defaultWelcome,
      defaultBotName,
      launcherIcon,
      launcherText,
      themeOverride,
    ],
  )

  const chat = useWidgetChat(agentId, apiUrl, resolved.welcomeMessage, skillId)

  const preChatFields = remoteConfig?.pre_chat_fields?.filter((f) => f?.key && f?.label) || []
  const preChatStorageKey = `${PRECHAT_KEY_PREFIX}${agentId}${skillId ? `:${skillId}` : ''}`
  const [preChatDone, setPreChatDone] = useState(true)

  React.useEffect(() => {
    if (!preChatFields.length) {
      setPreChatDone(true)
      return
    }
    setPreChatDone(localStorage.getItem(preChatStorageKey) === '1')
  }, [preChatFields.length, preChatStorageKey])

  const [isOpen, setIsOpen] = useState(isPage || isIframe || defaultOpen)

  const [isMinimized, setIsMinimized] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [widgetWidth, setWidgetWidth] = useState<number | null>(null)
  const resizeRef = useRef<{ startX: number; startW: number; edge: 'left' | 'right' } | null>(null)

  const handleResizeStart = useCallback((e: React.MouseEvent, edge: 'left' | 'right') => {
    e.preventDefault()
    e.stopPropagation()
    const panel = (e.currentTarget as HTMLElement).closest('[data-widget-panel]') as HTMLElement | null
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    resizeRef.current = { startX: e.clientX, startW: rect.width, edge }

    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return
      const dx = ev.clientX - resizeRef.current.startX
      const delta = resizeRef.current.edge === 'right' ? dx : -dx
      const newW = Math.max(300, Math.min(window.innerWidth - 32, resizeRef.current.startW + delta))
      setWidgetWidth(newW)
    }
    const onUp = () => {
      resizeRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [])

  const postPanelResize = (expanded: boolean) => {
    if (!isIframe) return
    try {
      window.parent.postMessage({ type: 'mchat:resize', expanded }, '*')
    } catch {
      /* cross-origin */
    }
  }

  const setExpanded = (expanded: boolean) => {
    setIsExpanded(expanded)
    postPanelResize(expanded)
  }

  const closeEmbed = () => {
    setExpanded(false)
    try {
      window.parent.postMessage({ type: 'mchat:close' }, '*')
    } catch {
      /* cross-origin */
    }
  }

  React.useEffect(() => {
    if (!isIframe) return
    const assistantCount = chat.messages.filter((m) => m.role === 'assistant' && m.id !== 'welcome').length
    if (assistantCount <= 0) return
    try {
      window.parent.postMessage({ type: 'mchat:unread', count: assistantCount }, '*')
    } catch {
      /* cross-origin */
    }
  }, [chat.messages, isIframe])

  const handlePreChatSubmit = (values: Record<string, string>) => {
    localStorage.setItem(preChatStorageKey, '1')
    localStorage.setItem(`${preChatStorageKey}_data`, JSON.stringify(values))
    setPreChatDone(true)
  }

  if (!agentId) {
    return (
      <div
        className={cn(
          'flex items-center justify-center p-6 text-center text-sm text-gray-500',
          isPage ? 'min-h-screen bg-gray-50' : 'fixed bottom-24 right-6 max-w-xs',
        )}
      >
        {t('chat.missingAgentConfig')}
      </div>
    )
  }

  if (configError && isPage) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <div className="max-w-md rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {configError}
        </div>
      </div>
    )
  }

  const chatBody = preChatFields.length > 0 && !preChatDone ? (
    <PreChatForm
      fields={preChatFields}
      accentColor={resolved.primaryColor}
      onSubmit={handlePreChatSubmit}
    />
  ) : (
    <ChatWindow
      messages={chat.messages}
      isStreaming={chat.isStreaming}
      streamingContent={chat.streamingContent}
      onSend={(content, options) => chat.sendMessage(content, options?.file)}
      title={isPage ? resolved.botName : undefined}
      emptyMessage={
        resolved.subscriptionActive
          ? resolved.welcomeMessage
          : resolved.offlineNotice || resolved.welcomeMessage
      }
      disabled={
        chat.isLoading ||
        chat.isStreaming ||
        configLoading ||
        !resolved.subscriptionActive
      }
      loading={chat.historyLoading || configLoading}
      accentColor={resolved.primaryColor}
      headerStyle={{ backgroundColor: resolved.primaryColor }}
      embedded={!isPage}
      speechConfigUrl={`${apiUrl}/widget/${agentId}/speech/config`}
      speechTranscribeUrl={`${apiUrl}/widget/${agentId}/speech/transcribe`}
      showGithubLink={false}
    />
  )

  if (isIframe) {
    return (
      <div className="h-full w-full flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
        <div
          className="shrink-0 flex items-center justify-between px-4 py-3 text-white"
          style={{ backgroundColor: resolved.primaryColor }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <MessageCircle className="w-5 h-5 shrink-0" />
            <span className="font-medium text-sm truncate">{resolved.botName}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <GithubLink onDark />
            {!isExpanded ? (
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="p-1 rounded hover:bg-white/20"
                title={t('widgetDemo.fullscreen')}
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="p-1 rounded hover:bg-white/20"
                title={t('widgetDemo.shrink')}
              >
                <Minimize2 className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={closeEmbed}
              className="p-1 rounded hover:bg-white/20"
              title={t('chat.widgetClose')}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        {chat.error && (
          <div className="shrink-0 mx-2 mt-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-600 dark:bg-red-950/40 dark:border-red-900 dark:text-red-300">
            {chat.error}
            <button
              type="button"
              className="ml-2 underline"
              onClick={() => chat.setError(null)}
            >
              {t('common.close')}
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0">{chatBody}</div>
      </div>
    )
  }

  if (isPage) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 dark:bg-gray-900">
        {chat.error && (
          <div className="shrink-0 mx-4 mt-2 px-4 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600">
            {chat.error}
            <button
              type="button"
              className="ml-2 underline"
              onClick={() => chat.setError(null)}
            >
              {t('chat.widgetClose')}
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0">{chatBody}</div>
      </div>
    )
  }

  return (
    <>
      {isOpen && !isMinimized && (
        <div
          data-widget-panel
          className={cn(
            'fixed z-[9999] flex flex-col overflow-hidden shadow-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 widget-enter',
            isExpanded
              ? 'inset-0 rounded-none'
              : cn(
                  'bottom-24 rounded-2xl',
                  resolved.position === 'right' ? 'right-4' : 'left-4',
                ),
          )}
          style={
            !isExpanded
              ? { width: widgetWidth || 'min(calc(100vw - 2rem), 440px)', height: 'min(80vh, 720px)' }
              : undefined
          }
        >
          <div
            className="shrink-0 flex items-center justify-between px-4 py-3 text-white"
            style={{ backgroundColor: resolved.primaryColor }}
          >
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5" />
              <span className="font-medium text-sm">{resolved.botName}</span>
            </div>
            <div className="flex items-center gap-1">
              <GithubLink onDark />
              {!isExpanded ? (
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="p-1 rounded hover:bg-white/20"
                  title={t('widgetDemo.fullscreen')}
                >
                  <Maximize2 className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="p-1 rounded hover:bg-white/20"
                  title={t('widgetDemo.shrink')}
                >
                  <Minimize2 className="w-4 h-4" />
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsMinimized(true)}
                className="p-1 rounded hover:bg-white/20"
                title={t('widgetDemo.minimize')}
              >
                <Minus className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  setExpanded(false)
                }}
                className="p-1 rounded hover:bg-white/20"
                title={t('chat.widgetClose')}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-900">
            {chatBody}
          </div>
          {!isExpanded && (
            <div
              onMouseDown={(e) => handleResizeStart(e, resolved.position === 'right' ? 'left' : 'right')}
              className={cn(
                'absolute top-0 bottom-0 w-2 -mt-[1px] -mb-[1px] cursor-ew-resize flex items-center group z-10',
                resolved.position === 'right' ? '-left-[5px] rounded-l-xl' : '-right-[5px] rounded-r-xl',
              )}
              title="Drag to resize"
            >
              <div className={cn(
                'opacity-0 group-hover:opacity-100 transition-opacity absolute top-1/2 -translate-y-1/2',
                resolved.position === 'right' ? 'left-0.5' : 'right-0.5',
              )}>
                <div className="flex flex-col gap-1">
                  <span className="w-1 h-1 rounded-full bg-gray-400" />
                  <span className="w-1 h-1 rounded-full bg-gray-400" />
                  <span className="w-1 h-1 rounded-full bg-gray-400" />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {isOpen && isMinimized && (
        <div
          className={cn(
            'fixed bottom-24 z-[9999] rounded-2xl shadow-lg px-4 py-3 text-white cursor-pointer flex items-center gap-2',
            resolved.position === 'right' ? 'right-4' : 'left-4',
          )}
          style={{ backgroundColor: resolved.primaryColor }}
          onClick={() => setIsMinimized(false)}
        >
          <MessageCircle className="w-5 h-5" />
          <span className="text-sm font-medium">{resolved.botName}</span>
        </div>
      )}

      {configError && (
        <div
          className={cn(
            'fixed bottom-24 z-[9998] max-w-xs rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700',
            resolved.position === 'right' ? 'right-4' : 'left-4',
          )}
        >
          {configError}
        </div>
      )}

      {configLoading && isOpen && (
        <div
          className={cn(
            'fixed bottom-24 z-[9998] rounded-lg bg-white border px-3 py-2 text-xs text-gray-600 shadow flex items-center gap-2',
            resolved.position === 'right' ? 'right-4' : 'left-4',
          )}
        >
          <Loader2 className="w-4 h-4 animate-spin" />
          {t('chat.widgetLoadingConfig')}
        </div>
      )}

      {(!isOpen || isMinimized) && (
      <WidgetButton
        isOpen={isOpen}
        onClick={() => {
          setIsOpen(!isOpen)
          setIsMinimized(false)
          setExpanded(false)
        }}
        position={resolved.position}
        primaryColor={resolved.primaryColor}
        launcherIcon={resolved.launcherIcon}
        launcherText={resolved.launcherText}
      />
      )}
    </>
  )
}
