import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  GripVertical,
  Maximize2,
  Minimize2,
  Plus,
  Save,
  Trash2,
  X,
} from 'lucide-react'
import {
  Background,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  useViewport,
  type Connection,
  type Edge,
  type Node,
  type Viewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { cn } from '@/lib/utils'
import {
  CATEGORY_ORDER,
  CONTROL_NODE_TYPES,
  NODE_COLORS,
  collectUpstreamNodeIds,
  defaultPayloadForSkill,
  extractStartInputFields,
  groupSkillsByCategory,
  inferSkillCategory,
  type GraphNodeType,
  type InputFieldDef,
  type WorkflowSkillOption,
} from '@/lib/workflowSkillMeta'
import { getSkillDisplayName } from '@/lib/skillDisplay'
import {
  buildPatentWorkflowPresets,
  getPatentPresetById,
  getPatentPresetDescription,
  getPatentPresetTitle,
  type PatentShowcaseConfig,
  type PatentWorkflowPreset,
} from '@/lib/patentWorkflowPresets'
import api from '@/lib/api'
import { PayloadMapper } from '@/components/workflow/PayloadMapper'
import { WorkflowCanvasToolbar, type CanvasTool } from '@/components/workflow/WorkflowCanvasToolbar'
import { workflowNodeTypes } from '@/components/workflow/WorkflowCanvasNode'
import { groupNodeTypes, computeGroupBounds } from '@/components/workflow/WorkflowGroupNode'
import {
  WorkflowGraphContextMenu,
  type GraphContextMenuState,
} from '@/components/workflow/WorkflowGraphContextMenu'
import { WorkflowCanvasToolHint } from '@/components/workflow/WorkflowCanvasToolHint'
import { WorkflowSidebar, type PresetItem } from '@/components/workflow/WorkflowSidebar'
import { WorkflowNodeSearch } from '@/components/workflow/WorkflowNodeSearch'
import { useWorkflowGraphHistory } from '@/hooks/useWorkflowGraphHistory'

export type { GraphNodeType }

function parseStoredViewport(raw?: Record<string, unknown>): Viewport | null {
  if (!raw || typeof raw !== 'object') return null
  const x = Number(raw.x)
  const y = Number(raw.y)
  const zoom = Number(raw.zoom)
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(zoom)) return null
  return { x, y, zoom }
}

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (el.isContentEditable) return true
  return Boolean(el.closest('[contenteditable="true"]'))
}

const DRAG_MIME = 'application/mchat-workflow'

export interface WorkflowGraphValue {
  version: number
  nodes: Array<{
    id: string
    type: GraphNodeType
    name?: string
    position?: { x: number; y: number }
    config?: Record<string, unknown>
    parentId?: string
  }>
  edges: Array<{
    id: string
    source: string
    target: string
    source_handle?: string
    target_handle?: string
    condition?: string
  }>
  viewport?: Record<string, unknown>
}

interface Props {
  value?: WorkflowGraphValue | null
  skills: WorkflowSkillOption[]
  onSave: (value: WorkflowGraphValue) => void
  workflowId?: string
  workflowName?: string
  onBack?: () => void
  headerExtra?: React.ReactNode
  presets?: PresetItem[]
}

function isDarkMode() {
  return document.documentElement.classList.contains('dark')
}

function toSafeInt(value: string, fallback: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.max(0, Math.floor(n))
}

function resolveSkillFromConfig(
  config: Record<string, unknown>,
  skills: WorkflowSkillOption[],
): WorkflowSkillOption | undefined {
  const skillId = String(config.skill_id || '')
  const skillName = String(config.skill_name || '')
  if (skillId) {
    const byId = skills.find((s) => s.id === skillId)
    if (byId) return byId
  }
  if (skillName) {
    return skills.find((s) => s.name === skillName)
  }
  return undefined
}

function enrichSkillConfig(
  config: Record<string, unknown>,
  skills: WorkflowSkillOption[],
): Record<string, unknown> {
  const resolved = resolveSkillFromConfig(config, skills)
  if (!resolved) return config
  return {
    ...config,
    skill_id: resolved.id,
    skill_name: resolved.name,
  }
}

function skillLabelForNode(
  config: Record<string, unknown>,
  skills: WorkflowSkillOption[],
  locale: string,
) {
  const skillId = String(config.skill_id || '')
  const skillName = String(config.skill_name || '')
  const byId = skills.find((s) => s.id === skillId)
  if (byId) return getSkillDisplayName(byId, locale)
  if (skillName) {
    const byName = skills.find((s) => s.name === skillName)
    if (byName) return getSkillDisplayName(byName, locale)
    return skillName
  }
  return ''
}

function isSkillMissing(config: Record<string, unknown>, skills: WorkflowSkillOption[]) {
  const skillId = String(config.skill_id || '')
  if (skillId && skills.some((s) => s.id === skillId)) return false
  const skillName = String(config.skill_name || '')
  if (skillName && skills.some((s) => s.name === skillName)) return false
  if (skillId || skillName) return true
  return false
}

function toFlowNodes(
  graphNodes: WorkflowGraphValue['nodes'],
  skills: WorkflowSkillOption[],
  locale: string,
  t: (key: string) => string,
): Node[] {
  const parentIds = new Map<string, number>()
  const parentChildNames = new Map<string, string[]>()
  for (const node of graphNodes) {
    if (node.parentId) {
      parentIds.set(node.parentId, (parentIds.get(node.parentId) || 0) + 1)
      const list = parentChildNames.get(node.parentId) || []
      const cfg = node.config || {}
      const sn = node.type === 'skill' ? (String(cfg.skill_name || '') || node.name || '') : (node.type || '')
      if (sn) list.push(sn)
      parentChildNames.set(node.parentId, list)
    }
  }
  return graphNodes.map((node) => {
    const rawConfig = node.config || {}
    const config =
      node.type === 'skill' ? enrichSkillConfig(rawConfig, skills) : rawConfig
    const skillLabel = node.type === 'skill' ? skillLabelForNode(config, skills, locale) : ''
    const category =
      node.type === 'skill'
        ? t(`workflows.skillCategory.${String(config.workflow_role || inferSkillCategory({ id: '', name: skillLabel || node.name || '', config }))}`)
        : ''
    const skillMissing = node.type === 'skill' ? isSkillMissing(config, skills) : false
    const batchListPath = node.type === 'batch' ? String(config.list_path || '') : ''
    const batchChildCount = node.type === 'batch' ? (parentIds.get(node.id) || 0) : 0
    const batchChildLabels = node.type === 'batch' ? (parentChildNames.get(node.id) || []) : []
    const isGroup = node.type === 'group'
    const groupChildCount = isGroup ? (parentIds.get(node.id) || 0) : 0
    const groupW = isGroup ? Number(config.width) || 280 : undefined
    const groupH = isGroup ? Number(config.height) || 160 : undefined
    return {
      id: node.id,
      type: isGroup ? 'workflowGroup' : 'workflowNode',
      position: node.position || { x: 100, y: 100 },
      style: node.parentId ? undefined : (node.type === 'batch' ? { width: 320, height: 240 } : isGroup ? { width: groupW, height: groupH } : undefined),
      width: (node.type === 'batch' && !node.parentId) ? 320 : isGroup ? groupW : undefined,
      height: (node.type === 'batch' && !node.parentId) ? 240 : isGroup ? groupH : undefined,
      measured: (node.type === 'batch' && !node.parentId) ? { width: 320, height: 240 } : isGroup ? { width: groupW, height: groupH } : undefined,
      parentId: node.parentId || undefined,
      extent: node.parentId ? 'parent' : undefined,
      hidden: isGroup && config.collapsed ? false : undefined,
      data: {
        label: node.name || node.id,
        nodeType: node.type,
        config,
        skillLabel: skillMissing && config.skill_name ? String(config.skill_name) : skillLabel,
        categoryLabel: category,
        skillMissing,
        batchListPath,
        batchChildCount,
        batchChildLabels,
        groupChildCount,
      },
    }
  })
}

