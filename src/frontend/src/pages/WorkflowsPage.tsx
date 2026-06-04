import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, LayoutTemplate, Network, Pencil, Play, Plus, RefreshCw, Trash2, Workflow } from 'lucide-react'

import api from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { WorkflowGraphEditor, type WorkflowGraphValue } from '@/components/workflow/WorkflowGraphEditor'
import { WorkflowReportPanel } from '@/components/workflow/WorkflowReportPanel'
import { extractStartInputFields, graphNeedsReportTitle, buildDefaultReportTitle } from '@/lib/workflowSkillMeta'
import { resolveRunDisplayName, runListSubtitle } from '@/lib/workflowRunLabel'

interface Skill {
  id: string
  name: string
  description?: string | null
  config?: Record<string, unknown> | null
}

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  category: string
  locale?: string | null
  node_count: number
  builtin?: boolean
}

interface WorkflowItem {
  id: string
  name: string
  description?: string | null
  enabled: boolean
  created_at: string
  updated_at: string
  graph_json?: WorkflowGraphValue | null
}

interface WorkflowRun {
  id: string
  workflow_id: string
  workflow_name: string
  display_name?: string
  trigger_type: string
  status: string
  input_payload?: Record<string, unknown> | null
  output_payload?: Record<string, unknown> | null
  error?: string | null
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
}

interface WorkflowStepRun {
  id: string
  step_id: string
  step_key: string
  step_name: string
  skill_id: string
  skill_name: string
  status: string
  payload?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  error?: string | null
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
}

interface WorkflowRunDetail extends WorkflowRun {
  step_runs: WorkflowStepRun[]
  node_runs?: Array<{
    node_id: string
    node_type: string
    node_name?: string
    status: string
    payload?: Record<string, unknown> | null
    result?: Record<string, unknown> | null
    error?: string | null
    started_at: string
    finished_at?: string | null
    duration_ms?: number | null
  }>
  pending_approvals?: Array<{
    id: string
    node_id: string
    node_name?: string | null
    status: string
    created_at: string
    comment?: string | null
  }>
  can_resume?: boolean
}

interface WorkflowApprovalTask {
  id: string
  workflow_run_id: string
  workflow_id: string
  workflow_name: string
  node_id: string
  node_name?: string | null
  status: string
  created_at: string
}

