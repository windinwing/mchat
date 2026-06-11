import React, { useCallback } from 'react'
import {
  Bold,
  Italic,
  Heading1,
  Heading2,
  Heading3,
  Link,
  Image,
  Quote,
  Code,
  List,
  ListOrdered,
  Minus,
  Paperclip,
} from 'lucide-react'

interface ToolbarAction {
  icon: React.ReactNode
  label: string
  prefix: string
  suffix: string
  defaultText?: string
  multiline?: boolean
}

const ACTIONS: ToolbarAction[] = [
  { icon: <Bold className="w-4 h-4" />, label: 'Bold', prefix: '**', suffix: '**', defaultText: 'bold text' },
  { icon: <Italic className="w-4 h-4" />, label: 'Italic', prefix: '*', suffix: '*', defaultText: 'italic text' },
  { icon: <Heading1 className="w-4 h-4" />, label: 'H1', prefix: '# ', suffix: '', defaultText: 'Heading' },
  { icon: <Heading2 className="w-4 h-4" />, label: 'H2', prefix: '## ', suffix: '', defaultText: 'Heading' },
  { icon: <Heading3 className="w-4 h-4" />, label: 'H3', prefix: '### ', suffix: '', defaultText: 'Heading' },
  { icon: <Link className="w-4 h-4" />, label: 'Link', prefix: '[', suffix: '](url)', defaultText: 'link text' },
  { icon: <Image className="w-4 h-4" />, label: 'Image', prefix: '![', suffix: '](image-url)', defaultText: 'alt text' },
  { icon: <Quote className="w-4 h-4" />, label: 'Quote', prefix: '> ', suffix: '', defaultText: 'quote', multiline: true },
  { icon: <Code className="w-4 h-4" />, label: 'Code block', prefix: '```\n', suffix: '\n```', defaultText: 'code', multiline: true },
  { icon: <List className="w-4 h-4" />, label: 'Bullet list', prefix: '- ', suffix: '', defaultText: 'item', multiline: true },
  { icon: <ListOrdered className="w-4 h-4" />, label: 'Numbered list', prefix: '1. ', suffix: '', defaultText: 'item', multiline: true },
  { icon: <Minus className="w-4 h-4" />, label: 'Divider', prefix: '\n---\n', suffix: '', defaultText: '' },
]

interface MarkdownToolbarProps {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  value: string
  onChange: (value: string) => void
  onOpenResourcePicker?: () => void
  hasResources?: boolean
}

export function MarkdownToolbar({ textareaRef, value, onChange, onOpenResourcePicker, hasResources }: MarkdownToolbarProps) {
  const applyAction = useCallback(
    (action: ToolbarAction) => {
      const textarea = textareaRef.current
      if (!textarea) return

      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const before = value.slice(0, start)
      const selected = value.slice(start, end)
      const after = value.slice(end)

      let insertText: string
      let newCursorStart: number
      let newCursorEnd: number

      if (selected.length > 0) {
        if (action.multiline) {
          const lines = selected.split('\n')
          const wrapped = lines.map((line) => action.prefix + line).join('\n')
          insertText = wrapped + action.suffix
          newCursorStart = start
          newCursorEnd = start + insertText.length
        } else {
          insertText = action.prefix + selected + action.suffix
          newCursorStart = start + action.prefix.length
          newCursorEnd = start + action.prefix.length + selected.length
        }
      } else {
        insertText = action.prefix + (action.defaultText || '') + action.suffix
        newCursorStart = start + action.prefix.length
        newCursorEnd = start + action.prefix.length + (action.defaultText || '').length
      }

      const newValue = before + insertText + after
      onChange(newValue)

      setTimeout(() => {
        textarea.focus()
        textarea.setSelectionRange(newCursorStart, newCursorEnd)
      }, 0)
    },
    [textareaRef, value, onChange]
  )

  return (
    <div className="flex items-center gap-0.5 flex-wrap bg-gray-50 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded-lg px-1.5 py-1">
      {ACTIONS.map((action) => (
        <button
          key={action.label}
          type="button"
          onClick={() => applyAction(action)}
          className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          title={action.label}
        >
          {action.icon}
        </button>
      ))}

      {hasResources && (
        <button
          type="button"
          onClick={onOpenResourcePicker}
          className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          title="Insert resource"
        >
          <Paperclip className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
