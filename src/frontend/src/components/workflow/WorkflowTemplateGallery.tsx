import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ReactFlow, Background, type Node, type Edge } from '@xyflow/react'
import { Loader2, Eye, Plus, X, Layers, Search, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import { toast } from '@/components/ui/Toast'
import { NODE_COLORS } from '@/lib/workflowSkillMeta'

interface TemplateItem {
  id: string
  name: string
  description?: string | null
  category?: string | null
  builtin?: boolean
  node_count?: number
  locale?: string | null
  graph_json?: Record<string, unknown> | null
}

interface WorkflowTemplateGalleryProps {
  open: boolean
  onClose: () => void
  /** Base path for navigation after apply (/admin or /portal) */
  basePath?: string
  /** If provided, "use template" calls this instead of creating a new workflow.
   *  Used by the graph editor to replace the current workflow's graph. */
  onSelectTemplate?: (tpl: TemplateItem) => void
  /** Called after a workflow is successfully created from a template.
   *  If not provided, navigates to the new workflow's graph editor by default. */
  onApplied?: (workflowId: string) => void
}

function MiniGraphPreview({ graph }: { graph: TemplateItem['graph_json'] }) {
  const nodes: Node[] = useMemo(() => {
    const n = (graph?.nodes as Array<{ id: string; type: string; name?: string; position?: { x: number; y: number } }>) || []
    return n.map((node) => ({
      id: node.id,
      type: 'default',
      position: node.position || { x: 0, y: 0 },
      data: { label: node.name || node.type },
      style: {
        fontSize: 9,
        padding: '2px 6px',
        borderColor: (NODE_COLORS as Record<string, string>)[node.type] || '#999',
        borderWidth: 2,
      },
    }))
  }, [graph])

  const edges: Edge[] = useMemo(() => {
    const e = (graph?.edges as Array<{ id: string; source: string; target: string }>) || []
    return e.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, type: 'smoothstep' }))
  }, [graph])

  if (!nodes.length) return null

  return (
    <div className="h-44 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-50 dark:bg-gray-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        panOnScroll={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ccc" gap={16} size={1} />
      </ReactFlow>
    </div>
  )
}

export function WorkflowTemplateGallery({ open, onClose, onSelectTemplate, onApplied }: WorkflowTemplateGalleryProps) {
  const { t, i18n } = useTranslation()
  const locale = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [applyingId, setApplyingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<TemplateItem[]>('/workflows/templates', { locale })
      setTemplates(data || [])
    } catch {
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }, [locale])

  useEffect(() => {
    if (open) {
      void load()
      setPreviewId(null)
      setSearch('')
      setCategoryFilter('all')
    }
  }, [open, load])

  const categories = useMemo(() => {
    const set = new Set(templates.map((t) => t.category).filter(Boolean) as string[])
    return ['all', ...Array.from(set)]
  }, [templates])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return templates.filter((tpl) => {
      if (categoryFilter !== 'all' && tpl.category !== categoryFilter) return false
      if (!q) return true
      return tpl.name.toLowerCase().includes(q) || (tpl.description || '').toLowerCase().includes(q)
    })
  }, [templates, search, categoryFilter])

  const handleUseTemplate = async (tpl: TemplateItem) => {
    // If a custom handler is provided (graph editor mode), use it
    if (onSelectTemplate) {
      onSelectTemplate(tpl)
      onClose()
      return
    }
    // Default: create a new workflow from template
    setApplyingId(tpl.id)
    try {
      const wf = await api.post<{ id: string }>(`/workflows/from-template/${tpl.id}`, {
        name: tpl.name,
      })
      toast(t('workflows.toastTemplateCreated', '模板已应用'), { type: 'success' })
      onClose()
      if (onApplied) {
        onApplied(wf.id)
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : t('workflows.toastTemplateCreateFailed', '应用失败'), { type: 'error' })
    } finally {
      setApplyingId(null)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50" onMouseDown={onClose}>
      <div
        className="flex h-[85vh] w-[90vw] max-w-5xl flex-col rounded-2xl bg-white dark:bg-gray-900 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 dark:border-gray-800 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary-500" />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('workflows.templatesTitle', '模板')}
            </h2>
            <span className="text-xs text-gray-400">({filtered.length})</span>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex shrink-0 items-center gap-2 border-b border-gray-100 dark:border-gray-800 px-4 py-2">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('common.search', '搜索...')}
              className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400"
            />
          </div>
          <div className="flex items-center gap-1">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategoryFilter(cat)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  categoryFilter === cat
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300'
                    : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800',
                )}
              >
                {cat === 'all' ? t('common.all', '全部') : cat}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-16 text-center text-sm text-gray-400">{t('workflows.noTemplates', '暂无模板')}</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {filtered.map((tpl) => {
                const isPreview = previewId === tpl.id
                const nodeCount = tpl.node_count || (tpl.graph_json?.nodes as unknown[])?.length || 0
                const edgeCount = (tpl.graph_json?.edges as unknown[])?.length || 0
                return (
                  <div
                    key={tpl.id}
                    className={cn(
                      'flex flex-col rounded-xl border bg-white dark:bg-gray-800 overflow-hidden transition-shadow',
                      isPreview
                        ? 'border-primary-300 dark:border-primary-700 shadow-md sm:col-span-2 lg:col-span-3'
                        : 'border-gray-200 dark:border-gray-700 hover:shadow-md',
                    )}
                  >
                    <div className="p-3 flex-1">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate flex-1">
                          {tpl.name}
                        </h3>
                        {tpl.builtin !== false && (
                          <span className="shrink-0 rounded bg-blue-100 dark:bg-blue-900/40 px-1.5 py-0.5 text-[9px] font-medium text-blue-600 dark:text-blue-400">
                            {t('workflows.builtin', '内置')}
                          </span>
                        )}
                      </div>
                      {tpl.description && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{tpl.description}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-400">
                        <span>{nodeCount} {t('workflows.nodes', '节点')}</span>
                        <span>{edgeCount} {t('workflows.edges', '连线')}</span>
                        {tpl.category && (
                          <span className="rounded bg-gray-100 dark:bg-gray-700 px-1 py-0.5">{tpl.category}</span>
                        )}
                      </div>
                    </div>

                    {/* Preview expanded */}
                    {isPreview && tpl.graph_json ? (
                      <div className="border-t border-gray-100 dark:border-gray-700 p-3 space-y-3">
                        <MiniGraphPreview graph={tpl.graph_json} />
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void handleUseTemplate(tpl)}
                            disabled={applyingId === tpl.id}
                            className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                          >
                            {applyingId === tpl.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Check className="w-3.5 h-3.5" />
                            )}
                            {t('workflows.useTemplate', '使用模板')}
                          </button>
                          <button
                            type="button"
                            onClick={() => setPreviewId(null)}
                            className="rounded-lg border border-gray-200 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            {t('common.cancel', '取消')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* Compact footer */
                      <div className="border-t border-gray-100 dark:border-gray-700 px-3 py-2 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setPreviewId(isPreview ? null : tpl.id)}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600 dark:hover:text-primary-400"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          {t('common.preview', '预览')}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleUseTemplate(tpl)}
                          disabled={applyingId === tpl.id}
                          className="ml-auto flex items-center gap-1 rounded-md bg-primary-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                        >
                          {applyingId === tpl.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Plus className="w-3.5 h-3.5" />
                          )}
                          {t('workflows.useTemplate', '使用')}
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