export function WorkflowsPage() {
  const { t, i18n } = useTranslation()
  const uiLocale = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [loading, setLoading] = useState(true)
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([])
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [runningMap, setRunningMap] = useState<Record<string, boolean>>({})
  const [pendingApprovals, setPendingApprovals] = useState<WorkflowApprovalTask[]>([])

  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [runDetailOpen, setRunDetailOpen] = useState(false)
  const [graphOpen, setGraphOpen] = useState(false)
  const [runInputOpen, setRunInputOpen] = useState(false)
  const [runInputValues, setRunInputValues] = useState<Record<string, string>>({})
  const reportTitleTouchedRef = useRef(false)
  const [runTarget, setRunTarget] = useState<WorkflowItem | null>(null)
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [creatingTemplateId, setCreatingTemplateId] = useState<string | null>(null)
  const [createFromTplOpen, setCreateFromTplOpen] = useState(false)
  const [createFromTplTarget, setCreateFromTplTarget] = useState<WorkflowTemplate | null>(null)
  const [createFromTplName, setCreateFromTplName] = useState('')
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false)
  const [saveTemplateTarget, setSaveTemplateTarget] = useState<WorkflowItem | null>(null)
  const [templateNameInput, setTemplateNameInput] = useState('')
  const [templateDescInput, setTemplateDescInput] = useState('')
  const [deletingTemplateId, setDeletingTemplateId] = useState<string | null>(null)

  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowItem | null>(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState<WorkflowRunDetail | null>(null)
  const [graphDraft, setGraphDraft] = useState<WorkflowGraphValue | null>(null)

  const [nameInput, setNameInput] = useState('')
  const [descriptionInput, setDescriptionInput] = useState('')
  const [enabledInput, setEnabledInput] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadAll()
  }, [uiLocale])

  const hasRunningJobs = runs.some((r) => r.status === 'running')

  useEffect(() => {
    if (!hasRunningJobs && !(selectedRunDetail?.status === 'running' && runDetailOpen)) {
      return
    }
    const timer = window.setInterval(async () => {
      try {
        const runData = await api.get<WorkflowRun[]>('/workflows/runs/list', { limit: '40' })
        setRuns(runData)
        if (runDetailOpen && selectedRunDetail?.id) {
          const detail = await api.get<WorkflowRunDetail>(
            `/workflows/runs/${selectedRunDetail.id}`
          )
          setSelectedRunDetail(detail)
        }
      } catch {
        /* ignore poll errors */
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [hasRunningJobs, runDetailOpen, selectedRunDetail?.id, selectedRunDetail?.status])

  const refreshRuns = async () => {
    try {
      const runData = await api.get<WorkflowRun[]>('/workflows/runs/list', { limit: '40' })
      setRuns(runData)
    } catch {
      /* ignore */
    }
  }

  const loadAll = async () => {
    setLoading(true)
    try {
      const [workflowData, runData, skillData, templateData] = await Promise.all([
        api.get<WorkflowItem[]>('/workflows'),
        api.get<WorkflowRun[]>('/workflows/runs/list', { limit: '40' }),
        api.get<Skill[]>('/skills'),
        api.get<WorkflowTemplate[]>(`/workflows/templates?locale=${uiLocale}`),
      ])
      const approvals = await api.get<WorkflowApprovalTask[]>('/workflows/approvals/pending', {
        limit: '50',
      })
      setWorkflows(workflowData)
      setRuns(runData)
      setSkills(skillData)
      setTemplates(templateData)
      setPendingApprovals(approvals)
    } catch (err: any) {
      toast(t('workflows.toastLoadFailed'), { type: 'error', message: err.message })
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setNameInput('')
    setDescriptionInput('')
    setEnabledInput(true)
    setCreateOpen(true)
  }

  const openEdit = (row: WorkflowItem) => {
    setSelectedWorkflow(row)
    setNameInput(row.name)
    setDescriptionInput(row.description || '')
    setEnabledInput(row.enabled)
    setEditOpen(true)
  }

  const saveCreate = async () => {
    if (!nameInput.trim()) return
    setSaving(true)
    try {
      await api.post('/workflows', {
        name: nameInput.trim(),
        description: descriptionInput.trim() || null,
        enabled: enabledInput,
      })
      setCreateOpen(false)
      await loadAll()
      toast(t('workflows.toastCreated'), { type: 'success' })
    } catch (err: any) {
      toast(t('workflows.toastSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const saveEdit = async () => {
    if (!selectedWorkflow) return
    setSaving(true)
    try {
      await api.patch(`/workflows/${selectedWorkflow.id}`, {
        name: nameInput.trim(),
        description: descriptionInput.trim() || null,
        enabled: enabledInput,
      })
      setEditOpen(false)
      await loadAll()
      toast(t('workflows.toastUpdated'), { type: 'success' })
    } catch (err: any) {
      toast(t('workflows.toastSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const toggleWorkflow = async (row: WorkflowItem, enabled: boolean) => {
    try {
      await api.patch(`/workflows/${row.id}`, { enabled })
      setWorkflows((prev) => prev.map((x) => (x.id === row.id ? { ...x, enabled } : x)))
    } catch (err: any) {
      toast(t('workflows.toastSaveFailed'), { type: 'error', message: err.message })
    }
  }

  const deleteWorkflow = async (row: WorkflowItem) => {
    if (!window.confirm(t('workflows.deleteConfirm', { name: row.name }))) return
    try {
      await api.delete(`/workflows/${row.id}`)
      setWorkflows((prev) => prev.filter((x) => x.id !== row.id))
      toast(t('workflows.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('workflows.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  const rerunRun = async (run: WorkflowRun) => {
    if (run.status === 'running') {
      toast(t('workflows.toastRunAlreadyRunning'), { type: 'warning' })
      return
    }
    setRunningMap((prev) => ({ ...prev, [run.workflow_id]: true }))
    try {
      const payload = (run.input_payload as Record<string, unknown> | null) || {}
      const detail = await api.post<WorkflowRunDetail>(`/workflows/${run.workflow_id}/run-once`, {
        payload,
      })
      toast(t('workflows.toastRunQueued'), { type: 'success' })
      if (detail?.id) {
        setRuns((prev) => [detail as WorkflowRun, ...prev.filter((r) => r.id !== detail.id)])
        setSelectedRunDetail(detail)
        setRunDetailOpen(true)
      } else {
        await refreshRuns()
      }
    } catch (err: any) {
      toast(t('workflows.toastRunFailed'), { type: 'error', message: err.message })
    } finally {
      setRunningMap((prev) => ({ ...prev, [run.workflow_id]: false }))
    }
  }

  const [renameRunOpen, setRenameRunOpen] = useState(false)
  const [renameRunTarget, setRenameRunTarget] = useState<WorkflowRun | null>(null)
  const [renameRunLabel, setRenameRunLabel] = useState('')
  const [renamingRun, setRenamingRun] = useState(false)

  const openRenameRun = (run: WorkflowRun) => {
    setRenameRunTarget(run)
    setRenameRunLabel(resolveRunDisplayName(run))
    setRenameRunOpen(true)
  }

  const confirmRenameRun = async () => {
    if (!renameRunTarget || !renameRunLabel.trim()) return
    setRenamingRun(true)
    try {
      const updated = await api.patch<WorkflowRun>(`/workflows/runs/${renameRunTarget.id}`, {
        run_label: renameRunLabel.trim(),
      })
      setRuns((prev) =>
        prev.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)),
      )
      if (selectedRunDetail?.id === updated.id) {
        setSelectedRunDetail((prev) => (prev ? { ...prev, ...updated } : prev))
      }
      toast(t('workflows.toastRunRenamed'), { type: 'success' })
      setRenameRunOpen(false)
      setRenameRunTarget(null)
    } catch (err: any) {
      toast(t('workflows.toastRunRenameFailed'), { type: 'error', message: err.message })
    } finally {
      setRenamingRun(false)
    }
  }

  const deleteRun = async (run: WorkflowRun) => {
    if (run.status === 'running') {
      toast(t('workflows.toastRunAlreadyRunning'), { type: 'warning' })
      return
    }
    if (!window.confirm(t('workflows.deleteRunConfirm', { name: resolveRunDisplayName(run) }))) return
    try {
      await api.delete(`/workflows/runs/${run.id}`)
      setRuns((prev) => prev.filter((r) => r.id !== run.id))
      if (selectedRunDetail?.id === run.id) {
        setRunDetailOpen(false)
        setSelectedRunDetail(null)
      }
      toast(t('workflows.toastRunDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('workflows.toastRunDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  const runOnce = async (row: WorkflowItem, payload: Record<string, unknown> = {}) => {
    setRunningMap((prev) => ({ ...prev, [row.id]: true }))
    try {
      const detail = await api.post<WorkflowRunDetail>(`/workflows/${row.id}/run-once`, {
        payload,
      })
      toast(t('workflows.toastRunQueued'), { type: 'success' })
      if (detail?.id) {
        setRuns((prev) => [detail as WorkflowRun, ...prev.filter((r) => r.id !== detail.id)])
        setSelectedRunDetail(detail)
        setRunDetailOpen(true)
      } else {
        await refreshRuns()
      }
    } catch (err: any) {
      toast(t('workflows.toastRunFailed'), { type: 'error', message: err.message })
    } finally {
      setRunningMap((prev) => ({ ...prev, [row.id]: false }))
      setRunInputOpen(false)
      setRunTarget(null)
    }
  }

  const skillOpts = useMemo(() => skills.map((s) => ({ id: s.id, name: s.name })), [skills])

  const openRunDialog = (row: WorkflowItem) => {
    const nodes = row.graph_json?.nodes || []
    const fields = extractStartInputFields(nodes, { t, skills: skillOpts })
    const defaults: Record<string, string> = {}
    for (const f of fields) defaults[f.key] = ''
    reportTitleTouchedRef.current = false
    setRunTarget(row)
    setRunInputValues(defaults)
    setRunInputOpen(true)
  }

  const handleRunInputChange = (key: string, value: string) => {
    if (key === 'report_title') {
      reportTitleTouchedRef.current = true
    }
    setRunInputValues((prev) => {
      const next = { ...prev, [key]: value }
      const nodes = runTarget?.graph_json?.nodes || []
      if (
        key === 'keyword' &&
        runTarget &&
        graphNeedsReportTitle(nodes, skillOpts) &&
        !reportTitleTouchedRef.current
      ) {
        next.report_title = buildDefaultReportTitle(value, {
          industry: prev.industry,
          locale: uiLocale,
        })
      }
      if (
        key === 'industry' &&
        runTarget &&
        graphNeedsReportTitle(nodes, skillOpts) &&
        !reportTitleTouchedRef.current &&
        next.keyword?.trim()
      ) {
        next.report_title = buildDefaultReportTitle(next.keyword, {
          industry: value,
          locale: uiLocale,
        })
      }
      return next
    })
  }

  const confirmRun = async () => {
    if (!runTarget) return
    const nodes = runTarget.graph_json?.nodes || []
    const fields = extractStartInputFields(nodes, { t, skills: skillOpts })
    for (const f of fields) {
      if (f.required && !runInputValues[f.key]?.trim()) {
        toast(t('workflows.runInputRequired', { field: f.label }), { type: 'error' })
        return
      }
    }
    const payload: Record<string, string> = { ...runInputValues, _locale: uiLocale }
    if (graphNeedsReportTitle(nodes, skillOpts)) {
      const title =
        payload.report_title?.trim() ||
        buildDefaultReportTitle(payload.keyword || '', {
          industry: payload.industry,
          locale: uiLocale,
        })
      if (title) payload.report_title = title
    } else if (!payload.report_title?.trim()) {
      delete payload.report_title
    }
    await runOnce(runTarget, payload)
  }

  const suggestWorkflowName = (baseName: string) => {
    const base = baseName.trim()
    const taken = new Set(workflows.map((w) => w.name.trim()))
    if (!taken.has(base)) return base
    let n = 2
    while (taken.has(`${base} (${n})`)) n += 1
    return `${base} (${n})`
  }

  const openCreateFromTemplate = (tpl: WorkflowTemplate) => {
    setCreateFromTplTarget(tpl)
    setCreateFromTplName(suggestWorkflowName(tpl.name))
    setCreateFromTplOpen(true)
  }

  const confirmCreateFromTemplate = async () => {
    if (!createFromTplTarget || !createFromTplName.trim()) return
    setCreatingTemplateId(createFromTplTarget.id)
    try {
      await api.post(`/workflows/from-template/${createFromTplTarget.id}`, {
        name: createFromTplName.trim(),
      })
      toast(t('workflows.toastTemplateCreated'), { type: 'success' })
      setCreateFromTplOpen(false)
      setCreateFromTplTarget(null)
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastTemplateCreateFailed'), { type: 'error', message: err.message })
    } finally {
      setCreatingTemplateId(null)
    }
  }

  const createFromTemplate = async (templateId: string) => {
    const tpl = templates.find((t) => t.id === templateId)
    if (tpl) {
      openCreateFromTemplate(tpl)
      return
    }
    setCreatingTemplateId(templateId)
    try {
      await api.post(`/workflows/from-template/${templateId}`, {})
      toast(t('workflows.toastTemplateCreated'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastTemplateCreateFailed'), { type: 'error', message: err.message })
    } finally {
      setCreatingTemplateId(null)
    }
  }

  const openSaveTemplate = (row: WorkflowItem) => {
    if (!row.graph_json?.nodes?.length) {
      toast(t('workflows.saveTemplateNeedGraph'), { type: 'error' })
      return
    }
    setSaveTemplateTarget(row)
    setTemplateNameInput(`${row.name} ${t('workflows.templateNameSuffix')}`)
    setTemplateDescInput(row.description || '')
    setSaveTemplateOpen(true)
  }

  const confirmSaveTemplate = async () => {
    if (!saveTemplateTarget || !templateNameInput.trim()) return
    setSaving(true)
    try {
      await api.post(`/workflows/${saveTemplateTarget.id}/save-as-template`, {
        name: templateNameInput.trim(),
        description: templateDescInput.trim() || null,
        category: 'custom',
        locale: uiLocale,
      })
      toast(t('workflows.toastTemplateSaved'), { type: 'success' })
      setSaveTemplateOpen(false)
      setSaveTemplateTarget(null)
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastTemplateSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const deleteUserTemplate = async (tpl: WorkflowTemplate) => {
    if (!window.confirm(t('workflows.deleteTemplateConfirm', { name: tpl.name }))) return
    setDeletingTemplateId(tpl.id)
    try {
      await api.delete(`/workflows/templates/${tpl.id}`)
      toast(t('workflows.toastTemplateDeleted'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastTemplateDeleteFailed'), { type: 'error', message: err.message })
    } finally {
      setDeletingTemplateId(null)
    }
  }

  const renderTemplateCard = (tpl: WorkflowTemplate) => (
    <div key={tpl.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{tpl.name}</p>
            {tpl.builtin ? (
              <Badge variant="info" size="sm">{t('workflows.templateBuiltin')}</Badge>
            ) : (
              <Badge variant="default" size="sm">{t('workflows.templateCustom')}</Badge>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tpl.description}</p>
        </div>
        <Badge variant="info" size="sm">{tpl.node_count} nodes</Badge>
      </div>
      {tpl.builtin && tpl.category === 'patent' ? (
        <p className="text-[10px] text-amber-600 dark:text-amber-400">{t('workflows.templatePatentHint')}</p>
      ) : null}
      {tpl.builtin && tpl.category === 'notification' ? (
        <p className="text-[10px] text-blue-600 dark:text-blue-400">{t('workflows.templateNotifyHint')}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          isLoading={creatingTemplateId === tpl.id}
          onClick={() => openCreateFromTemplate(tpl)}
        >
          {t('workflows.useTemplate')}
        </Button>
        {!tpl.builtin ? (
          <Button
            size="sm"
            variant="danger"
            isLoading={deletingTemplateId === tpl.id}
            onClick={() => deleteUserTemplate(tpl)}
          >
            {t('common.delete')}
          </Button>
        ) : null}
      </div>
    </div>
  )

  const builtinTemplates = templates.filter((t) => t.builtin !== false)
  const myTemplates = templates.filter((t) => t.builtin === false)

  const openGraphEditor = (row: WorkflowItem) => {
    setSelectedWorkflow(row)
    setGraphDraft(row.graph_json || { version: 1, nodes: [], edges: [] })
    setGraphOpen(true)
  }

  const saveGraph = async (graph: WorkflowGraphValue) => {
    if (!selectedWorkflow) return
    try {
      await api.patch(`/workflows/${selectedWorkflow.id}`, { graph_json: graph })
      toast(t('workflows.toastGraphSaved'), { type: 'success' })
      setGraphOpen(false)
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastGraphSaveFailed'), { type: 'error', message: err.message })
    }
  }

  const openRunDetail = async (run: WorkflowRun) => {
    try {
      const detail = await api.get<WorkflowRunDetail>(`/workflows/runs/${run.id}`)
      setSelectedRunDetail(detail)
      setRunDetailOpen(true)
    } catch (err: any) {
      toast(t('workflows.toastLoadRunDetailFailed'), { type: 'error', message: err.message })
    }
  }

  const approveTask = async (task: WorkflowApprovalTask) => {
    try {
      await api.post(`/workflows/approvals/${task.id}/approve`, {
        comment: null,
        auto_resume: true,
        decision_payload: {},
      })
      toast(t('workflows.toastApprovalApproved'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastApprovalActionFailed'), { type: 'error', message: err.message })
    }
  }

  const rejectTask = async (task: WorkflowApprovalTask) => {
    const comment = window.prompt(t('workflows.approvalRejectPrompt')) || ''
    try {
      await api.post(`/workflows/approvals/${task.id}/reject`, {
        comment,
        auto_resume: false,
        decision_payload: {},
      })
      toast(t('workflows.toastApprovalRejected'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastApprovalActionFailed'), { type: 'error', message: err.message })
    }
  }

  const resumeRun = async (runId: string) => {
    try {
      await api.post(`/workflows/runs/${runId}/resume`, { payload: {} })
      toast(t('workflows.toastRunResumed'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('workflows.toastResumeFailed'), { type: 'error', message: err.message })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="md" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            {t('workflows.pageTitle')}
            <Badge variant="warning">{t('common.beta')}</Badge>
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('workflows.pageSubtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" leftIcon={<RefreshCw className="w-4 h-4" />} onClick={loadAll}>
            {t('common.refresh')}
          </Button>
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
            {t('workflows.newWorkflow')}
          </Button>
        </div>
      </div>

      {builtinTemplates.some((tpl) => tpl.category === 'notification') ? (
        <Card>
          <CardHeader>{t('workflows.notifyTestCardTitle')}</CardHeader>
          <CardContent className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
            <ol className="list-decimal list-inside space-y-1">
              <li>{t('workflows.notifyTestStep1')}</li>
              <li>{t('workflows.notifyTestStep2')}</li>
              <li>{t('workflows.notifyTestStep3')}</li>
            </ol>
            <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">{t('workflows.notifyTestDoc')}</p>
          </CardContent>
        </Card>
      ) : null}

      {(builtinTemplates.length > 0 || myTemplates.length > 0) && (
        <div className="space-y-4">
          {builtinTemplates.length > 0 && (
            <Card>
              <CardHeader>{t('workflows.templatesTitle')}</CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                {builtinTemplates.map(renderTemplateCard)}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>{t('workflows.myTemplatesTitle')}</CardHeader>
            <CardContent>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{t('workflows.myTemplatesHint')}</p>
              {myTemplates.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">{t('workflows.myTemplatesEmpty')}</p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">{myTemplates.map(renderTemplateCard)}</div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>{t('workflows.listTitle')}</CardHeader>
        <CardContent className="p-0">
          {workflows.length === 0 ? (
            <div className="py-14 text-center text-gray-500 dark:text-gray-400">
              <Workflow className="w-10 h-10 mx-auto mb-2 opacity-60" />
              {t('workflows.empty')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {workflows.map((row) => (
                <div key={row.id} className="px-6 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{row.name}</p>
                      <button
                        type="button"
                        title={t('workflows.renameWorkflow')}
                        aria-label={t('workflows.renameWorkflow')}
                        onClick={() => openEdit(row)}
                        className="inline-flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <Badge variant={row.enabled ? 'success' : 'default'}>
                        {row.enabled ? t('common.enabled') : t('common.disabled')}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {row.description || t('workflows.noDescription')}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {t('workflows.updatedAt')}: {formatDate(row.updated_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Switch checked={row.enabled} onChange={(v) => toggleWorkflow(row, v)} />
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<Play className="w-4 h-4" />}
                      isLoading={!!runningMap[row.id]}
                      onClick={() => openRunDialog(row)}
                    >
                      {t('workflows.runOnce')}
                    </Button>
                    <Button size="sm" variant="outline" leftIcon={<Network className="w-4 h-4" />} onClick={() => openGraphEditor(row)}>
                      {t('workflows.editGraph')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      leftIcon={<LayoutTemplate className="w-4 h-4" />}
                      onClick={() => openSaveTemplate(row)}
                    >
                      {t('workflows.saveAsTemplate')}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => openEdit(row)}>
                      {t('common.edit')}
                    </Button>
                    <button
                      type="button"
                      title={t('common.delete')}
                      aria-label={t('common.delete')}
                      onClick={() => deleteWorkflow(row)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>{t('workflows.approvalsTitle')}</CardHeader>
        <CardContent className="p-0">
          {pendingApprovals.length === 0 ? (
            <div className="py-8 text-center text-gray-500 dark:text-gray-400">
              {t('workflows.approvalsEmpty')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {pendingApprovals.map((task) => (
                <div key={task.id} className="px-6 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {task.workflow_name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {task.node_name || task.node_id} · {formatDate(task.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button size="sm" variant="secondary" onClick={() => approveTask(task)}>
                      {t('workflows.approve')}
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => rejectTask(task)}>
                      {t('workflows.reject')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>{t('workflows.runsTitle')}</CardHeader>
        <CardContent className="p-0">
          {runs.length === 0 ? (
            <div className="py-10 text-center text-gray-500 dark:text-gray-400">
              {t('workflows.noRuns')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {runs.map((run) => {
                const runTitle = resolveRunDisplayName(run)
                const runSubtitle = runListSubtitle(run)
                return (
                <div key={run.id} className="px-6 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {runTitle}
                      </p>
                      <button
                        type="button"
                        title={t('workflows.renameRunRecord')}
                        aria-label={t('workflows.renameRunRecord')}
                        disabled={run.status === 'running'}
                        onClick={() => openRenameRun(run)}
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {runSubtitle ? `${runSubtitle} · ` : ''}
                      {formatDate(run.started_at)} · {run.trigger_type}
                      {run.error ? ` · ${run.error}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge
                      variant={
                        run.status === 'success'
                          ? 'success'
                          : run.status === 'failed'
                            ? 'danger'
                            : run.status === 'paused'
                              ? 'warning'
                              : 'default'
                      }
                    >
                      {run.status}
                    </Badge>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {run.duration_ms != null ? `${run.duration_ms}ms` : '-'}
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      leftIcon={<Eye className="w-4 h-4" />}
                      onClick={() => openRunDetail(run)}
                    >
                      {t('workflows.viewDetail')}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<RefreshCw className="w-4 h-4" />}
                      isLoading={!!runningMap[run.workflow_id]}
                      disabled={run.status === 'running'}
                      onClick={() => rerunRun(run)}
                    >
                      {t('workflows.rerun')}
                    </Button>
                    <button
                      type="button"
                      title={t('workflows.deleteRun')}
                      aria-label={t('workflows.deleteRun')}
                      disabled={run.status === 'running'}
                      onClick={() => deleteRun(run)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950/40"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                    {run.status === 'paused' ? (
                      <Button size="sm" variant="secondary" onClick={() => resumeRun(run.id)}>
                        {t('workflows.resumeRun')}
                      </Button>
                    ) : null}
                  </div>
                </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title={t('workflows.createDialogTitle')} size="md">
        <div className="space-y-4">
          <Input label={t('workflows.formName')} value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          <Input label={t('workflows.formDescription')} value={descriptionInput} onChange={(e) => setDescriptionInput(e.target.value)} />
          <Switch checked={enabledInput} onChange={setEnabledInput} label={t('workflows.formEnabled')} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={saveCreate} isLoading={saving} disabled={!nameInput.trim()}>{t('common.create')}</Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={editOpen} onClose={() => setEditOpen(false)} title={t('workflows.editDialogTitle')} size="md">
        <div className="space-y-4">
          <Input label={t('workflows.formName')} value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          <Input label={t('workflows.formDescription')} value={descriptionInput} onChange={(e) => setDescriptionInput(e.target.value)} />
          <Switch checked={enabledInput} onChange={setEnabledInput} label={t('workflows.formEnabled')} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setEditOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={saveEdit} isLoading={saving} disabled={!nameInput.trim()}>{t('common.save')}</Button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={runDetailOpen}
        onClose={() => setRunDetailOpen(false)}
        title={
          selectedRunDetail
            ? resolveRunDisplayName(selectedRunDetail)
            : t('workflows.runDetailTitle')
        }
        size="xl"
      >
        {selectedRunDetail && (
          <div className="space-y-4">
            {selectedRunDetail.status === 'running' ? (
              <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/80 dark:bg-blue-950/40 px-3 py-2 text-sm text-blue-800 dark:text-blue-200 space-y-2">
                <div className="flex items-center gap-2">
                  <Spinner size="sm" />
                  {t('workflows.runInProgressHint')}
                </div>
                <p className="text-xs text-blue-700/90 dark:text-blue-300/90 pl-6">
                  {t('workflows.runInProgressCloseHint')}
                </p>
              </div>
            ) : null}
            {selectedRunDetail.status === 'failed' && selectedRunDetail.error ? (
              <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50/80 dark:bg-red-950/40 px-3 py-2 space-y-1">
                <p className="text-sm font-medium text-red-800 dark:text-red-200">
                  {t('workflows.detailError')}
                </p>
                <pre className="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap break-words">
                  {selectedRunDetail.error}
                </pre>
              </div>
            ) : null}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
              <p className="text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t('workflows.detailReportTitle')}:</span>{' '}
                {resolveRunDisplayName(selectedRunDetail)}
              </p>
              <p className="text-gray-600 dark:text-gray-300"><span className="font-medium">{t('workflows.detailWorkflow')}:</span> {selectedRunDetail.workflow_name}</p>
              <p className="text-gray-600 dark:text-gray-300"><span className="font-medium">{t('workflows.detailStatus')}:</span> {selectedRunDetail.status}</p>
              <p className="text-gray-600 dark:text-gray-300"><span className="font-medium">{t('workflows.detailTriggerType')}:</span> {selectedRunDetail.trigger_type}</p>
              <p className="text-gray-600 dark:text-gray-300"><span className="font-medium">{t('workflows.detailDuration')}:</span> {selectedRunDetail.duration_ms != null ? `${selectedRunDetail.duration_ms}ms` : '-'}</p>
            </div>
            {selectedRunDetail.pending_approvals && selectedRunDetail.pending_approvals.length > 0 ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800 p-3">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200 mb-2">
                  {t('workflows.pendingApprovalHint')}
                </p>
                <div className="space-y-1">
                  {selectedRunDetail.pending_approvals.map((a) => (
                    <p key={a.id} className="text-xs text-amber-800 dark:text-amber-200">
                      - {a.node_name || a.node_id} · {formatDate(a.created_at)}
                    </p>
                  ))}
                </div>
              </div>
            ) : null}
            {selectedRunDetail.can_resume ? (
              <div className="flex justify-end">
                <Button size="sm" variant="secondary" onClick={() => resumeRun(selectedRunDetail.id)}>
                  {t('workflows.resumeRun')}
                </Button>
              </div>
            ) : null}

            <WorkflowReportPanel
              nodeRuns={selectedRunDetail.node_runs}
              outputPayload={selectedRunDetail.output_payload ?? undefined}
            />

            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{t('workflows.detailStepRuns')}</p>
              <div className="space-y-2 max-h-80 overflow-auto pr-1">
                {selectedRunDetail.step_runs.map((step) => (
                  <div key={step.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {step.step_name} · {step.skill_name}
                      </p>
                      <Badge
                        variant={step.status === 'success' ? 'success' : step.status === 'failed' ? 'danger' : 'warning'}
                      >
                        {step.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {formatDate(step.started_at)} · {step.duration_ms != null ? `${step.duration_ms}ms` : '-'}
                    </p>
                    {step.error ? (
                      <pre className="text-xs rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-2 mt-2 text-red-800 dark:text-red-200 overflow-auto">
{step.error}
                      </pre>
                    ) : null}
                    <details className="mt-2">
                      <summary className="text-xs cursor-pointer text-gray-600 dark:text-gray-300">
                        {t('workflows.viewStepPayloadAndResult')}
                      </summary>
                      <pre className="text-xs rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-2 mt-2 text-gray-800 dark:text-gray-200 overflow-auto">
{JSON.stringify({ payload: step.payload || {}, result: step.result || {} }, null, 2)}
                      </pre>
                    </details>
                  </div>
                ))}
              </div>
            </div>
            {selectedRunDetail.node_runs && selectedRunDetail.node_runs.length > 0 ? (
              <div className="space-y-1">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                  {t('workflows.detailNodeRuns')}
                </p>
                <div className="space-y-2 max-h-80 overflow-auto pr-1">
                  {selectedRunDetail.node_runs.map((node) => (
                    <div key={`${node.node_id}-${node.started_at}`} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {node.node_name || node.node_id} · {node.node_type}
                        </p>
                        <Badge variant={node.status === 'success' ? 'success' : node.status === 'failed' ? 'danger' : 'warning'}>
                          {node.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {formatDate(node.started_at)} · {node.duration_ms != null ? `${node.duration_ms}ms` : '-'}
                      </p>
                      {node.error ? (
                        <pre className="text-xs rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-2 mt-2 text-red-800 dark:text-red-200 overflow-auto">
{node.error}
                        </pre>
                      ) : null}
                      <details className="mt-2">
                        <summary className="text-xs cursor-pointer text-gray-600 dark:text-gray-300">
                          {t('workflows.viewStepPayloadAndResult')}
                        </summary>
                        <pre className="text-xs rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-2 mt-2 text-gray-800 dark:text-gray-200 overflow-auto">
{JSON.stringify({ payload: node.payload || {}, result: node.result || {} }, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
              {selectedRunDetail.status !== 'running' ? (
                <>
                  <Button
                    variant="secondary"
                    leftIcon={<RefreshCw className="w-4 h-4" />}
                    isLoading={!!runningMap[selectedRunDetail.workflow_id]}
                    onClick={() => rerunRun(selectedRunDetail)}
                  >
                    {t('workflows.rerun')}
                  </Button>
                  <button
                    type="button"
                    title={t('workflows.deleteRun')}
                    aria-label={t('workflows.deleteRun')}
                    onClick={() => deleteRun(selectedRunDetail)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              ) : null}
              <Button variant="secondary" onClick={() => setRunDetailOpen(false)}>
                {selectedRunDetail.status === 'running'
                  ? t('workflows.runDetailClose')
                  : t('common.close')}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
      <Dialog open={renameRunOpen} onClose={() => setRenameRunOpen(false)} title={t('workflows.renameRunRecordTitle')} size="md">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('workflows.renameRunRecordHint')}</p>
          <Input
            label={t('workflows.renameRunRecordLabel')}
            value={renameRunLabel}
            onChange={(e) => setRenameRunLabel(e.target.value)}
          />
          {renameRunTarget ? (
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {t('workflows.detailWorkflow')}: {renameRunTarget.workflow_name}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setRenameRunOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={confirmRenameRun} isLoading={renamingRun} disabled={!renameRunLabel.trim()}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </Dialog>
      <Dialog open={createFromTplOpen} onClose={() => setCreateFromTplOpen(false)} title={t('workflows.createFromTemplateTitle')} size="md">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('workflows.createFromTemplateHint')}</p>
          <Input
            label={t('workflows.formName')}
            value={createFromTplName}
            onChange={(e) => setCreateFromTplName(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateFromTplOpen(false)}>{t('common.cancel')}</Button>
            <Button
              onClick={confirmCreateFromTemplate}
              isLoading={!!creatingTemplateId}
              disabled={!createFromTplName.trim()}
            >
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Dialog>
      <Dialog open={runInputOpen} onClose={() => setRunInputOpen(false)} title={t('workflows.runInputTitle')}>
        <div className="space-y-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('workflows.runInputHint')}</p>
          {runTarget &&
            extractStartInputFields(runTarget.graph_json?.nodes || [], {
              t,
              skills: skillOpts,
            }).map((field) => (
              <Input
                key={field.key}
                type={field.type === 'number' ? 'number' : 'text'}
                label={field.label}
                value={runInputValues[field.key] || ''}
                placeholder={field.placeholder}
                onChange={(e) => handleRunInputChange(field.key, e.target.value)}
              />
            ))}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setRunInputOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={confirmRun} isLoading={runTarget ? runningMap[runTarget.id] : false}>
              {t('workflows.runOnce')}
            </Button>
          </div>
        </div>
      </Dialog>
      <Dialog open={saveTemplateOpen} onClose={() => setSaveTemplateOpen(false)} title={t('workflows.saveTemplateTitle')} size="md">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('workflows.saveTemplateHint')}</p>
          <Input label={t('workflows.formName')} value={templateNameInput} onChange={(e) => setTemplateNameInput(e.target.value)} />
          <Input label={t('workflows.formDescription')} value={templateDescInput} onChange={(e) => setTemplateDescInput(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setSaveTemplateOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={confirmSaveTemplate} isLoading={saving} disabled={!templateNameInput.trim()}>{t('common.save')}</Button>
          </div>
        </div>
      </Dialog>
      <Dialog
        open={graphOpen}
        onClose={() => setGraphOpen(false)}
        title={t('workflows.graphDialogTitle')}
        size="full"
        className="h-[95vh]"
        bodyClassName="flex min-h-0 flex-1 flex-col overflow-hidden p-0"
      >
        {graphDraft && (
          <WorkflowGraphEditor value={graphDraft} skills={skills} onSave={saveGraph} />
        )}
      </Dialog>
    </div>
  )
}
