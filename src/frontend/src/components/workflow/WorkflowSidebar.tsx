import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChevronDown,
  ChevronRight,
  Search,
  Box,
  Plus,
  CirclePlay,
  Split,
  ShieldCheck,
  GitMerge,
  Repeat,
  Square,
  Wrench,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  type GraphNodeType,
  type WorkflowSkillOption,
  type WorkflowSkillCategory,
  CONTROL_NODE_TYPES,
  NODE_COLORS,
  CATEGORY_ORDER,
  groupSkillsByCategory,
  inferSkillCategory,
} from '@/lib/workflowSkillMeta'
import { getSkillDisplayName } from '@/lib/skillDisplay'

const DRAG_MIME = 'application/mchat-workflow'

export interface PresetItem {
  id: string
  title: string
  description?: string
  skillName: string
  missing?: boolean
}

interface WorkflowSidebarProps {
  skills: WorkflowSkillOption[]
  locale: string
  onAddControlNode: (nodeType: GraphNodeType) => void
  presets?: PresetItem[]
}

function NodeDragItem({
  label,
  sublabel,
  color,
  icon,
  onClick,
  onDragStart,
  warning,
}: {
  label: string
  sublabel?: string
  color: string
  icon: React.ReactNode
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  warning?: boolean
}) {
  return (
    <div
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onClick={onClick}
      className="group flex items-center gap-2 rounded-lg px-2.5 py-1.5 cursor-grab active:cursor-grabbing border-l-[3px] bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      style={{ borderColor: color }}
    >
      <span className="shrink-0" style={{ color }}>{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block truncate text-xs font-medium text-gray-700 dark:text-gray-300">{label}</span>
        {sublabel && <span className="block truncate text-[10px] text-gray-400">{sublabel}</span>}
      </span>
      {warning && <span className="text-[10px] text-amber-500">⚠</span>}
      <Plus className="w-3 h-3 text-gray-300 group-hover:text-gray-500 dark:text-gray-600 dark:group-hover:text-gray-400 shrink-0" />
    </div>
  )
}

function CategorySection({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string
  count?: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1 px-1 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <span className="flex-1 text-left">{title}</span>
        {count !== undefined && <span className="text-[10px] text-gray-400">{count}</span>}
      </button>
      {open && <div className="space-y-1 ml-1">{children}</div>}
    </div>
  )
}

export function WorkflowSidebar({ skills, locale, onAddControlNode, presets }: WorkflowSidebarProps) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')

  const filteredSkills = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return skills
    return skills.filter(
      (s) =>
        getSkillDisplayName(s, locale).toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q),
    )
  }, [skills, search, locale])

  const grouped = useMemo(() => groupSkillsByCategory(filteredSkills), [filteredSkills])

  const nodeTypeLabel = (nt: GraphNodeType): string => {
    const map: Record<GraphNodeType, string> = {
      start: t('workflows.graphNodeStart'),
      skill: t('workflows.graphNodeSkill'),
      condition: t('workflows.graphNodeCondition'),
      approval: t('workflows.graphNodeApproval'),
      merge: t('workflows.graphNodeMerge'),
      batch: t('workflows.graphNodeBatch'),
      group: t('workflows.graphNodeGroup', 'Group'),
      end: t('workflows.graphNodeEnd'),
    }
    return map[nt] || nt
  }

  const categoryLabel = (cat: WorkflowSkillCategory): string => t(`workflows.skillCategory.${cat}`)

  const NODE_ICONS: Record<GraphNodeType, React.ComponentType<{ className?: string }>> = {
    start: CirclePlay,
    skill: Wrench,
    condition: Split,
    approval: ShieldCheck,
    merge: GitMerge,
    batch: Repeat,
    end: Square,
    group: Box,
  }

  const beginControlDrag = (e: React.DragEvent, nodeType: GraphNodeType) => {
    e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'control', nodeType }))
  }
  const beginSkillDrag = (e: React.DragEvent, skill: WorkflowSkillOption) => {
    e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'skill', skillId: skill.id }))
  }
  const beginEmptySkillDrag = (e: React.DragEvent) => {
    e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'skill-empty' }))
  }
  const beginPresetDrag = (e: React.DragEvent, presetId: string) => {
    e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'patent-preset', presetId }))
  }

  return (
    <div className="flex h-full flex-col">
      {/* Search */}
      <div className="relative shrink-0 p-2 border-b border-gray-100 dark:border-gray-800">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('workflows.searchNodes', 'Search nodes...')}
          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 pl-8 pr-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-primary-400"
        />
      </div>

      {/* Scrollable node tree */}
      <div className="flex-1 overflow-y-auto p-2">
        {/* Control nodes */}
        <CategorySection title={t('workflows.controlNodes', 'Control')} count={CONTROL_NODE_TYPES.length} defaultOpen>
          {CONTROL_NODE_TYPES.map((nt) => {
            const Icon = NODE_ICONS[nt] || Box
            return (
            <NodeDragItem
              key={nt}
              label={nodeTypeLabel(nt)}
              color={NODE_COLORS[nt]}
              icon={<Icon className="w-3.5 h-3.5" />}
              onClick={() => onAddControlNode(nt)}
              onDragStart={(e) => beginControlDrag(e, nt)}
            />
            )
          })}
        </CategorySection>

        {/* Patent presets */}
        {presets && presets.length > 0 && (
          <CategorySection title={t('workflows.palettePatentPresets', 'Presets')} count={presets.length} defaultOpen={false}>
            {presets.map((preset) => (
              <NodeDragItem
                key={preset.id}
                label={preset.title}
                sublabel={preset.description}
                color={NODE_COLORS.skill}
                icon={<Box className="w-3.5 h-3.5" />}
                warning={preset.missing}
                onDragStart={(e) => beginPresetDrag(e, preset.id)}
              />
            ))}
          </CategorySection>
        )}

        {/* Empty skill */}
        <CategorySection title={t('workflows.customSkill', 'Custom')} defaultOpen={false}>
          <NodeDragItem
            label={t('workflows.emptySkillNode', 'Empty Skill')}
            color={NODE_COLORS.skill}
            icon={<Plus className="w-3.5 h-3.5" />}
            onDragStart={beginEmptySkillDrag}
          />
        </CategorySection>

        {/* Skills by category */}
        {CATEGORY_ORDER.map((cat) => {
          const list = grouped[cat]
          if (!list || list.length === 0) return null
          return (
            <CategorySection key={cat} title={categoryLabel(cat)} count={list.length} defaultOpen={search.trim() !== ''}>
              {list.map((skill) => (
                <NodeDragItem
                  key={skill.id}
                  label={getSkillDisplayName(skill, locale)}
                  sublabel={skill.name}
                  color={NODE_COLORS.skill}
                  icon={
                    inferSkillCategory(skill) === 'search' ? (
                      <Search className="w-3.5 h-3.5" />
                    ) : (
                      <Box className="w-3.5 h-3.5" />
                    )
                  }
                  onDragStart={(e) => beginSkillDrag(e, skill)}
                />
              ))}
            </CategorySection>
          )
        })}

        {filteredSkills.length === 0 && (
          <p className="py-4 text-center text-xs text-gray-400">{t('workflows.noSkillsFound', 'No skills found')}</p>
        )}
      </div>
    </div>
  )
}
