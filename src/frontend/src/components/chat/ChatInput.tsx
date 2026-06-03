import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Paperclip, X, Mic, Square, Link2, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useSpeechInput } from '@/hooks/useSpeechInput'
import { useInputHistory } from '@/hooks/useInputHistory'
import { ChatSendOptions, OutboundAsset } from '@/stores/chat'

interface ChatInputProps {
  onSend: (content: string, options?: ChatSendOptions) => void
  disabled?: boolean
  placeholder?: string
  compact?: boolean
  /** Widget embed: single-line input, no auto-grow */
  singleLine?: boolean
  speechTranscribeUrl?: string
  speechConfigUrl?: string
  allowAssistantMode?: boolean
  allowOutboundLinks?: boolean
  defaultSendRole?: 'user' | 'assistant'
  allowAttachments?: boolean
  attachmentAccept?: string
  /** studio = portal; embedded = floating widget */
  variant?: 'default' | 'studio' | 'embedded'
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder,
  compact = false,
  singleLine = false,
  speechTranscribeUrl,
  speechConfigUrl,
  allowAssistantMode = false,
  allowOutboundLinks = false,
  defaultSendRole = 'user',
  allowAttachments = true,
  attachmentAccept,
  variant = 'default',
}: ChatInputProps) {
  const studio = variant === 'studio'
  const embeddedShell = variant === 'embedded'
  const { t, i18n } = useTranslation()
  const [content, setContent] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [sendRole, setSendRole] = useState<'user' | 'assistant'>(defaultSendRole)
    useEffect(() => {
      setSendRole(defaultSendRole)
    }, [defaultSendRole])

  const [linkEditorOpen, setLinkEditorOpen] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [linkName, setLinkName] = useState('')
  const [outboundLinks, setOutboundLinks] = useState<OutboundAsset[]>([])
  const [speechError, setSpeechError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  /** 开始录音前的输入框内容，避免预览与最终写入叠加重复 */
  const speechBaseRef = useRef('')
  const wasListeningRef = useRef(false)
  const inputHistory = useInputHistory()

  const speechMessages = useMemo(
    () => ({
      browserUnsupported: t('speech.browserUnsupported'),
      recognitionFailed: t('speech.recognitionFailed'),
      recordingTooShort: t('speech.recordingTooShort'),
      transcribeFailed: t('speech.transcribeFailed'),
      noSpeechDetected: t('speech.noSpeechDetected'),
      speechFailed: t('speech.speechFailed'),
      micDenied: t('speech.micDenied'),
      unavailable: t('speech.unavailable'),
    }),
    [t, i18n.language],
  )

  const appendTranscript = useCallback((text: string, interim?: boolean) => {
    if (!text || interim) return
    const t = text.trim()
    if (!t) return
    const base = speechBaseRef.current.trim()
    setContent(() => {
      if (!base) return t
      if (base === t || base.endsWith(t)) return base
      return `${base} ${t}`
    })
    setSpeechError(null)
  }, [])

  const speech = useSpeechInput({
    transcribeUrl: speechTranscribeUrl,
    configUrl: speechConfigUrl,
    disabled,
    language: i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US',
    messages: speechMessages,
    onTranscript: appendTranscript,
    onError: (msg) => setSpeechError(msg),
  })

  const speechEnabled =
    !!speechTranscribeUrl || !!speechConfigUrl || speech.supported

  useEffect(() => {
    if (speech.isListening && !wasListeningRef.current) {
      speechBaseRef.current = content.trimEnd()
    }
    wasListeningRef.current = speech.isListening
  }, [speech.isListening, content])

  useEffect(() => {
    if (singleLine || !textareaRef.current) return
    textareaRef.current.style.height = 'auto'
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
  }, [content, speech.interimText, singleLine])

  const handleSubmit = () => {
    const trimmed = content.trim()
    if (!trimmed && !selectedFile && outboundLinks.length === 0) return
    if (speech.isListening) speech.stopListening()
    onSend(trimmed, {
      file: selectedFile ?? undefined,
      role: sendRole,
      outboundAssets: outboundLinks.length > 0 ? outboundLinks : undefined,
    })
    if (trimmed) inputHistory.pushSent(trimmed)
    setContent('')
    setSelectedFile(null)
    setOutboundLinks([])
    setLinkEditorOpen(false)
    setLinkUrl('')
    setLinkName('')
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (!singleLine && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const getTextInputEl = () =>
    singleLine ? inputRef.current : textareaRef.current

  const atInputStart = () => {
    const el = getTextInputEl()
    if (!el) return true
    return el.selectionStart === 0 && el.selectionEnd === 0
  }

  const atInputEnd = () => {
    const el = getTextInputEl()
    if (!el) return true
    return el.selectionStart === el.value.length && el.selectionEnd === el.value.length
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (!atInputStart()) return
      const recalled = inputHistory.navigate(-1, content)
      if (recalled !== null) {
        e.preventDefault()
        setContent(recalled)
        if (speech.isListening) speechBaseRef.current = recalled
      }
      return
    }
    if (e.key === 'ArrowDown' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (!inputHistory.isBrowsing()) return
      if (!atInputEnd()) return
      const recalled = inputHistory.navigate(1, content)
      if (recalled !== null) {
        e.preventDefault()
        setContent(recalled)
        if (speech.isListening) speechBaseRef.current = recalled
      }
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInputChange = (value: string) => {
    if (inputHistory.isBrowsing()) inputHistory.resetBrowse()
    if (speech.isListening) {
      speechBaseRef.current = value.replace(speech.interimText, '').trimEnd()
    } else {
      setContent(value)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!allowAttachments) return
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    if (!allowAttachments) return
    const items = e.clipboardData?.items
    if (items) {
      for (const item of Array.from(items)) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) {
            setSelectedFile(file)
          }
          break
        }
      }
    }
  }

  const inputValue =
    speech.isListening && speech.interimText
      ? [speechBaseRef.current, speech.interimText].filter(Boolean).join(' ')
      : content

  const displayPlaceholder = speech.isListening
    ? t('chat.listeningPlaceholder')
    : (placeholder ?? t('chat.inputPlaceholder'))

  const addOutboundLink = () => {
    const url = linkUrl.trim()
    if (!url) return
    try {
      const parsed = new URL(url)
      if (!['http:', 'https:'].includes(parsed.protocol)) return
      setOutboundLinks((prev) => [
        ...prev,
        {
          type: 'link',
          name: linkName.trim() || parsed.hostname || parsed.href,
          url: parsed.href,
          source: 'explicit',
        },
      ])
      setLinkUrl('')
      setLinkName('')
      setLinkEditorOpen(false)
    } catch {
      // Ignore invalid URL; backend validation will still guard request payloads.
    }
  }

  const defaultAccept =
    'image/*,video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm,.pdf,.doc,.docx,.txt'
  const fileAccept = attachmentAccept ?? defaultAccept

  return (
    <div
      className={cn(
        studio
          ? 'rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800 px-3 pt-3 pb-3'
          : embeddedShell
            ? 'bg-transparent px-0 py-0'
            : cn(
                'bg-white dark:bg-gray-800',
                compact ? 'px-3 py-2.5' : 'px-0 py-0',
              ),
      )}
    >
      {speechError && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">{speechError}</p>
      )}

      {selectedFile && (
        <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg">
          {selectedFile.type.startsWith('image/') ? (
            <img
              src={URL.createObjectURL(selectedFile)}
              alt=""
              className="w-10 h-10 rounded object-cover shrink-0"
              onLoad={(e) => URL.revokeObjectURL((e.target as HTMLImageElement).src)}
            />
          ) : (
            <Paperclip className="w-4 h-4 text-gray-400 shrink-0" />
          )}
          <span className="text-sm text-gray-600 dark:text-gray-300 truncate flex-1">
            {selectedFile.name}
          </span>
          <button
            type="button"
            onClick={() => {
              setSelectedFile(null)
              if (fileInputRef.current) fileInputRef.current.value = ''
            }}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            title={t('chat.removeAttachment')}
            aria-label={t('chat.removeAttachment')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {outboundLinks.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {outboundLinks.map((asset, index) => (
            <span
              key={`${asset.url}-${index}`}
              className="inline-flex items-center gap-1 rounded-full bg-primary-50 dark:bg-primary-900/30 px-3 py-1 text-xs text-primary-700 dark:text-primary-300"
            >
              <Link2 className="w-3.5 h-3.5" />
              <span className="max-w-[180px] truncate">{asset.name || asset.url}</span>
              <button
                type="button"
                onClick={() => setOutboundLinks((prev) => prev.filter((_, i) => i !== index))}
                className="opacity-70 hover:opacity-100"
                title={t('chat.removeLinkAsset')}
                aria-label={t('chat.removeLinkAsset')}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {allowOutboundLinks && linkEditorOpen && (
        <div className="mb-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 space-y-2">
          <div className="grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] gap-2 items-center">
            <input
              type="url"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              placeholder={t('chat.linkUrlPlaceholder')}
              className="min-w-0 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <input
              type="text"
              value={linkName}
              onChange={(e) => setLinkName(e.target.value)}
              placeholder={t('chat.linkNamePlaceholder')}
              className="min-w-0 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button
              type="button"
              onClick={addOutboundLink}
              className="inline-flex items-center gap-1 whitespace-nowrap rounded-lg bg-primary-600 px-3 py-2 text-sm text-white hover:bg-primary-700"
            >
              <Plus className="w-4 h-4" />
              {t('chat.addLink')}
            </button>
          </div>
        </div>
      )}

      {(allowAssistantMode || allowOutboundLinks) && (
        <div className="flex items-center justify-between gap-3 mb-2">
          {allowAssistantMode ? (
            <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 p-1 bg-gray-50 dark:bg-gray-900/40">
              {(['user', 'assistant'] as const).map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => setSendRole(role)}
                  className={cn(
                    'px-3 py-1.5 rounded-md text-xs transition-colors',
                    sendRole === role
                      ? 'bg-primary-600 text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
                  )}
                >
                  {role === 'user' ? t('chat.sendAsUser') : t('chat.sendAsAssistant')}
                </button>
              ))}
            </div>
          ) : <div />}
          {allowOutboundLinks && (
            <button
              type="button"
              onClick={() => setLinkEditorOpen((prev) => !prev)}
              className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600"
            >
              <Link2 className="w-4 h-4" />
              {t('chat.addLinkAsset')}
            </button>
          )}
        </div>
      )}

      <div className={cn('flex gap-2', singleLine ? 'items-center' : 'items-end')}>
        {allowAttachments && (
          <>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
              title={t('chat.uploadAttachment')}
            >
              <Paperclip className="w-5 h-5" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileSelect}
              accept={fileAccept}
              title={t('chat.uploadAttachment')}
              aria-label={t('chat.uploadAttachment')}
            />
          </>
        )}

        {speechEnabled && (
          <button
            type="button"
            onClick={speech.toggleListening}
            disabled={disabled}
            title={speech.isListening ? t('chat.stopVoice') : t('chat.voiceInput')}
            className={cn(
              'p-2 rounded-lg transition-colors disabled:opacity-50',
              speech.isListening
                ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400 animate-pulse'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700',
            )}
          >
            {speech.isListening ? (
              <Square className="w-5 h-5" />
            ) : (
              <Mic className="w-5 h-5" />
            )}
          </button>
        )}

        <div className="flex-1 min-w-0">
          {singleLine ? (
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={displayPlaceholder}
              disabled={disabled}
              title={t('chat.inputHistoryHint')}
              className={cn(
                'block w-full h-10 rounded-xl border border-gray-300 bg-gray-50 px-4 text-sm',
                'placeholder:text-gray-400',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200 dark:placeholder:text-gray-500',
                speech.isListening && 'ring-2 ring-red-300 dark:ring-red-700',
              )}
            />
          ) : (
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={displayPlaceholder}
              disabled={disabled}
              title={t('chat.inputHistoryHint')}
              rows={1}
              className={cn(
                'block w-full min-h-[42px] h-auto resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm',
                'placeholder:text-gray-400',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200 dark:placeholder:text-gray-500',
                speech.isListening && 'ring-2 ring-red-300 dark:ring-red-700',
              )}
            />
          )}
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || (!content.trim() && !selectedFile && outboundLinks.length === 0)}
          className={cn(
            'p-2.5 rounded-xl transition-colors',
            content.trim() || selectedFile || outboundLinks.length > 0
              ? 'bg-primary-600 text-white hover:bg-primary-700'
              : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500 cursor-not-allowed',
          )}
          title={t('chat.send')}
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
    </div>
  )
}
