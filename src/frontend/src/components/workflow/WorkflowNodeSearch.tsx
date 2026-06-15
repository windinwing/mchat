import { useState, useRef, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Box, Workflow as WorkflowIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  type GraphNodeType,
  type WorkflowSkillOption,
  CONTROL_NODE_TYPES,
  NODE_COLORS,
} from '@/lib/workflowSkillMeta'
import { getSkillDisplayName } from '@/lib/skillDisplay'

const DRAG_MIME = 'application/mchat-workflow'

interface SearchItem {
  kind: 'control' | 'skill' | 'skill-empty'
  label: string
  sublabel?: string
  color: string
  icon: React.ReactNode
  payload: string
}

interface WorkflowNodeSearchProps {
  open: boolean
  position: { x: number; y: number } | null
  skills: WorkflowSkillOption[]
  locale: string
  onSelect: (payload: string) => void
  onClose: () => void
}

export function WorkflowNodeSearch({ open, position, skills, locale, onSelect, onClose }: WorkflowNodeSearchProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [highlighted, setHighlighted] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setHighlighted(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const items = useMemo<SearchItem[]>(() => {
    const controlItems: SearchItem[] = CONTROL_NODE_TYPES.map((nt) => {
      const labels: Record<GraphNodeType, string> = {
        start: t('workflows.graphNodeStart'),
        skill: t('workflows.graphNodeSkill'),
        condition: t('workflows.graphNodeCondition'),
        approval: t('workflows.graphNodeApproval'),
        merge: t('workflows.graphNodeMerge'),
        batch: t('workflows.graphNodeBatch'),
        group: t('workflows.graphNodeGroup', 'Group'),
        end: t('workflows.graphNodeEnd'),
      }
      return {
        kind: 'control',
        label: labels[nt],
        color: NODE_COLORS[nt],
        icon: <WorkflowIcon className="w-4 h-4" />,
        payload: JSON.stringify({ kind: 'control', nodeType: nt }),
      }
    })

    const skillItems: SearchItem[] = skills.map((s) => ({
      kind: 'skill',
      label: getSkillDisplayName(s, locale),
      sublabel: s.name,
      color: NODE_COLORS.skill,
      icon: <Box className="w-4 h-4" />,
      payload: JSON.stringify({ kind: 'skill', skillId: s.id }),
    }))

    skillItems.push({
      kind: 'skill-empty',
      label: t('workflows.emptySkillNode', 'Empty Skill'),
      color: NODE_COLORS.skill,
      icon: <Box className="w-4 h-4" />,
      payload: JSON.stringify({ kind: 'skill-empty' }),
    })

    return [...controlItems, ...skillItems]
  }, [skills, locale, t])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(
      (it) => it.label.toLowerCase().includes(q) || (it.sublabel || '').toLowerCase().includes(q),
    )
  }, [items, query])

  useEffect(() => {
    setHighlighted(0)
  }, [query])

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlighted((h) => Math.min(h + 1, filtered.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlighted((h) => Math.max(h - 1, 0))
      } else if (e.key === 'Enter' && filtered[highlighted]) {
        e.preventDefault()
        onSelect(filtered[highlighted].payload)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, filtered, highlighted, onSelect, onClose])

  // Scroll highlighted item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${highlighted}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [highlighted])

  if (!open || !position) return null

  // Clamp position to viewport
  const left = Math.min(position.x, window.innerWidth - 320)
  const top = Math.min(position.y, window.innerHeight - 400)

  return (
    <div className="fixed inset-0 z-[100]" onMouseDown={onClose}>
      <div
        className="absolute w-80 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl overflow-hidden"
        style={{ left, top }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="relative border-b border-gray-100 dark:border-gray-800">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('workflows.searchNodes', 'Search nodes...')}
            className="w-full border-0 bg-transparent pl-10 pr-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 placeholder:text-gray-400 focus:outline-none focus:ring-0"
          />
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-72 overflow-y-auto p-1">
          {filtered.length === 0 ? (
            <p className="py-6 text-center text-xs text-gray-400">{t('workflows.noSkillsFound', 'No results')}</p>
          ) : (
            filtered.map((item, idx) => (
              <button
                key={idx}
                data-idx={idx}
                type="button"
                onMouseEnter={() => setHighlighted(idx)}
                onClick={() => onSelect(item.payload)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors',
                  idx === highlighted
                    ? 'bg-primary-50 dark:bg-primary-900/30'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800',
                )}
              >
                <span
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md"
                  style={{ backgroundColor: `${item.color}22`, color: item.color }}
                >
                  {item.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-gray-700 dark:text-gray-300">{item.label}</span>
                  {item.sublabel && <span className="block truncate text-[10px] text-gray-400">{item.sublabel}</span>}
                </span>
              </button>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="shrink-0 border-t border-gray-100 dark:border-gray-800 px-3 py-1.5 text-[10px] text-gray-400">
          ↑↓ navigate · Enter select · Esc close
        </div>
      </div>
    </div>
  )
}
