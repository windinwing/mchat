import { useCallback, useRef } from 'react'

const MAX_INPUT_HISTORY = 100

/** Shell-style ↑/↓ recall for sent messages in chat input. */
export function useInputHistory() {
  const entriesRef = useRef<string[]>([])
  const cursorRef = useRef(-1)
  const draftRef = useRef('')

  const pushSent = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const list = entriesRef.current
    if (list[list.length - 1] !== trimmed) {
      list.push(trimmed)
      if (list.length > MAX_INPUT_HISTORY) list.shift()
    }
    cursorRef.current = -1
    draftRef.current = ''
  }, [])

  const resetBrowse = useCallback(() => {
    cursorRef.current = -1
    draftRef.current = ''
  }, [])

  const navigate = useCallback((direction: -1 | 1, currentValue: string): string | null => {
    const list = entriesRef.current
    if (list.length === 0) return null

    if (direction === -1) {
      if (cursorRef.current === -1) {
        draftRef.current = currentValue
        cursorRef.current = list.length - 1
      } else if (cursorRef.current > 0) {
        cursorRef.current -= 1
      } else {
        return list[0]
      }
      return list[cursorRef.current]
    }

    if (cursorRef.current === -1) return null
    if (cursorRef.current < list.length - 1) {
      cursorRef.current += 1
      return list[cursorRef.current]
    }
    cursorRef.current = -1
    return draftRef.current
  }, [])

  const isBrowsing = useCallback(() => cursorRef.current >= 0, [])

  return { pushSent, navigate, resetBrowse, isBrowsing }
}