function toFlowEdges(edges: WorkflowGraphValue['edges']): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.condition || '',
    sourceHandle: edge.source_handle,
    targetHandle: edge.target_handle,
  }))
}

function recomputeBatchChildrenMeta(nodes: Node[], batchId: string): Node[] {
  const children = nodes.filter((n) => n.parentId === batchId)
  const count = children.length
  const labels = children
    .map((n) => {
      const nd = (n.data || {}) as Record<string, unknown>
      const cfg = (nd.config || {}) as Record<string, unknown>
      const nt = String(nd.nodeType || '')
      const lbl = String(nd.label || '')
      return nt === 'skill' ? String(cfg.skill_name || '') || lbl || '' : nt || lbl || ''
    })
    .filter(Boolean)
  return nodes.map((n) => {
    const nd = n.data as Record<string, unknown> | undefined
    if (n.id === batchId && nd?.nodeType === 'batch') {
      return { ...n, data: { ...nd, batchChildCount: count, batchChildLabels: labels } }
    }
    return n
  })
}

function IconToolButton({
  title,
  onClick,
  disabled,
  active,
  children,
  className,
}: {
  title: string
  onClick: () => void
  disabled?: boolean
  active?: boolean
  children: React.ReactNode
  className?: string
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-md border transition-colors',
        active
          ? 'border-primary-400 bg-primary-50 text-primary-700 dark:border-primary-500 dark:bg-primary-950/80 dark:text-primary-300'
          : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800',
        'disabled:cursor-not-allowed disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  )
}

function PanelEdgeToggle({
  side,
  title,
  onClick,
}: {
  side: 'left' | 'right'
  title: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className={cn(
        'flex w-6 shrink-0 flex-col items-center justify-center border-gray-200 bg-white text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-800',
        'dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200',
        side === 'left' ? 'border-r' : 'border-l',
      )}
    >
      {side === 'left' ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
    </button>
  )
}

export function WorkflowGraphEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <WorkflowGraphEditorInner {...props} />
    </ReactFlowProvider>
  )
}

