import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  GripVertical,
  Hand,
  Maximize2,
  Minimize2,
  MousePointer2,
  Save,
  Trash2,
} from 'lucide-react'
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { cn } from '@/lib/utils'
import {
  CONTROL_NODE_TYPES,
  NODE_COLORS,
  collectUpstreamNodeIds,
  defaultPayloadForSkill,
  extractStartInputFields,
  inferSkillCategory,
  type GraphNodeType,
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
import { workflowNodeTypes } from '@/components/workflow/WorkflowCanvasNode'
import {
  WorkflowGraphContextMenu,
  type GraphContextMenuState,
} from '@/components/workflow/WorkflowGraphContextMenu'

export type { GraphNodeType }

type CanvasTool = 'pointer' | 'pan'

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
}

function isDarkMode() {
  return document.documentElement.classList.contains('dark')
}

function toSafeInt(value: string, fallback: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.max(0, Math.floor(n))
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
  return graphNodes.map((node) => {
    const config = node.config || {}
    const skillLabel = node.type === 'skill' ? skillLabelForNode(config, skills, locale) : ''
    const category =
      node.type === 'skill'
        ? t(`workflows.skillCategory.${String(config.workflow_role || inferSkillCategory({ id: '', name: skillLabel || node.name || '', config }))}`)
        : ''
    const skillMissing = node.type === 'skill' ? isSkillMissing(config, skills) : false
    return {
      id: node.id,
      type: 'workflowNode',
      position: node.position || { x: 100, y: 100 },
      data: {
        label: node.name || node.id,
        nodeType: node.type,
        config,
        skillLabel: skillMissing && config.skill_name ? String(config.skill_name) : skillLabel,
        categoryLabel: category,
        skillMissing,
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

function WorkflowGraphEditorInner({ value, skills, onSave }: Props) {
  const { t, i18n } = useTranslation()
  const uiLocale = i18n.language || 'zh'
  const { screenToFlowPosition } = useReactFlow()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const reactFlowWrapper = useRef<HTMLDivElement | null>(null)
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
  const [canvasTool, setCanvasTool] = useState<CanvasTool>('pointer')
  const isPointerTool = canvasTool === 'pointer'
  const [showcaseConfig, setShowcaseConfig] = useState<PatentShowcaseConfig | null>(null)

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
      if (e.repeat || isEditableTarget(e.target)) return
      if (e.key === 'v' || e.key === 'V') {
        setCanvasTool('pointer')
      } else if (e.key === 'h' || e.key === 'H') {
        setCanvasTool('pan')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    const observer = new MutationObserver(() => setDark(isDarkMode()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setNodes(toFlowNodes(initial.nodes, skills, uiLocale, t))
    setEdges(toFlowEdges(initial.edges))
  }, [initial, skills, setEdges, setNodes, t, uiLocale])

  useEffect(() => {
    const onFullscreenChange = () => setFullScreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((eds) =>
        addEdge({ ...params, id: `e_${params.source}_${params.target}_${Date.now()}` }, eds),
      ),
    [setEdges],
  )

  const addControlNode = (nodeType: GraphNodeType, position?: { x: number; y: number }) => {
    const id = `${nodeType}_${Date.now()}`
    const defaultName: Record<GraphNodeType, string> = {
      start: t('workflows.graphNodeStart'),
      skill: t('workflows.graphNodeSkill'),
      condition: t('workflows.graphNodeCondition'),
      approval: t('workflows.graphNodeApproval'),
      merge: t('workflows.graphNodeMerge'),
      end: t('workflows.graphNodeEnd'),
    }
    const config: Record<string, unknown> =
      nodeType === 'start'
        ? {
            input_fields: [
              { key: 'keyword', label: t('workflows.inputKeyword'), placeholder: t('workflows.inputKeywordPh'), required: true },
              { key: 'industry', label: t('workflows.inputIndustry'), placeholder: t('workflows.inputIndustryPh'), required: false },
            ],
          }
        : nodeType === 'merge'
          ? { merge_mode: 'sections' }
          : {}
    const pos = position || { x: 120 + nodes.length * 36, y: 80 + nodes.length * 24 }
    const next: Node = {
      id,
      type: 'workflowNode',
      position: pos,
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
    const skill =
      skills.find((s) => s.name === preset.skillName) ||
      skills.find((s) => s.name === 'patent-search' && preset.skillName === 'patent-search')
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
    const next = buildSkillNode(skill, position)
    setNodes((prev) => [...prev, next])
    setSelectedNodeId(next.id)
    setSelectedEdgeId(null)
    setPropsOpen(true)
  }

  const addEmptySkillNodeAt = (position: { x: number; y: number }) => {
    const next = buildSkillNode(null, position, t('workflows.emptySkillNode'))
    setNodes((prev) => [...prev, next])
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
    setNodes((prev) => prev.filter((n) => n.id !== nodeId))
    setEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId))
    if (selectedNodeId === nodeId) setSelectedNodeId(null)
  }

  const deleteEdgeById = (edgeId: string) => {
    setEdges((prev) => prev.filter((e) => e.id !== edgeId))
    if (selectedEdgeId === edgeId) setSelectedEdgeId(null)
  }

  const duplicateNodeById = (nodeId: string) => {
    const source = nodes.find((n) => n.id === nodeId)
    if (!source) return
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

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setContextMenu(null)
      const raw = event.dataTransfer.getData(DRAG_MIME)
      if (!raw || !reactFlowWrapper.current) return
      let payload: { kind: string; skillId?: string }
      try {
        payload = JSON.parse(raw)
      } catch {
        return
      }
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      if (payload.kind === 'skill' && payload.skillId) {
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
          const cfg = nextData.config || {}
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

  const saveGraph = () => {
    onSave({
      version: 1,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: ((n.data as any)?.nodeType || 'skill') as GraphNodeType,
        name: String((n.data as any)?.label || ''),
        position: n.position,
        config: ((n.data as any)?.config || {}) as Record<string, unknown>,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle || undefined,
        target_handle: e.targetHandle || undefined,
        condition: (typeof e.label === 'string' && e.label) || undefined,
      })),
    })
  }

  const nodeTypeLabel = (type: GraphNodeType) => {
    const map: Record<GraphNodeType, string> = {
      start: t('workflows.graphNodeStart'),
      skill: t('workflows.graphNodeSkill'),
      condition: t('workflows.graphNodeCondition'),
      approval: t('workflows.graphNodeApproval'),
      merge: t('workflows.graphNodeMerge'),
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

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-col bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-2 py-1.5 dark:border-gray-800">
        <p className="truncate text-xs font-medium text-gray-600 dark:text-gray-300">{t('workflows.graphEditorTitle')}</p>
        <div className="flex items-center gap-1">
          <div className="mr-1 flex items-center gap-0.5 rounded-md border border-gray-200 p-0.5 dark:border-gray-700">
            <IconToolButton
              title={t('workflows.canvasToolPointer')}
              active={isPointerTool}
              onClick={() => setCanvasTool('pointer')}
            >
              <MousePointer2 className="h-4 w-4" />
            </IconToolButton>
            <IconToolButton
              title={t('workflows.canvasToolPan')}
              active={!isPointerTool}
              onClick={() => setCanvasTool('pan')}
            >
              <Hand className="h-4 w-4" />
            </IconToolButton>
          </div>
          <IconToolButton title={fullScreen ? t('workflows.graphExitFullscreen') : t('workflows.graphFullscreen')} onClick={toggleFullscreen}>
            {fullScreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </IconToolButton>
          <IconToolButton title={t('workflows.graphDeleteSelected')} onClick={removeSelected} disabled={!selectedNodeId && !selectedEdgeId} className="text-red-600 dark:text-red-400">
            <Trash2 className="h-4 w-4" />
          </IconToolButton>
          <IconToolButton title={t('workflows.graphSave')} onClick={saveGraph}>
            <Save className="h-4 w-4" />
          </IconToolButton>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!paletteOpen ? (
          <PanelEdgeToggle side="left" title={t('workflows.graphShowLeft')} onClick={() => setPaletteOpen(true)} />
        ) : null}

        {paletteOpen ? (
          <aside className="flex w-56 shrink-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-2 py-1.5 dark:border-gray-800">
              <span className="text-xs font-medium">{t('workflows.graphNodeLibrary')}</span>
              <button type="button" title={t('workflows.graphHideLeft')} aria-label={t('workflows.graphHideLeft')} onClick={() => setPaletteOpen(false)} className="rounded p-0.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2 space-y-3">
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">{t('workflows.paletteControl')}</p>
                <div className="flex flex-col gap-1">
                  {CONTROL_NODE_TYPES.map((nodeType) => (
                    <button
                      key={nodeType}
                      type="button"
                      title={nodeTypeLabel(nodeType)}
                      onClick={() => addControlNode(nodeType)}
                      className="rounded-md border border-gray-200 px-2 py-1.5 text-left text-xs hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                      style={{ borderLeftWidth: 3, borderLeftColor: NODE_COLORS[nodeType] }}
                    >
                      {nodeTypeLabel(nodeType)}
                    </button>
                  ))}
                </div>
              </div>

              {showcaseConfig?.enabled !== false ? (
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                  {t('workflows.palettePatentPresets')}
                </p>
                <p className="mb-2 text-[10px] leading-relaxed text-gray-500 dark:text-gray-400">
                  {t('workflows.palettePatentPresetsHint')}
                </p>
                {showcaseConfig && !showcaseConfig.ready ? (
                  <p className="mb-2 text-[10px] leading-relaxed text-amber-600 dark:text-amber-400">
                    {t('workflows.patentShowcaseNotReady')}
                  </p>
                ) : null}
                <div className="flex flex-col gap-1">
                  {patentPresets.map((preset) => {
                    const missing = !skills.some((s) => s.name === preset.skillName)
                    return (
                      <div
                        key={preset.id}
                        draggable
                        onDragStart={(e) => beginPresetDrag(e, preset.id)}
                        title={t('workflows.dragPresetHint')}
                        className="flex cursor-grab items-start gap-1.5 rounded-md border border-gray-200 px-2 py-1.5 active:cursor-grabbing hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                        style={{
                          borderLeftWidth: 3,
                          borderLeftColor: NODE_COLORS.skill,
                        }}
                      >
                        <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-40" />
                        <div className="min-w-0 flex-1">
                          <span className="block truncate text-xs font-medium">
                            {getPatentPresetTitle(preset, uiLocale)}
                          </span>
                          <span className="block truncate text-[10px] text-gray-400">
                            {getPatentPresetDescription(preset, uiLocale)}
                          </span>
                          {missing ? (
                            <span className="text-[10px] text-amber-600 dark:text-amber-400">⚠</span>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              ) : null}

              <div>
                <div className="mb-1 flex items-center justify-between gap-1">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                    {t('workflows.paletteSkills')}
                  </p>
                  <Link to="/admin/skills" className="text-[10px] text-primary-600 hover:underline dark:text-primary-400">
                    {t('workflows.manageSkills')}
                  </Link>
                </div>
                <p className="mb-2 text-[10px] leading-relaxed text-gray-500 dark:text-gray-400">
                  {t('workflows.paletteSkillsHint')}
                </p>
                <input
                  type="search"
                  value={skillSearch}
                  onChange={(e) => setSkillSearch(e.target.value)}
                  placeholder={t('workflows.paletteSkillSearch')}
                  className="mb-2 w-full rounded border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-700 dark:bg-gray-800"
                />
                <div
                  draggable
                  onDragStart={beginEmptySkillDrag}
                  className="mb-2 flex cursor-grab items-center gap-1.5 rounded-md border border-dashed border-gray-300 px-2 py-1.5 text-xs text-gray-600 active:cursor-grabbing dark:border-gray-600 dark:text-gray-300"
                >
                  <GripVertical className="h-3.5 w-3.5 shrink-0 opacity-50" />
                  {t('workflows.dragEmptySkill')}
                </div>
                {skills.length === 0 ? (
                  <p className="text-xs text-amber-600 dark:text-amber-400">{t('workflows.paletteNoSkills')}</p>
                ) : filteredSkills.length === 0 ? (
                  <p className="text-xs text-gray-500">{t('common.noData')}</p>
                ) : (
                  <div className="flex flex-col gap-1">
                    {filteredSkills.map((skill) => {
                      const cat = inferSkillCategory(skill)
                      return (
                        <div
                          key={skill.id}
                          draggable
                          onDragStart={(e) => beginSkillDrag(e, skill)}
                          title={t('workflows.dragSkillHint')}
                          className="flex cursor-grab items-start gap-1.5 rounded-md border border-gray-200 px-2 py-1.5 active:cursor-grabbing hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                          style={{ borderLeftWidth: 3, borderLeftColor: NODE_COLORS.skill }}
                        >
                          <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-40" />
                          <div className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-medium">{getSkillDisplayName(skill, uiLocale)}</span>
                            <span className="block truncate text-[10px] text-gray-400">{skill.name}</span>
                            <span className="text-[10px] text-gray-500">{t(`workflows.skillCategory.${cat}`)}</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </aside>
        ) : null}

        <div
          ref={reactFlowWrapper}
          className={cn(
            'min-h-0 min-w-0 flex-1 bg-white dark:bg-gray-900',
            !isPointerTool && '[&_.react-flow__pane]:cursor-grab [&_.react-flow__pane:active]:cursor-grabbing',
          )}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          <ReactFlow
            className="h-full w-full"
            nodeTypes={workflowNodeTypes}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            panOnDrag={isPointerTool ? [1, 2] : true}
            panOnScroll
            selectionOnDrag={isPointerTool}
            nodesDraggable={isPointerTool}
            nodesConnectable={isPointerTool}
            elementsSelectable={isPointerTool}
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
            onPaneClick={() => setContextMenu(null)}
            fitView
            colorMode={dark ? 'dark' : 'light'}
          >
            <Background />
            <Controls />
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
                          <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.startNodeHint')}</p>
                        ) : null}
                        {selectedNodeType === 'merge' ? (
                          <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.mergeNodeHint')}</p>
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
                              value={String(selectedNodeConfig.skill_id || '')}
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
                              <Input label={t('workflows.graphRetryCount')} type="number" value={String(selectedNodeConfig.retry_count ?? 0)} onChange={(e) => updateNodeConfig('retry_count', toSafeInt(e.target.value, 0))} />
                              <Input label={t('workflows.graphTimeoutSec')} type="number" value={String(selectedNodeConfig.timeout_seconds ?? 0)} onChange={(e) => updateNodeConfig('timeout_seconds', toSafeInt(e.target.value, 0))} />
                            </div>
                            <PayloadMapper
                              fields={startInputFields}
                              upstreamNodeIds={upstreamForSelected}
                              payload={(selectedNodeConfig.payload_template || {}) as Record<string, unknown>}
                              onChange={(next) => updateNodeConfig('payload_template', next)}
                            />
                          </>
                        ) : null}
                        {selectedNodeType === 'condition' ? (
                          <div className="space-y-2">
                            <Input label={t('workflows.graphConditionLeft')} value={String(selectedNodeConfig.left || '')} onChange={(e) => updateNodeConfig('left', e.target.value)} />
                            <select className="block w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800" value={String(selectedNodeConfig.op || '==')} onChange={(e) => updateNodeConfig('op', e.target.value)}>
                              <option value="==">==</option>
                              <option value="!=">!=</option>
                            </select>
                            <Input label={t('workflows.graphConditionRight')} value={String(selectedNodeConfig.right ?? '')} onChange={(e) => updateNodeConfig('right', e.target.value)} />
                          </div>
                        ) : null}
                        {selectedNodeType === 'approval' ? (
                          <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.graphApprovalHint')}</p>
                        ) : null}
                      </div>
                    ) : null}
                    {selectedEdge ? (
                      <div className="space-y-2">
                        <select
                          className="block w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800"
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
                    <textarea className="mt-2 h-72 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs dark:border-gray-600 dark:bg-gray-800" value={jsonDraft} onChange={(e) => setJsonDraft(e.target.value)} />
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
    </div>
  )
}
