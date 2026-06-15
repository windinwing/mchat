import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ReactFlow, Background, Controls, type Node, type Edge } from '@xyflow/react'
import { Loader2, Eye, Plus, X, Layers, Filter } from 'lucide-react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import { NODE_COLORS, type GraphNodeType } from '@/lib/workflowSkillMeta'

interface TemplateGraph {
  version: number
  nodes: Array<{ id: string; type: string; name?: string; position?: { x: number; y: number } }>
  edges: Array<{ id: string; source: string; target: string; condition?: string }>
}

interface TemplateItem {
  id: string
  name: string
  description?: string | null
  category?: string | null
  builtin?: boolean
  node_count?: number
  locale?: string | null
  graph_json?: TemplateGraph
}

interface WorkflowTemplateGalleryProps {
  open: boolean
  onClose: () => void
  onApply: (graph: TemplateGraph) => void
}

function MiniGraphPreview({ graph }: { graph: TemplateGraph }) {
  const nodes: Node[] = useMemo(
    () =>
      (graph.nodes || []).map((n) => ({
        id: n.id,
        type: 'default',
        position: n.position || { x: 0, y: 0 },
        data: { label: n.name || n.type },
        style: {
          fontSize: 9,
          padding: '2px 6px',
          borderColor: (NODE_COLORS as Record<string, string>)[n.type] || '#999',
          borderWidth: 2,
        },
      })),
    [graph.nodes],
  )
  const edges: Edge[] = useMemo(
    () =>
      (graph.edges || []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
      })),
    [graph.edges],
  )

  if (!graph.nodes || graph.nodes.length === 0) return null

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

export function WorkflowTemplateGallery({ open, onClose, onApply }: WorkflowTemplateGalleryProps) {
  const { t } = useTranslation()
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [previewId, setPreviewId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<TemplateItem[]>('/workflows/templates')
      setTemplates(data || [])
    } catch {
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      void load()
      setPreviewId(null)
      setFilter('')
    }
  }, [open, load])

  const categories = useMemo(() => {
    const set = new Set(templates.map((t) => t.category).filter(Boolean) as string[])
    return ['all', ...Array.from(set)]
  }, [templates])

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return templates.filter((tpl) => {
      if (categoryFilter !== 'all' && tpl.category !== categoryFilter) return false
      if (!q) return true
      return (
        tpl.name.toLowerCase().includes(q) ||
        (tpl.description || '').toLowerCase().includes(q)
      )
    })
  }, [templates, filter, categoryFilter])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50" onMouseDown={onClose}>
      <div
        className="flex h-[85vh] w-[90vw] max-w-5xl flex-col rounded-2xl bg-white dark:bg-gray-900 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 dark:border-gray-800 px-5 py-3">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-primary-500" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              {t('workflows.sidebarTemplates', 'Templates')}
            </h2>
            <span className="text-xs text-gray-400">({filtered.length})</span>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex shrink-0 items-center gap-3 border-b border-gray-100 dark:border-gray-800 px-5 py-2.5">
          <div className="relative flex-1 max-w-xs">
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t('common.search', 'Search...')}
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
                {cat === 'all' ? t('common.all', 'All') : cat}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-16 text-center text-sm text-gray-400">{t('workflows.noTemplates', 'No templates')}</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((tpl) => {
                const isPreview = previewId === tpl.id
                return (
                  <div
                    key={tpl.id}
                    className={cn(
                      'flex flex-col rounded-xl border bg-white dark:bg-gray-800 overflow-hidden transition-shadow',
                      isPreview
                        ? 'border-primary-300 dark:border-primary-700 shadow-md col-span-1 sm:col-span-2 lg:col-span-3'
                        : 'border-gray-200 dark:border-gray-700 hover:shadow-md',
                    )}
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{tpl.name}</h3>
                        {tpl.builtin !== false && (
                          <span className="shrink-0 rounded bg-blue-100 dark:bg-blue-900/40 px-1.5 py-0.5 text-[9px] font-medium text-blue-600 dark:text-blue-400">
                            built-in
                          </span>
                        )}
                      </div>
                      {tpl.description && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mb-2">{tpl.description}</p>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-gray-400">
                        <span>{tpl.node_count || tpl.graph_json?.nodes?.length || 0} nodes</span>
                        <span>{tpl.graph_json?.edges?.length || 0} edges</span>
                        {tpl.category && <span className="rounded bg-gray-100 dark:bg-gray-700 px-1 py-0.5">{tpl.category}</span>}
                      </div>
                    </div>

                    {/* Preview / Apply */}
                    {isPreview && tpl.graph_json ? (
                      <div className="border-t border-gray-100 dark:border-gray-700 p-3 space-y-3">
                        <MiniGraphPreview graph={tpl.graph_json} />
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              onApply(tpl.graph_json!)
                              onClose()
                            }}
                            className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700"
                          >
                            <Plus className="w-3.5 h-3.5" />
                            {t('workflows.applyTemplate', 'Apply Template')}
                          </button>
                          <button
                            type="button"
                            onClick={() => setPreviewId(null)}
                            className="rounded-lg border border-gray-200 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            {t('common.cancel', 'Cancel')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="border-t border-gray-100 dark:border-gray-700 px-3 py-2 flex items-center gap-2">
                        {tpl.graph_json && (
                          <button
                            type="button"
                            onClick={() => setPreviewId(tpl.id)}
                            className="flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600 dark:hover:text-primary-400"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            {t('common.preview', 'Preview')}
                          </button>
                        )}
                        {tpl.graph_json && (
                          <button
                            type="button"
                            onClick={() => {
                              onApply(tpl.graph_json!)
                              onClose()
                            }}
                            className="ml-auto flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
                          >
                            <Plus className="w-3.5 h-3.5" />
                            {t('workflows.applyTemplate', 'Apply')}
                          </button>
                        )}
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