function WorkflowGraphEditorInner({ value, skills, onSave, workflowId, workflowName, onBack, headerExtra, presets }: Props) {
  const { t, i18n } = useTranslation()
  const uiLocale = i18n.language || 'zh'
  const { screenToFlowPosition, zoomIn, zoomOut, fitView, getViewport, setViewport } = useReactFlow()
  const { zoom } = useViewport()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const reactFlowWrapper = useRef<HTMLDivElement | null>(null)
  const viewportInitialized = useRef(false)
  const [dark, setDark] = useState(isDarkMode())
  const [paletteOpen, setPaletteOpen] = useState(true)
  const [propsOpen, setPropsOpen] = useState(false)
  const [selectedTab, setSelectedTab] = useState<'visual' | 'json'>('visual')

  const initial = useMemo<WorkflowGraphValue>(
    () => value || { version: 1, nodes: [], edges: [] },
    [value],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(toFlowNodes(initial.nodes, skills, uiLocale, t))
  const [edges, setEdges, onEdgesChange] = useEdgesState(toFlowEdges(initial.edges))
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [fullScreen, setFullScreen] = useState(false)
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [skillSearch, setSkillSearch] = useState('')
  const [contextMenu, setContextMenu] = useState<GraphContextMenuState>(null)
  const [nodeSearch, setNodeSearch] = useState<{ open: boolean; pos: { x: number; y: number } | null }>({ open: false, pos: null })
  const [canvasTool, setCanvasTool] = useState<CanvasTool>('pointer')
  const [spaceHeld, setSpaceHeld] = useState(false)
  const [showMinimap, setShowMinimap] = useState(true)
  const [toolHintLabel, setToolHintLabel] = useState<string | null>(null)
  const toolHintTimerRef = useRef<number | undefined>(undefined)
  const isPointerTool = canvasTool === 'pointer' && !spaceHeld
  const [showcaseConfig, setShowcaseConfig] = useState<PatentShowcaseConfig | null>(null)

  const {
    pushHistory,
    undo,
    redo,
    clearHistory,
    onNodeDragStart,
    onNodeDragStop,
    handleNodesChange,
    handleEdgesChange,
  } = useWorkflowGraphHistory(nodes, edges, setNodes, setEdges)

  const showToolHint = useCallback(
    (mode: 'pointer' | 'pan' | 'space') => {
      const label =
        mode === 'pointer'
          ? t('workflows.canvasHintPointer')
          : mode === 'pan'
            ? t('workflows.canvasHintPan')
            : t('workflows.canvasHintSpacePan')
      setToolHintLabel(label)
      window.clearTimeout(toolHintTimerRef.current)
      toolHintTimerRef.current = window.setTimeout(() => setToolHintLabel(null), 1600)
    },
    [t],
  )

  const selectCanvasTool = useCallback(
    (tool: CanvasTool) => {
      setCanvasTool(tool)
      showToolHint(tool === 'pointer' ? 'pointer' : 'pan')
    },
    [showToolHint],
  )

  const patentPresets = useMemo(
    () =>
      buildPatentWorkflowPresets(
        showcaseConfig?.search_skill,
        showcaseConfig?.report_skill,
      ),
    [showcaseConfig?.search_skill, showcaseConfig?.report_skill],
  )

  useEffect(() => {
    let cancelled = false
    api
      .get<PatentShowcaseConfig>('/workflows/showcase-config')
      .then((data) => {
        if (!cancelled) setShowcaseConfig(data)
      })
      .catch(() => {
        if (!cancelled) setShowcaseConfig(null)
      })
    return () => {
      cancelled = true
    }
  }, [])
  // Listen for batch node drop events
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { raw: string; batchNodeId: string }
      if (!detail?.raw || !detail?.batchNodeId) return
      e.stopPropagation()
      let payload: { kind: string; skillId?: string }
      try { payload = JSON.parse(detail.raw) } catch { return }
      if (payload.kind === 'skill' && payload.skillId) {
        const skill = skills.find((s) => s.id === payload.skillId)
        if (!skill) return
        pushHistory()
        const label = getSkillDisplayName(skill, uiLocale)
        const existing = nodes.filter((n) => n.parentId === detail.batchNodeId).length
        const relPos = { x: 20, y: 60 + existing * 50 }
        const childNode = buildSkillNode(skill, relPos, label)
        childNode.parentId = detail.batchNodeId
        childNode.extent = 'parent'
        setNodes((prev) => recomputeBatchChildrenMeta([...prev, childNode], detail.batchNodeId))
        setSelectedNodeId(childNode.id)
        setSelectedEdgeId(null)
        setPropsOpen(true)
      }
    }
    window.addEventListener('mchat-batch-drop', handler)
    return () => window.removeEventListener('mchat-batch-drop', handler)
  }, [skills, nodes, pushHistory, setNodes, uiLocale])

  const filteredSkills = useMemo(() => {
    const q = skillSearch.trim().toLowerCase()
    const list = [...skills].sort((a, b) =>
      getSkillDisplayName(a, uiLocale).localeCompare(getSkillDisplayName(b, uiLocale)),
    )
    if (!q) return list
    return list.filter((s) => {
      const title = getSkillDisplayName(s, uiLocale).toLowerCase()
      return (
        title.includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q)
      )
    })
  }, [skillSearch, skills, uiLocale])

  const graphNodeSnapshots = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        type: ((n.data as any)?.nodeType || 'skill') as GraphNodeType,
        config: ((n.data as any)?.config || {}) as Record<string, unknown>,
      })),
    [nodes],
  )
  const startInputFields = useMemo(
    () => extractStartInputFields(graphNodeSnapshots),
    [graphNodeSnapshots],
  )

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(e.target)) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          if (redo()) {
            setToolHintLabel(t('workflows.canvasRedo'))
            window.clearTimeout(toolHintTimerRef.current)
            toolHintTimerRef.current = window.setTimeout(() => setToolHintLabel(null), 1200)
          }
        } else if (undo()) {
          setToolHintLabel(t('workflows.canvasUndo'))
          window.clearTimeout(toolHintTimerRef.current)
          toolHintTimerRef.current = window.setTimeout(() => setToolHintLabel(null), 1200)
        }
        return
      }
      if (e.repeat) return
      if (e.code === 'Space') {
        e.preventDefault()
        setSpaceHeld(true)
        showToolHint('space')
        return
      }
      if (e.key === 'v' || e.key === 'V') {
        selectCanvasTool('pointer')
      } else if (e.key === 'h' || e.key === 'H') {
        selectCanvasTool('pan')
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'g' || e.key === 'G')) {
        e.preventDefault()
        createGroupFromSelected()
      } else if (e.key === '=' || e.key === '+') {
        e.preventDefault()
        zoomIn({ duration: 120 })
      } else if (e.key === '-') {
        e.preventDefault()
        zoomOut({ duration: 120 })
      } else if (e.key === '0') {
        e.preventDefault()
        fitView({ padding: 0.15, duration: 200 })
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedEdgeId) {
          e.preventDefault()
          deleteEdgeById(selectedEdgeId)
        }
      }
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !isEditableTarget(e.target)) {
        e.preventDefault()
        setSpaceHeld(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.clearTimeout(toolHintTimerRef.current)
    }
  }, [fitView, redo, selectCanvasTool, showToolHint, t, undo, zoomIn, zoomOut, selectedNodeId, selectedEdgeId])

  useEffect(() => {
    const observer = new MutationObserver(() => setDark(isDarkMode()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setNodes(toFlowNodes(initial.nodes, skills, uiLocale, t))
    setEdges(toFlowEdges(initial.edges))
    clearHistory()
    const stored = parseStoredViewport(initial.viewport)
    if (stored) {
      setViewport(stored, { duration: 0 })
      viewportInitialized.current = true
    }
  }, [clearHistory, initial, skills, setEdges, setNodes, setViewport, t, uiLocale])

  const onFlowInit = useCallback(() => {
    if (viewportInitialized.current) return
    viewportInitialized.current = true
    const stored = parseStoredViewport(initial.viewport)
    if (stored) {
      setViewport(stored, { duration: 0 })
      return
    }
    fitView({ padding: 0.15, duration: 200 })
  }, [fitView, initial.viewport, setViewport])

  useEffect(() => {
    const onFullscreenChange = () => setFullScreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const onConnect = useCallback(
    (params: Connection) => {
      pushHistory()
      setEdges((eds) =>
        addEdge({ ...params, id: `e_${params.source}_${params.target}_${Date.now()}` }, eds),
      )
    },
    [pushHistory, setEdges],
  )

  const onNodesChangeWrapped = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      handleNodesChange(changes, onNodesChange)
    },
    [handleNodesChange, onNodesChange],
  )

  const onEdgesChangeWrapped = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      handleEdgesChange(changes, onEdgesChange)
    },
    [handleEdgesChange, onEdgesChange],
  )

  const addControlNode = (nodeType: GraphNodeType, position?: { x: number; y: number }) => {
    pushHistory()
    const id = `${nodeType}_${Date.now()}`
    const defaultName: Record<GraphNodeType, string> = {
      start: t('workflows.graphNodeStart'),
      skill: t('workflows.graphNodeSkill'),
      condition: t('workflows.graphNodeCondition'),
      approval: t('workflows.graphNodeApproval'),
      merge: t('workflows.graphNodeMerge'),
      batch: t('workflows.graphNodeBatch'),
      group: t('workflows.graphNodeGroup', 'Group'),
      end: t('workflows.graphNodeEnd'),
    }
    const config: Record<string, unknown> =
      nodeType === 'start'
        ? {
            input_fields: [
              { key: 'keyword', label: t('workflows.inputKeyword'), placeholder: t('workflows.inputKeywordPh'), required: true },
              { key: 'report_title', label: t('workflows.inputReportTitle'), placeholder: t('workflows.inputReportTitlePh'), required: false },
              { key: 'industry', label: t('workflows.inputIndustry'), placeholder: t('workflows.inputIndustryPh'), required: false },
            ],
          }
        : nodeType === 'merge'
          ? { merge_mode: 'sections' }
          : nodeType === 'batch'
            ? { list_path: '', max_concurrent: 3 }
            : {}
    const pos = position || { x: 120 + nodes.length * 36, y: 80 + nodes.length * 24 }
    const isBatch = nodeType === 'batch'
    const next: Node = {
      id,
      type: 'workflowNode',
      position: isBatch ? { x: pos.x, y: pos.y } : pos,
      style: isBatch ? { width: 320, height: 240 } : undefined,
      width: isBatch ? 320 : undefined,
      height: isBatch ? 240 : undefined,
      measured: isBatch ? { width: 320, height: 240 } : undefined,
      data: {
        label: defaultName[nodeType],
        nodeType,
        config,
        skillLabel: '',
        categoryLabel: '',
        skillMissing: false,
      },
    }
    setNodes((prev) => [...prev, next])
    setSelectedNodeId(id)
    setSelectedEdgeId(null)
    setPropsOpen(true)
  }

  const buildPresetNode = (preset: PatentWorkflowPreset, position: { x: number; y: number }): Node => {
    const skill = resolveSkillFromConfig({ skill_name: preset.skillName }, skills)
    const id = `${preset.id}_${Date.now()}`
    const label = getPatentPresetTitle(preset, uiLocale)
    const skillLabel = skill ? getSkillDisplayName(skill, uiLocale) : preset.skillName
    const skillMissing = preset.skillName
      ? !skills.some((s) => s.name === preset.skillName)
      : false
    return {
      id,
      type: 'workflowNode',
      position,
      data: {
        label,
        nodeType: 'skill',
        config: {
          skill_id: skill?.id || '',
          skill_name: preset.skillName,
          workflow_role: preset.workflowRole,
          payload_template: { ...preset.payloadTemplate },
        },
        skillLabel: skillMissing ? preset.skillName : skillLabel,
        categoryLabel: t(`workflows.skillCategory.${preset.workflowRole}`),
        skillMissing,
      },
    }
  }

  const addPresetNodeAt = (preset: PatentWorkflowPreset, position: { x: number; y: number }) => {
    pushHistory()
    const next = buildPresetNode(preset, position)
    setNodes((prev) => [...prev, next])
    setSelectedNodeId(next.id)
    setSelectedEdgeId(null)
    setPropsOpen(true)
  }

  const buildSkillNode = (
    skill: WorkflowSkillOption | null,
    position: { x: number; y: number },
    labelOverride?: string,
  ): Node => {
    const slug = (skill?.name || 'skill').replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 24)
    const id = `${slug}_${Date.now()}`
    const category = skill ? inferSkillCategory(skill) : 'other'
    const upstream = collectUpstreamNodeIds(
      id,
      edges.map((e) => ({ source: e.source, target: e.target })),
    )
    return {
      id,
      type: 'workflowNode',
      position,
      data: {
        label: labelOverride || (skill ? getSkillDisplayName(skill, uiLocale) : t('workflows.graphNodeSkill')),
        nodeType: 'skill',
        config: skill
          ? {
              skill_id: skill.id,
              skill_name: skill.name,
              workflow_role: category,
              payload_template: defaultPayloadForSkill(skill, upstream),
            }
          : { skill_id: '', skill_name: '', payload_template: {} },
        skillLabel: skill ? getSkillDisplayName(skill, uiLocale) : '',
        categoryLabel: skill ? t(`workflows.skillCategory.${category}`) : '',
        skillMissing: false,
      },
    }
  }

  const addSkillNodeAt = (skill: WorkflowSkillOption, position: { x: number; y: number }) => {
    pushHistory()
    const label = getSkillDisplayName(skill, uiLocale)
    const next = buildSkillNode(skill, position, label)
    // Auto-assign parent batch node if dropped inside one
    let batchId: string | null = null
    const batchNodes = nodes.filter((n) => (n.data as any)?.nodeType === 'batch' && !n.parentId)
    for (const bn of batchNodes) {
      const bw = (bn.style as any)?.width || 320
      const bh = (bn.style as any)?.height || 240
      if (position.x > bn.position.x && position.x < bn.position.x + bw && position.y > bn.position.y + 8 && position.y < bn.position.y + bh) {
        next.parentId = bn.id
        next.extent = 'parent'
        next.position = { x: position.x - bn.position.x, y: position.y - bn.position.y }
        batchId = bn.id
        break
      }
    }
    setNodes((prev) => (batchId ? recomputeBatchChildrenMeta([...prev, next], batchId) : [...prev, next]))
    setSelectedNodeId(next.id)
    setSelectedEdgeId(null)
    setPropsOpen(true)
  }

  const addEmptySkillNodeAt = (position: { x: number; y: number }) => {
    pushHistory()
    const next = buildSkillNode(null, position, t('workflows.emptySkillNode'))
    // Auto-assign parent batch
    let batchId: string | null = null
    const batchNodes = nodes.filter((n) => (n.data as any)?.nodeType === 'batch' && !n.parentId)
    for (const bn of batchNodes) {
      const bw = (bn.style as any)?.width || 320
      const bh = (bn.style as any)?.height || 240
      if (position.x > bn.position.x && position.x < bn.position.x + bw && position.y > bn.position.y + 8 && position.y < bn.position.y + bh) {
        next.parentId = bn.id
        next.extent = 'parent'
        next.position = { x: position.x - bn.position.x, y: position.y - bn.position.y }
        batchId = bn.id
        break
      }
    }
    setNodes((prev) => (batchId ? recomputeBatchChildrenMeta([...prev, next], batchId) : [...prev, next]))
    setSelectedNodeId(next.id)
    setSelectedEdgeId(null)
    setPropsOpen(true)
  }

  const removeSelected = () => {
    if (selectedNodeId) {
      deleteNodeById(selectedNodeId)
      return
    }
    if (selectedEdgeId) {
      deleteEdgeById(selectedEdgeId)
    }
  }

  const deleteNodeById = (nodeId: string) => {
    pushHistory()
    const target = nodes.find((n) => n.id === nodeId)
    const parentId = target?.parentId || undefined
    const isGroup = (target?.data as any)?.nodeType === 'group'
    setNodes((prev) => {
      let filtered = prev.filter((n) => n.id !== nodeId)
      // When deleting a group, unparent its children (convert to absolute coords)
      if (isGroup && target) {
        filtered = filtered.map((n) => {
          if (n.parentId === nodeId) {
            return {
              ...n,
              parentId: undefined,
              extent: undefined,
              position: { x: n.position.x + target.position.x, y: n.position.y + target.position.y },
            }
          }
          return n
        })
      }
      return parentId ? recomputeBatchChildrenMeta(filtered, parentId) : filtered
    })
    setEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId))
    if (selectedNodeId === nodeId) setSelectedNodeId(null)
  }

  const deleteEdgeById = (edgeId: string) => {
    pushHistory()
    setEdges((prev) => prev.filter((e) => e.id !== edgeId))
    if (selectedEdgeId === edgeId) setSelectedEdgeId(null)
  }

  const duplicateNodeById = (nodeId: string) => {
    const source = nodes.find((n) => n.id === nodeId)
    if (!source) return
    pushHistory()
    const copy: Node = {
      ...source,
      id: `${nodeId}_copy_${Date.now()}`,
      position: { x: source.position.x + 40, y: source.position.y + 40 },
      selected: true,
    }
    setNodes((prev) => [...prev.map((n) => ({ ...n, selected: false })), copy])
    setSelectedNodeId(copy.id)
    setPropsOpen(true)
  }

  const createGroupFromSelected = useCallback(() => {
    const selected = nodes.filter((n) => n.selected && (n.data as any)?.nodeType !== 'group' && !n.parentId)
    if (selected.length === 0) return
    pushHistory()
    const bounds = computeGroupBounds(selected)
    const groupId = `group_${Date.now()}`
    const groupNode: Node = {
      id: groupId,
      type: 'workflowGroup',
      position: { x: bounds.x, y: bounds.y },
      style: { width: bounds.width, height: bounds.height },
      width: bounds.width,
      height: bounds.height,
      measured: { width: bounds.width, height: bounds.height },
      data: {
        label: t('workflows.groupDefaultName', 'Group'),
        nodeType: 'group',
        config: { color: '#64748b', collapsed: false },
        groupChildCount: selected.length,
      },
    }
    setNodes((prev) => {
      let updated = [...prev.filter((n) => !n.selected), groupNode]
      // Reparent selected nodes into the group
      updated = updated.map((n) => {
        if (selected.some((s) => s.id === n.id)) {
          return {
            ...n,
            parentId: groupId,
            extent: 'parent' as const,
            position: { x: n.position.x - bounds.x, y: n.position.y - bounds.y },
            selected: false,
          }
        }
        return n
      })
      return updated
    })
  }, [nodes, pushHistory, setNodes, t])

  // Listen for group node events (toggle collapse, rename, color change)
  useEffect(() => {
    const onToggle = (e: Event) => {
      const { groupId } = (e as CustomEvent).detail
      setNodes((prev) => prev.map((n) => {
        if (n.id !== groupId) return n
        const cfg = (n.data as any)?.config || {}
        const collapsed = !cfg.collapsed
        return {
          ...n,
          data: { ...n.data, config: { ...cfg, collapsed } },
          // Hide/show children
        }
      }))
      // Toggle children visibility
      setNodes((prev) => {
        const group = prev.find((n) => n.id === groupId)
        const collapsed = (group?.data as any)?.config?.collapsed
        if (collapsed === undefined) return prev
        return prev.map((n) => {
          if (n.parentId === groupId) {
            return { ...n, hidden: collapsed }
          }
          return n
        })
      })
    }
    const onRename = (e: Event) => {
      const { groupId, label } = (e as CustomEvent).detail
      setNodes((prev) => prev.map((n) =>
        n.id === groupId ? { ...n, data: { ...n.data, label } } : n,
      ))
    }
    const onColor = (e: Event) => {
      const { groupId, color } = (e as CustomEvent).detail
      setNodes((prev) => prev.map((n) => {
        if (n.id !== groupId) return n
        const cfg = (n.data as any)?.config || {}
        return { ...n, data: { ...n.data, config: { ...cfg, color } } }
      }))
    }
    window.addEventListener('mchat-group-toggle', onToggle)
    window.addEventListener('mchat-group-rename', onRename)
    window.addEventListener('mchat-group-color', onColor)
    return () => {
      window.removeEventListener('mchat-group-toggle', onToggle)
      window.removeEventListener('mchat-group-rename', onRename)
      window.removeEventListener('mchat-group-color', onColor)
    }
  }, [setNodes])

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const autoAssignParent = useCallback((nodeId: string, absolutePos: { x: number; y: number }) => {
    const batchNodes = nodes.filter((n) => (n.data as any)?.nodeType === 'batch' && n.id !== nodeId && !n.parentId)
    for (const bn of batchNodes) {
      const bw = (bn.style as any)?.width || 320
      const bh = (bn.style as any)?.height || 240
      if (
        absolutePos.x > bn.position.x &&
        absolutePos.x < bn.position.x + bw &&
        absolutePos.y > bn.position.y + 8 &&
        absolutePos.y < bn.position.y + bh
      ) {
        setNodes((prev) => {
          let updated = prev.map((n) => {
            if (n.id === nodeId) {
              return { ...n, parentId: bn.id, extent: 'parent' as const, position: { x: absolutePos.x - bn.position.x, y: absolutePos.y - bn.position.y } }
            }
            return n
          })
          updated = recomputeBatchChildrenMeta(updated, bn.id)
          return updated
        })
        return true
      }
    }
    return false
  }, [nodes, setNodes])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setContextMenu(null)
      const raw = event.dataTransfer.getData(DRAG_MIME)
      if (!raw || !reactFlowWrapper.current) return
      let payload: { kind: string; skillId?: string; presetId?: string; nodeType?: string }
      try {
        payload = JSON.parse(raw)
      } catch {
        return
      }
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })

      // Check if drop target is inside a batch container node
      const batchEl = (event.target as HTMLElement)?.closest('[data-batch-container]')
      if (batchEl && payload.kind === 'skill' && payload.skillId) {
        const batchId = batchEl.getAttribute('data-batch-id')
        if (batchId) {
          const skill = skills.find((s) => s.id === payload.skillId)
          if (skill) {
            pushHistory()
            const label = getSkillDisplayName(skill, uiLocale)
            const batchNode = nodes.find((n) => n.id === batchId)
            const relPos = batchNode
              ? { x: position.x - batchNode.position.x, y: position.y - batchNode.position.y }
              : { x: 20, y: 60 + (nodes.filter((n) => n.parentId === batchId).length * 50) }
            const childNode = buildSkillNode(skill, relPos, label)
            childNode.parentId = batchId
            childNode.extent = 'parent'
            setNodes((prev) => recomputeBatchChildrenMeta([...prev, childNode], batchId))
            setSelectedNodeId(childNode.id)
            setSelectedEdgeId(null)
            setPropsOpen(true)
            return
          }
        }
      }

      if (payload.kind === 'control' && payload.nodeType) {
        addControlNode(payload.nodeType as GraphNodeType, position)
      } else if (payload.kind === 'skill' && payload.skillId) {
        const skill = skills.find((s) => s.id === payload.skillId)
        if (skill) addSkillNodeAt(skill, position)
      } else if (payload.kind === 'patent-preset' && payload.presetId) {
        const preset = getPatentPresetById(payload.presetId, patentPresets)
        if (preset) addPresetNodeAt(preset, position)
      } else if (payload.kind === 'skill-empty') {
        addEmptySkillNodeAt(position)
      }
    },
    [edges, nodes.length, patentPresets, skills, screenToFlowPosition, t, uiLocale],
  )

  const beginSkillDrag = (event: React.DragEvent, skill: WorkflowSkillOption) => {
    event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'skill', skillId: skill.id }))
    event.dataTransfer.effectAllowed = 'move'
  }

  const beginPresetDrag = (event: React.DragEvent, presetId: string) => {
    event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'patent-preset', presetId }))
    event.dataTransfer.effectAllowed = 'move'
  }

  const beginEmptySkillDrag = (event: React.DragEvent) => {
    event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'skill-empty' }))
    event.dataTransfer.effectAllowed = 'move'
  }

  const beginControlNodeDrag = (event: React.DragEvent, nodeType: GraphNodeType) => {
    event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ kind: 'control', nodeType }))
    event.dataTransfer.effectAllowed = 'move'
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null
  const selectedEdge = edges.find((e) => e.id === selectedEdgeId) || null
  const selectedNodeConfig = ((selectedNode?.data as any)?.config || {}) as Record<string, unknown>
  const selectedNodeType = ((selectedNode?.data as any)?.nodeType || 'skill') as GraphNodeType
  const upstreamForSelected = selectedNode
    ? collectUpstreamNodeIds(
        selectedNode.id,
        edges.map((e) => ({ source: e.source, target: e.target })),
      )
    : []

  const updateNodeData = (nodeId: string, updater: (data: any) => any) => {
    setNodes((prev) =>
      prev.map((n) => {
        if (n.id !== nodeId) return n
        const nextData = updater(n.data as any)
        if (nextData.nodeType === 'skill') {
          const cfg = enrichSkillConfig(nextData.config || {}, skills)
          nextData.config = cfg
          nextData.skillLabel = skillLabelForNode(cfg, skills, uiLocale)
          const cat = String(cfg.workflow_role || inferSkillCategory({ id: '', name: nextData.skillLabel, config: cfg }))
          nextData.categoryLabel = t(`workflows.skillCategory.${cat}`)
          nextData.skillMissing = isSkillMissing(cfg, skills)
        }
        return { ...n, data: nextData }
      }),
    )
  }

  const updateNodeConfig = (key: string, value: unknown) => {
    if (!selectedNode) return
    updateNodeData(selectedNode.id, (data) => ({
      ...data,
      config: { ...(data?.config || {}), [key]: value },
    }))
  }

  const toggleFullscreen = async () => {
    const el = containerRef.current
    if (!el) return
    if (document.fullscreenElement) await document.exitFullscreen()
    else await el.requestFullscreen()
  }

  const applyTemplate = (graph: WorkflowGraphValue) => {
    pushHistory()
    const tplNodes = (graph.nodes || []).map((n: WorkflowGraphValue['nodes'][number]) => ({ ...n, type: n.type as GraphNodeType }))
    const tplEdges = (graph.edges || []).map((e: WorkflowGraphValue['edges'][number]) => ({ ...e }))
    setNodes(toFlowNodes(tplNodes, skills, uiLocale, t))
    setEdges(toFlowEdges(tplEdges))
    setPropsOpen(false)
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
    setTimeout(() => fitView({ padding: 0.2 }), 100)
  }

  const saveGraph = () => {
    onSave({
      version: 1,
      nodes: nodes.map((n) => {
        const nodeType = ((n.data as any)?.nodeType || 'skill') as GraphNodeType
        const rawConfig = ((n.data as any)?.config || {}) as Record<string, unknown>
        const config = nodeType === 'skill' ? enrichSkillConfig(rawConfig, skills) : rawConfig
        // Persist group dimensions so they survive save/reload
        if (nodeType === 'group') {
          config.width = n.width || (n.style as any)?.width || 280
          config.height = n.height || (n.style as any)?.height || 160
        }
        return {
          id: n.id,
          type: nodeType,
          name: String((n.data as any)?.label || ''),
          position: n.position,
          parentId: n.parentId || undefined,
          config,
        }
      }),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle || undefined,
        target_handle: e.targetHandle || undefined,
        condition: (typeof e.label === 'string' && e.label) || undefined,
      })),
      viewport: getViewport(),
    })
  }

  const nodeTypeLabel = (type: GraphNodeType) => {
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
    return map[type]
  }

  const openJsonEditor = () => {
    setJsonError('')
    if (selectedNode) {
      setJsonDraft(JSON.stringify(selectedNodeConfig || {}, null, 2))
      return
    }
    if (selectedEdge) {
      setJsonDraft(JSON.stringify({ condition: typeof selectedEdge.label === 'string' ? selectedEdge.label : '' }, null, 2))
      return
    }
    setJsonDraft('{}')
  }

  const applyJsonDraft = () => {
    try {
      const parsed = JSON.parse(jsonDraft || '{}')
      if (selectedNode) updateNodeData(selectedNode.id, (data) => ({ ...data, config: parsed }))
      else if (selectedEdge) {
        setEdges((prev) =>
          prev.map((e) => (e.id === selectedEdge.id ? { ...e, label: String(parsed.condition || '') } : e)),
        )
      }
      setJsonError('')
    } catch {
      setJsonError(t('workflows.graphJsonInvalid'))
    }
  }

  const handleNodeSearchSelect = (rawPayload: string) => {
    if (!nodeSearch.pos) return
    const flowPos = screenToFlowPosition({ x: nodeSearch.pos.x, y: nodeSearch.pos.y })
    let payload: { kind: string; nodeType?: string; skillId?: string }
    try { payload = JSON.parse(rawPayload) } catch { return }
    if (payload.kind === 'control' && payload.nodeType) {
      addControlNode(payload.nodeType as GraphNodeType, flowPos)
    } else if (payload.kind === 'skill' && payload.skillId) {
      const skill = skills.find((s) => s.id === payload.skillId)
      if (skill) addSkillNodeAt(skill, flowPos)
    } else if (payload.kind === 'skill-empty') {
      addEmptySkillNodeAt(flowPos)
    }
    setNodeSearch({ open: false, pos: null })
  }

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-col bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-2 py-1 dark:border-gray-800">
        <div className="flex items-center gap-1.5 min-w-0">
          {onBack && (
            <button type="button" onClick={onBack} className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" title={t('common.back', 'Back')}>
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <p className="truncate text-xs font-semibold text-gray-700 dark:text-gray-200">{workflowName || t('workflows.graphEditorTitle')}</p>
        </div>
        <div className="flex items-center gap-1">
          {headerExtra}
          <button
            type="button"
            onClick={toggleFullscreen}
            title={fullScreen ? t('workflows.graphExitFullscreen') : t('workflows.graphFullscreen')}
            className="inline-flex items-center justify-center rounded-md border border-gray-200 dark:border-gray-700 p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            {fullScreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={removeSelected}
            disabled={!selectedNodeId && !selectedEdgeId}
            title={t('workflows.graphDeleteSelected')}
            className="inline-flex items-center justify-center rounded-md border border-gray-200 dark:border-gray-700 p-1.5 text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={saveGraph} className="flex items-center gap-1 rounded-md bg-primary-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-primary-700">
            <Save className="h-3.5 w-3.5" />
            {t('workflows.graphSave')}
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!paletteOpen ? (
          <PanelEdgeToggle side="left" title={t('workflows.graphShowLeft')} onClick={() => setPaletteOpen(true)} />
        ) : null}

        {paletteOpen ? (
          <aside className="flex w-64 shrink-0 flex-col border-r border-gray-200 dark:border-gray-800">
            <div className="flex items-center justify-between border-b border-gray-200 px-2 py-1.5 dark:border-gray-800">
              <span className="text-xs font-medium">{t('workflows.graphNodeLibrary')}</span>
              <button type="button" title={t('workflows.graphHideLeft')} aria-label={t('workflows.graphHideLeft')} onClick={() => setPaletteOpen(false)} className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <WorkflowSidebar
              skills={skills}
              locale={uiLocale}
              onAddControlNode={(nt) => addControlNode(nt)}
              presets={presets}
            />
          </aside>
        ) : null}

        <div
          ref={reactFlowWrapper}
          tabIndex={0}
          className={cn(
            'min-h-0 min-w-0 flex-1 bg-white dark:bg-gray-900',
            !isPointerTool && '[&_.react-flow__pane]:cursor-grab [&_.react-flow__pane:active]:cursor-grabbing',
          )}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onKeyDown={(e) => {
            if (isEditableTarget(e.target as HTMLElement)) return
            if (e.key === 'Delete' || e.key === 'Backspace') {
              if (selectedNodeId) {
                e.preventDefault()
                e.stopPropagation()
                deleteNodeById(selectedNodeId)
              } else if (selectedEdgeId) {
                e.preventDefault()
                e.stopPropagation()
                deleteEdgeById(selectedEdgeId)
              }
            }
          }}
        >
          <ReactFlow
            className="h-full w-full"
            nodeTypes={{ ...workflowNodeTypes, ...groupNodeTypes }}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChangeWrapped}
            onEdgesChange={onEdgesChangeWrapped}
            onConnect={onConnect}
            onNodeDragStart={onNodeDragStart}
            onNodeDragStop={(event, node) => {
              onNodeDragStop()
              const halfW = ((node.style as any)?.width || 180) / 2
              const halfH = ((node.style as any)?.height || 40) / 2
              // node.position is relative to parent when the node is already a child;
              // convert to canvas-absolute coordinates before comparing with batch rects.
              const parentOfDragged = node.parentId ? nodes.find((n) => n.id === node.parentId) : null
              const absLeft = node.position.x + (parentOfDragged?.position.x || 0)
              const absTop = node.position.y + (parentOfDragged?.position.y || 0)
              const cx = absLeft + halfW
              const cy = absTop + halfH
              const batchNodes = nodes.filter((n) => (n.data as any)?.nodeType === 'batch' && n.id !== node.id)
              let targetBatch: Node | null = null
              for (const bn of batchNodes) {
                const bw = (bn.style as any)?.width || 320
                const bh = (bn.style as any)?.height || 240
                if (cx > bn.position.x && cx < bn.position.x + bw && cy > bn.position.y && cy < bn.position.y + bh) {
                  targetBatch = bn
                  break
                }
              }
              if (targetBatch) {
                if (node.parentId !== targetBatch.id) {
                  const previousParentId = node.parentId
                  setNodes((prev) => {
                    let updated = prev.map((n) => (n.id === node.id
                      ? { ...n, parentId: targetBatch.id, extent: 'parent' as const, position: { x: absLeft - targetBatch.position.x, y: absTop - targetBatch.position.y } }
                      : n))
                    updated = recomputeBatchChildrenMeta(updated, targetBatch.id)
                    if (previousParentId) updated = recomputeBatchChildrenMeta(updated, previousParentId)
                    return updated
                  })
                }
                return
              }
              // Center is outside every batch: detach if it was a child.
              if (node.parentId) {
                const previousParentId = node.parentId
                setNodes((prev) => {
                  let updated = prev.map((n) => {
                    if (n.id !== node.id || !n.parentId) return n
                    return { ...n, parentId: undefined, extent: undefined, position: { x: absLeft, y: absTop } }
                  })
                  updated = recomputeBatchChildrenMeta(updated, previousParentId)
                  return updated
                })
              }
            }}
            onInit={onFlowInit}
            minZoom={0.08}
            maxZoom={2.5}
            zoomOnScroll
            zoomOnPinch
            zoomOnDoubleClick={false}
            panOnScroll={false}
            panOnDrag={isPointerTool ? [1, 2] : true}
            selectionOnDrag={isPointerTool}
            selectionKeyCode={isPointerTool ? 'Shift' : null}
            nodesDraggable={isPointerTool}
            nodesConnectable={isPointerTool}
            elementsSelectable={isPointerTool}
            deleteKeyCode={null}
            multiSelectionKeyCode="Shift"
            proOptions={{ hideAttribution: true }}
            onNodesDelete={(deleted) => {
              pushHistory()
              const ids = new Set(deleted.map((n) => n.id))
              setEdges((prev) => prev.filter((e) => !ids.has(e.source) && !ids.has(e.target)))
              if (selectedNodeId && ids.has(selectedNodeId)) setSelectedNodeId(null)
            }}
            onEdgesDelete={(deleted) => {
              pushHistory()
              const ids = new Set(deleted.map((e) => e.id))
              if (selectedEdgeId && ids.has(selectedEdgeId)) setSelectedEdgeId(null)
            }}
            onNodeClick={(_, node) => {
              if (!isPointerTool) return
              setContextMenu(null)
              setSelectedNodeId(node.id)
              setSelectedEdgeId(null)
              setSelectedTab('visual')
              setPropsOpen(true)
            }}
            onEdgeClick={(_, edge) => {
              if (!isPointerTool) return
              setContextMenu(null)
              setSelectedEdgeId(edge.id)
              setSelectedNodeId(null)
              setSelectedTab('visual')
              setPropsOpen(true)
            }}
            onNodeContextMenu={(e, node) => {
              if (!isPointerTool) return
              e.preventDefault()
              setSelectedNodeId(node.id)
              setSelectedEdgeId(null)
              setPropsOpen(true)
              setContextMenu({ kind: 'node', x: e.clientX, y: e.clientY, nodeId: node.id })
            }}
            onEdgeContextMenu={(e, edge) => {
              if (!isPointerTool) return
              e.preventDefault()
              setSelectedEdgeId(edge.id)
              setSelectedNodeId(null)
              setContextMenu({ kind: 'edge', x: e.clientX, y: e.clientY, edgeId: edge.id })
            }}
            onPaneContextMenu={(e) => {
              e.preventDefault()
              const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
              setContextMenu({ kind: 'pane', x: e.clientX, y: e.clientY, flowX: position.x, flowY: position.y })
            }}
            onDoubleClick={(e) => {
              // ComfyUI-style: double-click empty canvas → node search popup
              if (e.target instanceof HTMLElement && e.target.closest('.react-flow__node')) return
              setNodeSearch({ open: true, pos: { x: e.clientX, y: e.clientY } })
            }}
            onPaneClick={() => { setContextMenu(null); setNodeSearch({ open: false, pos: null }) }}
            colorMode={dark ? 'dark' : 'light'}
          >
            <Background gap={20} size={1} />
            <WorkflowCanvasToolbar
              canvasTool={canvasTool}
              onCanvasToolChange={selectCanvasTool}
              spacePanActive={spaceHeld}
              zoom={zoom}
              showMinimap={showMinimap}
              onToggleMinimap={() => setShowMinimap((v) => !v)}
              onZoomIn={() => zoomIn({ duration: 120 })}
              onZoomOut={() => zoomOut({ duration: 120 })}
              onFitView={() => fitView({ padding: 0.15, duration: 200 })}
              onResetZoom={() => setViewport({ ...getViewport(), zoom: 1 }, { duration: 150 })}
            />
            <WorkflowCanvasToolHint label={toolHintLabel} />
            {showMinimap ? (
              <Panel position="bottom-right" className="!m-3">
                <MiniMap
                  className="mchat-workflow-minimap !rounded-lg !border !border-gray-300 !shadow-lg dark:!border-gray-600"
                  nodeColor={(node) => {
                    const nodeType = ((node.data as { nodeType?: GraphNodeType })?.nodeType || 'skill') as GraphNodeType
                    return NODE_COLORS[nodeType] || '#94a3b8'
                  }}
                  nodeStrokeWidth={2}
                  maskColor={dark ? 'rgba(15, 23, 42, 0.62)' : 'rgba(255, 255, 255, 0.72)'}
                  pannable
                  zoomable
                />
              </Panel>
            ) : null}
          </ReactFlow>
        </div>

        <WorkflowGraphContextMenu
          menu={contextMenu}
          onClose={() => setContextMenu(null)}
          onDeleteNode={deleteNodeById}
          onDuplicateNode={duplicateNodeById}
          onDeleteEdge={deleteEdgeById}
          onSetEdgeCondition={(edgeId, condition) => {
            setEdges((prev) =>
              prev.map((edge) => (edge.id === edgeId ? { ...edge, label: condition } : edge)),
            )
          }}
          onAddControlAt={(nodeType, position) => addControlNode(nodeType as GraphNodeType, position)}
          onAddSkillAt={(skill, position) => addSkillNodeAt(skill, position)}
          onGroupSelected={createGroupFromSelected}
          selectedCount={nodes.filter((n) => n.selected).length}
          skills={filteredSkills}
        />

        {!propsOpen ? (
          <PanelEdgeToggle side="right" title={t('workflows.graphShowRight')} onClick={() => setPropsOpen(true)} />
        ) : null}

        {propsOpen ? (
          <aside className="flex w-80 shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-2 py-1.5 dark:border-gray-800">
              <button type="button" title={t('workflows.graphHideRight')} aria-label={t('workflows.graphHideRight')} onClick={() => setPropsOpen(false)} className="rounded p-0.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">
                <ChevronRight className="h-4 w-4" />
              </button>
              <span className="text-xs font-medium">{t('workflows.graphProperties')}</span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {!selectedNode && !selectedEdge ? (
                <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.graphSelectHint')}</p>
              ) : (
                <>
                  <Tabs
                    tabs={[
                      { id: 'visual', label: t('workflows.graphTabVisual') },
                      { id: 'json', label: 'JSON' },
                    ]}
                    activeTab={selectedTab}
                    onChange={(tab) => {
                      const next = tab as 'visual' | 'json'
                      setSelectedTab(next)
                      if (next === 'json') openJsonEditor()
                    }}
                  />
                  <TabPanel id="visual" activeTab={selectedTab}>
                    {selectedNode ? (
                      <div className="space-y-2">
                        <Input
                          label={t('workflows.graphLabel')}
                          value={String((selectedNode.data as any)?.label || '')}
                          onChange={(e) => updateNodeData(selectedNode.id, (data) => ({ ...data, label: e.target.value }))}
                        />
                        {selectedNodeType === 'start' ? (
                          <div className="space-y-2">
                            <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.startNodeHint')}</p>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-300">{t('workflows.startInputFields')}</span>
                                <button
                                  type="button"
                                  className="inline-flex h-5 w-5 items-center justify-center rounded text-xs text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-950"
                                  onClick={() => {
                                    const fields = [...(Array.isArray(selectedNodeConfig.input_fields) ? selectedNodeConfig.input_fields : [])]
                                    fields.push({ key: '', label: '', placeholder: '', required: false })
                                    updateNodeConfig('input_fields', fields)
                                  }}
                                >
                                  <Plus className="h-3.5 w-3.5" />
                                </button>
                              </div>
                              {(Array.isArray(selectedNodeConfig.input_fields) ? selectedNodeConfig.input_fields as InputFieldDef[] : []).map((field, idx) => (
                                <div key={idx} className="rounded border border-gray-200 p-2 space-y-1 dark:border-gray-700">
                                  <div className="flex items-center gap-1">
                                    <Input
                                      placeholder={t('workflows.startFieldKey')}
                                      value={field.key || ''}
                                      onChange={(e) => {
                                        const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                        fields[idx] = { ...fields[idx], key: e.target.value }
                                        updateNodeConfig('input_fields', fields)
                                      }}
                                    />
                                    <button
                                      type="button"
                                      className="shrink-0 inline-flex h-6 w-6 items-center justify-center rounded text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950"
                                      onClick={() => {
                                        const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                        fields.splice(idx, 1)
                                        updateNodeConfig('input_fields', fields)
                                      }}
                                    >
                                      <X className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                  <Input
                                    placeholder={t('workflows.startFieldLabel')}
                                    value={field.label || ''}
                                    onChange={(e) => {
                                      const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                      fields[idx] = { ...fields[idx], label: e.target.value }
                                      updateNodeConfig('input_fields', fields)
                                    }}
                                  />
                                  <div className="flex items-center gap-2">
                                    <Input
                                      placeholder={t('workflows.startFieldPlaceholder')}
                                      value={field.placeholder || ''}
                                      onChange={(e) => {
                                        const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                        fields[idx] = { ...fields[idx], placeholder: e.target.value }
                                        updateNodeConfig('input_fields', fields)
                                      }}
                                    />
                                    <label className="flex shrink-0 items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(field.required)}
                                        onChange={(e) => {
                                          const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                          fields[idx] = { ...fields[idx], required: e.target.checked }
                                          updateNodeConfig('input_fields', fields)
                                        }}
                                        className="h-3 w-3"
                                      />
                                      {t('workflows.startFieldRequired')}
                                    </label>
                                    <select
                                      className="h-6 rounded border border-gray-300 bg-white text-[10px] dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                                      value={field.type || 'text'}
                                      onChange={(e) => {
                                        const fields = [...(selectedNodeConfig.input_fields as InputFieldDef[])]
                                        fields[idx] = { ...fields[idx], type: e.target.value as InputFieldDef['type'] }
                                        updateNodeConfig('input_fields', fields)
                                      }}
                                    >
                                      <option value="text">{t('workflows.fieldTypeText')}</option>
                                      <option value="multiline">{t('workflows.fieldTypeMultiline')}</option>
                                      <option value="number">{t('workflows.fieldTypeNumber')}</option>
                                      <option value="file">{t('workflows.fieldTypeFile')}</option>
                                    </select>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        {selectedNodeType === 'merge' ? (
                          <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.mergeNodeHint')}</p>
                        ) : null}
                        {selectedNodeType === 'batch' ? (
                          <div className="space-y-2">
                            <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.batchNodeHint')}</p>
                            <div className="rounded-lg border border-cyan-200 bg-cyan-50 dark:border-cyan-800 dark:bg-cyan-950/30 p-3">
                              <p className="text-xs text-cyan-700 dark:text-cyan-300 font-medium mb-1">{t('workflows.batchHowTo')}</p>
                              <p className="text-xs text-cyan-600 dark:text-cyan-400">{t('workflows.batchHowToDesc')}</p>
                            </div>
                            <div>
                              <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.batchListPath')}</label>
                              <input placeholder="input.urls 或 nodes.fetch.result.links" value={String(selectedNodeConfig.list_path || '')} onChange={(e) => updateNodeConfig('list_path', e.target.value)} className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                            </div>
                            <div>
                              <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.batchItemKey')}</label>
                              <input placeholder="line / url" value={String(selectedNodeConfig.item_key || '')} onChange={(e) => updateNodeConfig('item_key', e.target.value)} className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                            </div>
                            <div>
                              <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.graphMaxConcurrent', '并发数')}</label>
                              <input type="number" value={String(selectedNodeConfig.max_concurrent ?? 3)} onChange={(e) => updateNodeConfig('max_concurrent', toSafeInt(e.target.value, 3))} className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                            </div>
                          </div>
                        ) : null}
                        {selectedNodeType === 'skill' ? (
                          <>
                            {isSkillMissing(selectedNodeConfig, skills) ? (
                              <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                                {t('workflows.skillNotInstalled', {
                                  name: String(selectedNodeConfig.skill_name || selectedNodeConfig.skill_id || ''),
                                })}
                                {' '}
                                <Link to="/admin/skills" className="underline">{t('workflows.manageSkills')}</Link>
                              </p>
                            ) : null}
                            <label className="block text-xs text-gray-600 dark:text-gray-300">{t('workflows.graphSkillSelect')}</label>
                            <select
                              className="block w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                              value={resolveSkillFromConfig(selectedNodeConfig, skills)?.id || String(selectedNodeConfig.skill_id || '')}
                              onChange={(e) => {
                                const skill = skills.find((s) => s.id === e.target.value)
                                updateNodeData(selectedNode.id, (data) => ({
                                  ...data,
                                  config: {
                                    ...(data.config || {}),
                                    skill_id: e.target.value,
                                    skill_name: skill?.name || '',
                                    workflow_role: skill ? inferSkillCategory(skill) : data.config?.workflow_role,
                                  },
                                }))
                              }}
                            >
                              <option value="">{t('workflows.graphSkillPlaceholder')}</option>
                              {skills.map((skill) => (
                                <option key={skill.id} value={skill.id}>
                                  {getSkillDisplayName(skill, uiLocale)} ({skill.name})
                                </option>
                              ))}
                            </select>
                            <div className="grid grid-cols-2 gap-2">
                              <div>
                                <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.graphRetryCount')}</label>
                                <input type="number" value={String(selectedNodeConfig.retry_count ?? 0)} onChange={(e) => updateNodeConfig('retry_count', toSafeInt(e.target.value, 0))} className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                              </div>
                              <div>
                                <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.graphTimeoutSec')}</label>
                                <input type="number" value={String(selectedNodeConfig.timeout_seconds ?? 0)} onChange={(e) => updateNodeConfig('timeout_seconds', toSafeInt(e.target.value, 0))} className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                              </div>
                            </div>
                            {(() => {
                            const selSkill = skills.find((s) => s.name === String(selectedNodeConfig.skill_name || ''))
                            return (
                            <PayloadMapper
                              skillName={String(selectedNodeConfig.skill_name || '')}
                              fields={startInputFields}
                              upstreamNodeIds={upstreamForSelected}
                              payload={(selectedNodeConfig.payload_template || {}) as Record<string, unknown>}
                              onChange={(next) => updateNodeConfig('payload_template', next)}
                              workflowFields={(selSkill?.config as any)?.workflow_fields}
                            />)})()}
                          </>
                        ) : null}
                        {selectedNodeType === 'condition' ? (
                          <div className="space-y-2">
                            <div>
                              <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.graphConditionLeft')}</label>
                              <input value={String(selectedNodeConfig.left || '')} onChange={(e) => updateNodeConfig('left', e.target.value)} placeholder="input.keyword 或 nodes.x.result.field" className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                            </div>
                            <select className="block w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100" value={String(selectedNodeConfig.op || '==')} onChange={(e) => updateNodeConfig('op', e.target.value)}>
                              <option value="==">== (等于)</option>
                              <option value="!=">!= (不等于)</option>
                              <option value=">">&gt; (大于)</option>
                              <option value="<">&lt; (小于)</option>
                              <option value=">=">&gt;= (大于等于)</option>
                              <option value="<=">&lt;= (小于等于)</option>
                              <option value="contains">contains (包含)</option>
                              <option value="not_contains">not_contains (不包含)</option>
                              <option value="startswith">startswith (前缀)</option>
                              <option value="endswith">endswith (后缀)</option>
                            </select>
                            <div>
                              <label className="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">{t('workflows.graphConditionRight')}</label>
                              <input value={String(selectedNodeConfig.right ?? '')} onChange={(e) => updateNodeConfig('right', e.target.value)} placeholder="静态值 或 ${nodes.x.result.field}" className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                            </div>
                            <p className="text-[10px] text-gray-400">支持 ${'{' + 'input.xxx}'}/{'}{'}nodes.xxx.result{'}'}, right 也支持模板变量</p>
                          </div>
                        ) : null}
                        {selectedNodeType === 'approval' ? (
                          <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.graphApprovalHint')}</p>
                        ) : null}
                        {selectedNodeType === 'end' ? (
                          <div className="space-y-2">
                            <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.endNodeHint')}</p>
                            {upstreamForSelected.length > 0 ? (
                              <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
                                <p className="text-[10px] font-medium text-gray-500 mb-1">{t('workflows.endNodeUpstream')}</p>
                                {upstreamForSelected.map((uid) => {
                                  const un = nodes.find((n) => n.id === uid)
                                  const uName = String((un?.data as any)?.label || un?.id || uid)
                                  return (
                                    <p key={uid} className="text-[10px] text-gray-600 dark:text-gray-300">
                                      • {uName} &rarr; <code className="text-[10px]">{`\${nodes.${uid}.result}`}</code>
                                    </p>
                                  )
                                })}
                              </div>
                            ) : (
                              <p className="text-[10px] text-amber-600 dark:text-amber-400">{t('workflows.endNodeNoUpstream')}</p>
                            )}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {selectedEdge ? (
                      <div className="space-y-2">
                        <select
                          className="block w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                          value={typeof selectedEdge.label === 'string' ? selectedEdge.label : ''}
                          onChange={(e) => setEdges((prev) => prev.map((edge) => (edge.id === selectedEdge.id ? { ...edge, label: e.target.value } : edge)))}
                        >
                          <option value="">{t('workflows.graphEdgeDefault')}</option>
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      </div>
                    ) : null}
                  </TabPanel>
                  <TabPanel id="json" activeTab={selectedTab}>
                    <textarea className="mt-2 h-72 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100" value={jsonDraft} onChange={(e) => setJsonDraft(e.target.value)} />
                    {jsonError ? <p className="text-xs text-red-600">{jsonError}</p> : null}
                    <div className="mt-2 flex justify-end">
                      <Button size="sm" variant="secondary" onClick={applyJsonDraft}>{t('workflows.graphApplyJson')}</Button>
                    </div>
                  </TabPanel>
                </>
              )}
            </div>
          </aside>
        ) : null}
      </div>

      {/* ComfyUI-style double-click node search */}
      <WorkflowNodeSearch
        open={nodeSearch.open}
        position={nodeSearch.pos}
        skills={skills}
        locale={uiLocale}
        onSelect={handleNodeSearchSelect}
        onClose={() => setNodeSearch({ open: false, pos: null })}
      />
    </div>
  )
}
