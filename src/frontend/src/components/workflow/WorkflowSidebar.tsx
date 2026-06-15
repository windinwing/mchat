import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChevronDown,
  ChevronRight,
  Search,
  Layers,
  Clock,
  FileOutput,
  Box,
  Workflow as WorkflowIcon,
  CheckCircle2,
  XCircle,
  Loader2,
  Eye,
  Plus,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
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

export interface WorkflowGraphValue {
  version: number
  nodes: Array<{
    id: string
    type: string
    name?: string
    position?: { x: number; y: number }
    config?: Record<string, unknown>
    parentId?: string
  }>
  edges: Array<{ id: string; source: string; target: string; condition?: string }>
  viewport?: Record<string, unknown>
}

type SidebarTab = 'nodes' | 'templates' | 'history' | 'results'

interface TemplateItem {
  id: string
  name: string
  description?: string | null
  category?: string | null
  builtin?: boolean
  node_count?: number
  graph_json?: WorkflowGraphValue
}

interface RunItem {
  id: string
  status: string
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
  trigger_type?: string | null
  error?: string | null
  output_payload?: Record<string, unknown> | null
}

interface WorkflowSidebarProps {
  skills: WorkflowSkillOption[]
  locale: string
  workflowId?: string
  onAddControlNode: (nodeType: GraphNodeType) => void
  onApplyTemplate: (graph: WorkflowGraphValue) => void
}

function statusIcon(status: string) {
  if (status === 'success') return <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
  if (status === 'failed') return <XCircle className="w-3.5 h-3.5 text-red-500" />
  if (status === 'running') return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />
  if (status === 'paused') return <Clock className="w-3.5 h-3.5 text-amber-500" />
  return <Clock className="w-3.5 h-3.5 text-gray-400" />
}

function NodeDragItem({
  label,
  color,
  icon,
  onClick,
  onDragStart,
}: {
  label: string
  color: string
  icon: React.ReactNode
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
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
      <span className="flex-1 min-w-0 truncate text-xs font-medium text-gray-700 dark:text-gray-300">{label}</span>
      <Plus className="w-3 h-3 text-gray-300 group-hover:text-gray-500 dark:text-gray-600 dark:group-hover:text-gray-400 shrink-0" />
    </div>
  )
}

