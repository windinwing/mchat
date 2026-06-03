import { useEffect, useCallback, useRef } from 'react'
import { useChatStore, Message } from '@/stores/chat'
import { getWsClient } from '@/lib/websocket'

export function useChat(conversationId?: string) {
  const {
    conversations,
    currentConversation,
    messages,
    isStreaming,
    streamingContent,
    isLoading,
    error,
    fetchConversations,
    fetchMessages,
    sendMessage,
    createConversation,
    appendToStream,
    finalizeStream,
    endStream,
    syncMessagesFromServer,
    clearCurrentConversation,
    setError,
  } = useChatStore()

  const subscribedRef = useRef(false)

  const handleMessage = useCallback(
    (data: any) => {
      if (data.type === 'subscribed') {
        subscribedRef.current = true
        return
      }

      if (data.type === 'chat:stream') {
        if (!data.conversation_id || data.conversation_id === conversationId) {
          appendToStream(data.content || '')
        }
        return
      }

      if (data.type === 'chat:stream:end') {
        if (!data.conversation_id || data.conversation_id === conversationId) {
          const messageId = data.id || data.message_id
          const live = useChatStore.getState().streamingContent
          const content = data.content || live
          finalizeStream({
            id: messageId,
            conversation_id: data.conversation_id || conversationId,
            content,
          })
          if (
            typeof content === 'string' &&
            (content.startsWith('Error:') ||
              content.includes('未配置') ||
              content.includes('No AI configuration') ||
              content.includes('模型工作台'))
          ) {
            setError(content)
          }
        }
        return
      }

      if (data.type === 'chat:message' || data.type === 'message') {
        const msg = data.message || data
        if (
          msg.role === 'assistant' &&
          (!msg.conversation_id || msg.conversation_id === conversationId)
        ) {
          finalizeStream({
            id: msg.id,
            conversation_id: msg.conversation_id || conversationId,
            content: msg.content,
          })
          if (
            msg.extra_data?.is_error ||
            (typeof msg.content === 'string' &&
              (msg.content.includes('未配置') ||
                msg.content.startsWith('Error:') ||
                msg.content.includes('No AI configuration')))
          ) {
            setError(msg.content || 'Error')
          }
          return
        }
        const message: Message = {
          id: msg.id || `msg-${Date.now()}`,
          conversation_id: msg.conversation_id || conversationId || '',
          role: msg.role || 'assistant',
          content: msg.content || '',
          content_type: msg.content_type || 'text',
          extra_data: msg.extra_data,
          created_at: msg.created_at || new Date().toISOString(),
        }
        useChatStore.getState().addMessage(message)
        return
      }

      if (data.type === 'chat:error') {
        setError(data.message || 'Error')
        endStream()
      }
    },
    [conversationId, appendToStream, finalizeStream, endStream, setError],
  )

  useEffect(() => {
    if (!conversationId) return

    subscribedRef.current = false
    useChatStore.setState({
      messages: [],
      isStreaming: false,
      streamingContent: '',
      currentConversation: null,
    })
    fetchMessages(conversationId)

    const ws = getWsClient()
    ws.connect()

    const doSubscribe = () => {
      ws.send({ type: 'subscribe', conversation_id: conversationId })
    }

    doSubscribe()
    const timer = setTimeout(doSubscribe, 400)

    const handleStatus = (status: string) => {
      if (status === 'connected') {
        subscribedRef.current = false
        doSubscribe()
      }
    }
    const unsubStatus = ws.on('status', handleStatus)
    const unsubscribe = ws.on('message', handleMessage)

    return () => {
      clearTimeout(timer)
      subscribedRef.current = false
      ws.send({ type: 'unsubscribe', conversation_id: conversationId })
      unsubStatus()
      unsubscribe()
    }
  }, [conversationId, fetchMessages, handleMessage])

  // Fallback when stream:end is missed — poll lightly to avoid hammering the API
  useEffect(() => {
    if (!conversationId || !isStreaming) return
    let polls = 0
    const maxPolls = 4
    const interval = window.setInterval(() => {
      polls += 1
      if (polls > maxPolls) {
        clearInterval(interval)
        return
      }
      void syncMessagesFromServer(conversationId)
    }, 8000)
    const first = window.setTimeout(() => {
      void syncMessagesFromServer(conversationId)
    }, 5000)
    return () => {
      clearInterval(interval)
      clearTimeout(first)
    }
  }, [conversationId, isStreaming, syncMessagesFromServer])

  // After stream completes, sync once from server (authoritative ids + content)
  useEffect(() => {
    if (!conversationId || isStreaming) return
    const timer = window.setTimeout(() => {
      void syncMessagesFromServer(conversationId)
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [conversationId, isStreaming, syncMessagesFromServer])

  return {
    conversations,
    currentConversation,
    messages,
    isStreaming,
    streamingContent,
    isLoading,
    error,
    sendMessage,
    createConversation,
    clearCurrentConversation,
    setError,
  }
}
