import { useCallback, useEffect, useRef, useState } from 'react'
import i18n from '@/i18n'
import { normalizeMessageMedia } from '@/lib/mediaUrl'
import type { Message } from '@/stores/chat'

const VISITOR_KEY_PREFIX = 'mchat_widget_visitor_'
const CONV_KEY_PREFIX = 'mchat_widget_conv_'

function widgetScope(agentId: string, skillId?: string) {
  const sid = (skillId || '').trim()
  return sid ? `${agentId}:${sid}` : agentId
}

function visitorStorageKey(scope: string) {
  return `${VISITOR_KEY_PREFIX}${scope}`
}

function conversationStorageKey(scope: string) {
  return `${CONV_KEY_PREFIX}${scope}`
}

/** Stable per browser tab; cleared when tab closes — visitors do not share sessions. */
function getOrCreateVisitorToken(scope: string): string {
  const key = visitorStorageKey(scope)
  let token = localStorage.getItem(key)
  if (!token) {
    token =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `v_${Date.now()}_${Math.random().toString(36).slice(2)}`
    localStorage.setItem(key, token)
  }
  return token
}

/** Remove duplicate assistant replies (e.g. legacy double-save in DB). */
function dedupeMessages(messages: Message[]): Message[] {
  const seen = new Set<string>()
  const out: Message[] = []
  for (const m of messages) {
    const key =
      m.role === 'assistant' ? `a:${m.content}` : `u:${m.id}:${m.content}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(m)
  }
  return out
}

async function consumeWidgetStream(
  response: Response,
  onToken: (chunk: string, full: string) => void,
): Promise<{
  conversationId: string
  messageId: string
  response: string
  extraData?: Record<string, unknown>
}> {
  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  let conversationId = ''
  let messageId = ''
  let extraData: Record<string, unknown> | undefined

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (!raw) continue
      const data = JSON.parse(raw) as {
        type: string
        content?: string
        conversationId?: string
        messageId?: string
        message?: string
        extraData?: Record<string, unknown>
      }

      if (data.type === 'token' && data.content) {
        full += data.content
        onToken(data.content, full)
      } else if (data.type === 'done') {
        conversationId = data.conversationId || conversationId
        messageId = data.messageId || messageId
        if (data.content) full = data.content
        if (data.extraData) extraData = data.extraData
      } else if (data.type === 'error') {
        throw new Error(data.message || '流式请求失败')
      }
    }
  }

  return { conversationId, messageId, response: full, extraData }
}

function welcomeOnlyMessage(welcomeMessage: string): Message {
  return {
    id: 'welcome',
    conversation_id: '',
    role: 'assistant',
    content: welcomeMessage,
    content_type: 'text',
    created_at: new Date().toISOString(),
  }
}

export function useWidgetChat(
  agentId: string,
  apiUrl: string,
  welcomeMessage: string,
  skillId?: string,
) {
  const [messages, setMessages] = useState<Message[]>(() =>
    welcomeMessage ? [welcomeOnlyMessage(welcomeMessage)] : [],
  )
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const base = apiUrl.replace(/\/$/, '')
  const scope = widgetScope(agentId, skillId)

  const loadHistory = useCallback(async () => {
    if (!agentId) return

    const visitorToken = getOrCreateVisitorToken(scope)
    const convId = localStorage.getItem(conversationStorageKey(scope))

    if (!convId) {
      setMessages([welcomeOnlyMessage(welcomeMessage)])
      return
    }

    setHistoryLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ visitor_token: visitorToken })
      const res = await fetch(
        `${base}/widget/${agentId}/conversation/${convId}?${params}`,
      )
      if (!res.ok) {
        if (res.status === 404 || res.status === 403) {
          localStorage.removeItem(conversationStorageKey(scope))
          setMessages([welcomeOnlyMessage(welcomeMessage)])
          return
        }
        const body = await res.json().catch(() => ({}))
        throw new Error(
          typeof body.detail === 'string' ? body.detail : `加载历史失败 (${res.status})`,
        )
      }

      const data = await res.json()
      const list: Message[] = (data.messages || []).map((m: Message) =>
        normalizeMessageMedia({
          id: m.id,
          conversation_id: m.conversation_id,
          role: m.role as Message['role'],
          content: m.content,
          content_type: m.content_type || 'text',
          extra_data: m.extra_data,
          created_at: m.created_at,
        }),
      )

      if (list.length === 0) {
        setMessages([
          {
            id: 'welcome',
            conversation_id: convId,
            role: 'assistant',
            content: welcomeMessage,
            content_type: 'text',
            created_at: new Date().toISOString(),
          },
        ])
      } else {
        const filtered = list.filter(
          (m) => m.role === 'user' || m.role === 'assistant',
        )
        setMessages(dedupeMessages(filtered))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载历史失败')
      setMessages([
        {
          id: 'welcome',
          conversation_id: '',
          role: 'assistant',
          content: welcomeMessage,
          content_type: 'text',
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      setHistoryLoading(false)
    }
  }, [agentId, base, welcomeMessage, scope])

  useEffect(() => {
    if (!agentId) return
    loadHistory()
  }, [agentId, loadHistory])

  const sendMessage = useCallback(
    async (content: string, file?: File) => {
      if (!agentId || isLoading || isStreaming) return
      if (!file && !content.trim()) return

      const visitorToken = getOrCreateVisitorToken(scope)
      const text = content.trim() || file?.name || ''
      const previewUrl =
        file && file.type.startsWith('image/')
          ? URL.createObjectURL(file)
          : undefined
      const tempId = `user-${Date.now()}`
      const userMessage: Message = {
        id: tempId,
        conversation_id: localStorage.getItem(conversationStorageKey(scope)) || '',
        role: 'user',
        content: text,
        content_type: file?.type.startsWith('image/') ? 'image' : file ? 'file' : 'text',
        extra_data: file
          ? {
              attachments: [
                {
                  name: file.name,
                  mime: file.type,
                  url: previewUrl,
                },
              ],
            }
          : undefined,
        created_at: new Date().toISOString(),
      }

      setMessages((prev) => {
        const withoutWelcome = prev.filter((m) => m.id !== 'welcome')
        return [...withoutWelcome, userMessage]
      })
      setIsLoading(true)
      setIsStreaming(true)
      setStreamingContent('')
      setError(null)
      const controller = new AbortController()
      abortRef.current = controller

      const convId = localStorage.getItem(conversationStorageKey(scope))

      try {
        let result: {
          conversationId: string
          messageId: string
          response: string
          extraData?: Record<string, unknown>
          userAttachments?: Array<{ url?: string; name?: string; mime?: string }>
        }

        if (file) {
          const form = new FormData()
          form.append('file', file)
          if (convId) form.append('conversationId', convId)
          form.append('visitorToken', visitorToken)
          if (skillId?.trim()) form.append('skillId', skillId.trim())
          if (content.trim()) form.append('content', content.trim())

          const uploadRes = await fetch(`${base}/widget/${agentId}/upload`, {
            method: 'POST',
            body: form,
            signal: controller.signal,
          })
          if (!uploadRes.ok) {
            const errBody = await uploadRes.json().catch(() => ({}))
            throw new Error(
              typeof errBody.detail === 'string'
                ? errBody.detail
                : `请求失败 (${uploadRes.status})`,
            )
          }
          const data = await uploadRes.json()
          result = {
            conversationId: data.conversationId,
            messageId: data.messageId,
            response: data.response || '',
            userAttachments: data.userAttachments,
          }
          setStreamingContent(result.response)
        } else {
        const payload = JSON.stringify({
          message: text,
          conversationId: convId,
          visitorToken,
          skillId,
        })

        const streamRes = await fetch(`${base}/widget/${agentId}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          signal: controller.signal,
        })

        if (streamRes.ok && streamRes.headers.get('content-type')?.includes('text/event-stream')) {
          result = await consumeWidgetStream(streamRes, (_chunk, full) => {
            setStreamingContent(full)
          })
        } else {
          const syncRes = await fetch(`${base}/widget/${agentId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload,
          })
          if (!syncRes.ok) {
            const errBody = await syncRes.json().catch(() => ({}))
            throw new Error(
              typeof errBody.detail === 'string'
                ? errBody.detail
                : `请求失败 (${syncRes.status})`,
            )
          }
          const data = await syncRes.json()
          result = {
            conversationId: data.conversationId,
            messageId: data.messageId,
            response: data.response || '',
            extraData: data.extraData,
          }
          setStreamingContent(result.response)
        }
        }

        if (previewUrl) URL.revokeObjectURL(previewUrl)

        if (result.conversationId) {
          localStorage.setItem(
            conversationStorageKey(scope),
            result.conversationId,
          )
        }

        const assistantMessage: Message = normalizeMessageMedia({
          id: result.messageId || `assistant-${Date.now()}`,
          conversation_id: result.conversationId || convId || '',
          role: 'assistant',
          content: result.response || i18n.t('chat.fallbackResponse'),
          content_type: 'text',
          extra_data: result.extraData,
          created_at: new Date().toISOString(),
        })

        const finalUserMessage = normalizeMessageMedia({
          ...userMessage,
          extra_data: result.userAttachments?.length
            ? { attachments: result.userAttachments }
            : userMessage.extra_data,
        })

        setMessages((prev) =>
          dedupeMessages([
            ...prev.filter((m) => m.id !== tempId),
            finalUserMessage,
            assistantMessage,
          ]),
        )
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') {
          // user stopped — keep partial content in streamingContent, let ChatWindow show it
        } else {
          if (previewUrl) URL.revokeObjectURL(previewUrl)
          const errMsg = e instanceof Error ? e.message : i18n.t('chat.networkError')
          setError(errMsg)
          setMessages((prev) => [
            ...prev.filter((m) => m.id !== tempId),
            userMessage,
            {
              id: `error-${Date.now()}`,
              conversation_id: '',
              role: 'assistant',
              content: errMsg,
              content_type: 'text',
              created_at: new Date().toISOString(),
            },
          ])
      }} finally {
        abortRef.current = null
        setIsLoading(false)
        setIsStreaming(false)
        setStreamingContent('')
      }
    },
    [agentId, base, isLoading, isStreaming, skillId, scope],
  )

  const endStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    setIsLoading(false)
  }, [])

  return {
    messages,
    isLoading,
    isStreaming,
    streamingContent,
    historyLoading,
    error,
    sendMessage,
    endStream,
    reloadHistory: loadHistory,
    setError,
  }
}