function CategorySection({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: string
  count?: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen ?? true)
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

export function WorkflowSidebar({ skills, locale, workflowId, onAddControlNode, onApplyTemplate }: WorkflowSidebarProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<SidebarTab>('nodes')
  const [search, setSearch] = useState('')

  // Templates
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [previewTemplate, setPreviewTemplate] = useState<string | null>(null)

  // History
  const [runs, setRuns] = useState<RunItem[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [latestRun, setLatestRun] = useState<RunItem | null>(null)

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true)
    try {
      const data = await api.get<TemplateItem[]>('/workflows/templates')
      setTemplates(data || [])
    } catch {
      setTemplates([])
    } finally {
      setTemplatesLoading(false)
    }
  }, [])

  const loadRuns = useCallback(async () => {
    if (!workflowId) return
    setRunsLoading(true)
    try {
      const data = await api.get<{ items: RunItem[] }>('/workflows/runs/list', {
        limit: '20',
        workflow_id: workflowId,
      })
      const items = data.items || []
      setRuns(items)
      setLatestRun(items.find((r) => r.status === 'success') || items[0] || null)
    } catch {
      setRuns([])
    } finally {
      setRunsLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    if (tab === 'templates') void loadTemplates()
    if (tab === 'history' || tab === 'results') void loadRuns()
  }, [tab, loadTemplates, loadRuns])

  // Node filtering
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
      end: t('workflows.graphNodeEnd'),
    }
    return map[nt] || nt
  }

  const categoryLabel = (cat: WorkflowSkillCategory): string => {
    return t(`workflows.skillCategory.${cat}`)
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

  const TABS: { id: SidebarTab; icon: React.ReactNode; label: string }[] = [
    { id: 'nodes', icon: <Box className="w-4 h-4" />, label: t('workflows.sidebarNodes', 'Nodes') },
    { id: 'templates', icon: <Layers className="w-4 h-4" />, label: t('workflows.sidebarTemplates', 'Templates') },
    { id: 'history', icon: <Clock className="w-4 h-4" />, label: t('workflows.sidebarHistory', 'History') },
    { id: 'results', icon: <FileOutput className="w-4 h-4" />, label: t('workflows.sidebarResults', 'Results') },
  ]

  return (
    <div className="flex h-full w-full flex-col bg-white dark:bg-gray-900">
      {/* Tab bar */}
      <div className="flex shrink-0 border-b border-gray-200 dark:border-gray-800">
        {TABS.map((tb) => (
          <button
            key={tb.id}
            type="button"
            onClick={() => setTab(tb.id)}
            className={cn(
              'flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors',
              tab === tb.id
                ? 'text-primary-600 dark:text-primary-400 border-b-2 border-primary-500'
                : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
            )}
          >
            {tb.icon}
            <span>{tb.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-2.5">
        {tab === 'nodes' && (
          <>
            {/* Search */}
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('workflows.searchNodes', 'Search nodes...')}
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 pl-8 pr-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            </div>

            {/* Control nodes */}
            <CategorySection title={t('workflows.controlNodes', 'Control')} count={CONTROL_NODE_TYPES.length}>
              {CONTROL_NODE_TYPES.map((nt) => (
                <NodeDragItem
                  key={nt}
                  label={nodeTypeLabel(nt)}
                  color={NODE_COLORS[nt]}
                  icon={<WorkflowIcon className="w-3.5 h-3.5" />}
                  onClick={() => onAddControlNode(nt)}
                  onDragStart={(e) => beginControlDrag(e, nt)}
                />
              ))}
            </CategorySection>

            {/* Empty skill node */}
            <CategorySection title={t('workflows.customSkill', 'Custom')}>
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
                <CategorySection key={cat} title={categoryLabel(cat)} count={list.length}>
                  {list.map((skill) => (
                    <NodeDragItem
                      key={skill.id}
                      label={getSkillDisplayName(skill, locale)}
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
          </>
        )}

        {tab === 'templates' && (
          <>
            {templatesLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : templates.length === 0 ? (
              <p className="py-8 text-center text-xs text-gray-400">{t('workflows.noTemplates', 'No templates')}</p>
            ) : (
              <div className="space-y-2">
                {templates.map((tpl) => {
                  const isPreview = previewTemplate === tpl.id
                  const graph = tpl.graph_json
                  return (
                    <div
                      key={tpl.id}
                      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-hidden"
                    >
                      <div className="p-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">{tpl.name}</p>
                            {tpl.description && (
                              <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400 line-clamp-2">{tpl.description}</p>
                            )}
                            <div className="mt-1 flex items-center gap-2">
                              {tpl.node_count != null && (
                                <span className="text-[10px] text-gray-400">{tpl.node_count} nodes</span>
                              )}
                              {tpl.builtin !== false && (
                                <span className="rounded bg-blue-100 dark:bg-blue-900/40 px-1 py-0.5 text-[9px] font-medium text-blue-600 dark:text-blue-400">
                                  built-in
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="mt-2 flex items-center gap-1.5">
                          {graph && (
                            <button
                              type="button"
                              onClick={() => setPreviewTemplate(isPreview ? null : tpl.id)}
                              className="flex items-center gap-1 rounded-md border border-gray-200 dark:border-gray-600 px-2 py-1 text-[10px] text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                            >
                              <Eye className="w-3 h-3" />
                              {isPreview ? t('common.hide', 'Hide') : t('common.preview', 'Preview')}
                            </button>
                          )}
                          {graph && (
                            <button
                              type="button"
                              onClick={() => onApplyTemplate(graph)}
                              className="flex items-center gap-1 rounded-md bg-primary-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-primary-700"
                            >
                              <Plus className="w-3 h-3" />
                              {t('workflows.applyTemplate', 'Apply')}
                            </button>
                          )}
                        </div>
                      </div>
                      {/* Inline preview */}
                      {isPreview && graph && (
                        <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2">
                          <div className="space-y-0.5">
                            {(graph.nodes || []).slice(0, 12).map((n) => (
                              <div key={n.id} className="flex items-center gap-1.5 text-[10px]">
                                <span
                                  className="inline-block h-2 w-2 rounded-full shrink-0"
                                  style={{ backgroundColor: (NODE_COLORS as any)[n.type] || '#999' }}
                                />
                                <span className="truncate text-gray-600 dark:text-gray-400">
                                  {n.name || n.type}
                                </span>
                              </div>
                            ))}
                            {graph.nodes && graph.nodes.length > 12 && (
                              <p className="text-[10px] text-gray-400 pl-3.5">
                                …{graph.nodes.length - 12} more
                              </p>
                            )}
                          </div>
                          <div className="mt-1.5 flex items-center gap-3 text-[10px] text-gray-400">
                            <span>{graph.nodes?.length || 0} nodes</span>
                            <span>{graph.edges?.length || 0} edges</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {tab === 'history' && (
          <>
            {runsLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : runs.length === 0 ? (
              <p className="py-8 text-center text-xs text-gray-400">{t('workflows.noRuns', 'No runs yet')}</p>
            ) : (
              <div className="space-y-1.5">
                {runs.map((run) => (
                  <div
                    key={run.id}
                    className="flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-2"
                  >
                    {statusIcon(run.status)}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-gray-700 dark:text-gray-300">
                        {run.trigger_type || 'manual'}
                      </p>
                      <p className="text-[10px] text-gray-400">
                        {new Date(run.started_at).toLocaleString()}
                      </p>
                    </div>
                    {run.duration_ms != null && (
                      <span className="text-[10px] text-gray-400 shrink-0">
                        {(run.duration_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {tab === 'results' && (
          <>
            {!latestRun ? (
              <p className="py-8 text-center text-xs text-gray-400">{t('workflows.noResults', 'No results yet')}</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2 rounded-lg bg-green-50 dark:bg-green-900/20 p-2">
                  {statusIcon(latestRun.status)}
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                    {new Date(latestRun.started_at).toLocaleString()}
                  </span>
                </div>
                {latestRun.output_payload && (
                  <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-2.5">
                    <p className="mb-1.5 text-[10px] font-semibold uppercase text-gray-400">
                      {t('workflows.nodeOutputs', 'Node Outputs')}
                    </p>
                    {(() => {
                      const payload = latestRun.output_payload as Record<string, unknown>
                      const nodes = (payload.nodes || payload.node_runs || {}) as Record<string, unknown>
                      const entries = Object.entries(nodes)
                      return (
                        <div className="space-y-1">
                          {entries.slice(0, 10).map(([nodeId, data]) => {
                            const result = (data as any)?.result || data
                            const preview =
                              typeof result === 'string'
                                ? result.slice(0, 120)
                                : typeof result === 'object'
                                  ? JSON.stringify(result).slice(0, 120)
                                  : String(result || '').slice(0, 120)
                            return (
                              <div key={nodeId} className="rounded bg-white dark:bg-gray-900 p-1.5">
                                <p className="text-[10px] font-medium text-gray-600 dark:text-gray-400 truncate">{nodeId}</p>
                                <p className="mt-0.5 text-[10px] text-gray-400 line-clamp-2 break-all">{preview}</p>
                              </div>
                            )
                          })}
                          {entries.length > 10 && (
                            <p className="text-[10px] text-gray-400">…{entries.length - 10} more</p>
                          )}
                        </div>
                      )
                    })()}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
