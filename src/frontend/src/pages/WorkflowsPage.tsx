import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Eye,
  LayoutTemplate,
  MoreVertical,
  Network,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Store,
  Trash2,
  Workflow,
} from 'lucide-react'

import api from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { WorkflowTemplateGallery } from '@/components/workflow/WorkflowTemplateGallery'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import { Dialog } from '@/components/ui/Dialog'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { Pagination } from '@/components/ui/Pagination'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { WorkflowGraphEditor, type WorkflowGraphValue } from '@/components/workflow/WorkflowGraphEditor'
import { WorkflowReportPanel } from '@/components/workflow/WorkflowReportPanel'
import { extractStartInputFields, graphNeedsReportTitle, buildDefaultReportTitle, canQuickRun } from '@/lib/workflowSkillMeta'
import { resolveRunDisplayName, runListSubtitle } from '@/lib/workflowRunLabel'
import { humanizeRunError } from '@/lib/humanizeRunError'
import { EntitlementConfirmDialog } from '@/components/workflow/EntitlementConfirmDialog'
import {
  WorkflowEntitlementBanner,
  useWorkflowEntitlements,
} from '@/components/core/WorkflowEntitlementBanner'
import { automationCheckoutPath, extractAutomationLimit, limitMessage, type AutomationLimitDetail } from '@/lib/automationLimit'

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
  const location = useLocation()
  const navigate = useNavigate()
  const isPortal = location.pathname.startsWith('/portal')
  const workflowCenterPath = isPortal ? '/portal/workflow-center' : '/admin/workflow-center'
  const entitlements = useWorkflowEntitlements()
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
  const [runInputOpen, setRunInputOpen] = useState(false)
  const [runInputValues, setRunInputValues] = useState<Record<string, string>>({})
  const reportTitleTouchedRef = useRef(false)
  const [runTarget, setRunTarget] = useState<WorkflowItem | null>(null)
  const [publishingAccounts, setPublishingAccounts] = useState<{id:string;name:string;channel_type:string}[]>([])
  const [moreMenuId, setMoreMenuId] = useState<string | null>(null)

  useEffect(() => {
    if (!runInputOpen) return
    ;(async () => {
      try {
        const data = await api.get<{id:string;name:string;channel_type:string}[]>('/portal/publishing-accounts')
        setPublishingAccounts(data || [])
      } catch {
        try {
          const data = await api.get<{id:string;name:string;channel_type:string}[]>('/channels')
          setPublishingAccounts((data || []).filter((c: any) =>
            ['feishu','dingtalk','wecom','wechat_mp','slack','discord','telegram_channel','twitter_x','facebook','linkedin','playwright_client'].includes(c.channel_type)
          ))
        } catch { /* ignore */ }
      }
    })()
  }, [runInputOpen])
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [creatingTemplateId, setCreatingTemplateId] = useState<string | null>(null)
  const [createFromTplOpen, setCreateFromTplOpen] = useState(false)
  const [createFromTplTarget, setCreateFromTplTarget] = useState<WorkflowTemplate | null>(null)
  const [createFromTplName, setCreateFromTplName] = useState('')
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false)
  const [saveTemplateTarget, setSaveTemplateTarget] = useState<WorkflowItem | null>(null)
  const [templateNameInput, setTemplateNameInput] = useState('')
  const [templateDescInput, setTemplateDescInput] = useState('')
  const [shareTemplateToCenter, setShareTemplateToCenter] = useState(false)
  const [deletingTemplateId, setDeletingTemplateId] = useState<string | null>(null)

  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowItem | null>(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState<WorkflowRunDetail | null>(null)

  const [nameInput, setNameInput] = useState('')
  const [descriptionInput, setDescriptionInput] = useState('')
  const [enabledInput, setEnabledInput] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showTemplateGallery, setShowTemplateGallery] = useState(false)
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set())
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [entitlementLimit, setEntitlementLimit] = useState<AutomationLimitDetail | null>(null)

  // ── Tabs + pagination + search state ──────────────────────────────
  const [activeTab, setActiveTab] = useState<'workflows' | 'runs'>('workflows')
  const PAGE_SIZE = 10
  // workflow list paging
  const [wfPage, setWfPage] = useState(1)
  const [wfSearch, setWfSearch] = useState('')
  const [wfSearchInput, setWfSearchInput] = useState('')
  const [wfTotal, setWfTotal] = useState(0)
  const [wfLoading, setWfLoading] = useState(false)
  // runs list paging
  const [runsPage, setRunsPage] = useState(1)
  const [runsSearch, setRunsSearch] = useState('')
  const [runsSearchInput, setRunsSearchInput] = useState('')
  const [runsStatus, setRunsStatus] = useState('')
  const [runsTotal, setRunsTotal] = useState(0)
  const [runsLoading, setRunsLoading] = useState(false)

  // Paginated list envelopes returned by the backend.
  type ListEnvelope<T> = { items: T[]; total: number; limit: number; offset: number }

  const loadWorkflows = useCallback(
    async (page: number, search: string) => {
      setWfLoading(true)
      try {
        const params: Record<string, string> = { limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) }
        if (search.trim()) params.search = search.trim()
        const data = await api.get<ListEnvelope<WorkflowItem>>('/workflows', params)
        setWorkflows(data.items || [])
        setWfTotal(data.total || 0)
      } catch (err: any) {
        toast(t('workflows.toastLoadFailed'), { type: 'error', message: err.message })
      } finally {
        setWfLoading(false)
      }
    },
    [t],
  )

  const loadRuns = useCallback(
    async (page: number, search: string, status: string) => {
      setRunsLoading(true)
      try {
        const params: Record<string, string> = { limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) }
        if (search.trim()) params.search = search.trim()
        if (status) params.status = status
        const data = await api.get<ListEnvelope<WorkflowRun>>('/workflows/runs/list', params)
        setRuns(data.items || [])
        setRunsTotal(data.total || 0)
      } catch (err: any) {
        toast(t('workflows.toastLoadFailed'), { type: 'error', message: err.message })
      } finally {
        setRunsLoading(false)
      }
    },
    [t],
  )

  // Initial load + when search/page/status change.
  useEffect(() => {
    loadWorkflows(wfPage, wfSearch)
  }, [wfPage, wfSearch, loadWorkflows])
  useEffect(() => {
    loadRuns(runsPage, runsSearch, runsStatus)
  }, [runsPage, runsSearch, runsStatus, loadRuns])

  // Debounced search: typing updates the *Input field immediately; the
  // committed search value (which triggers the fetch) updates 300ms after.
  useEffect(() => {
    const id = window.setTimeout(() => {
      setWfSearch(wfSearchInput)
      setWfPage(1)
    }, 300)
    return () => window.clearTimeout(id)
  }, [wfSearchInput])
  useEffect(() => {
    const id = window.setTimeout(() => {
      setRunsSearch(runsSearchInput)
      setRunsPage(1)
    }, 300)
    return () => window.clearTimeout(id)
  }, [runsSearchInput])

  // Load non-paginated aux data once.
  useEffect(() => {
    (async () => {
      setLoading(true)
      try {
        const [skillData, templateData] = await Promise.all([
          api.get<Skill[]>('/skills'),
          api.get<WorkflowTemplate[]>(`/workflows/templates?locale=${uiLocale}`),
        ])
        setSkills(skillData)
        setTemplates(templateData)
        const approvals = await api.get<WorkflowApprovalTask[]>('/workflows/approvals/pending', {
          limit: '50',
        })
        setPendingApprovals(approvals)
      } catch (err: any) {
        toast(t('workflows.toastLoadFailed'), { type: 'error', message: err.message })
      } finally {
        setLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uiLocale])

  const hasRunningJobs = runs.some((r) => r.status === 'running' || r.status === 'paused')

  useEffect(() => {
    if (!hasRunningJobs && pendingApprovals.length === 0 && !(selectedRunDetail?.status === 'running' && runDetailOpen)) {
      return
    }
    const timer = window.setInterval(async () => {
      // Re-fetch the CURRENT runs page (preserve offset) so polling doesn't
      // reset pagination when a run completes mid-page.
      try {
        const params: Record<string, string> = { limit: String(PAGE_SIZE), offset: String((runsPage - 1) * PAGE_SIZE) }
        if (runsSearch.trim()) params.search = runsSearch.trim()
        if (runsStatus) params.status = runsStatus
        const data = await api.get<ListEnvelope<WorkflowRun>>('/workflows/runs/list', params)
        setRuns(data.items || [])
        setRunsTotal(data.total || 0)
        try {
          const approvals = await api.get<WorkflowApprovalTask[]>('/workflows/approvals/pending', { limit: '50' })
          setPendingApprovals(approvals)
        } catch { /* ignore */ }
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
  }, [hasRunningJobs, pendingApprovals.length, runDetailOpen, selectedRunDetail?.id, selectedRunDetail?.status, runsPage, runsSearch, runsStatus])

  const refreshAll = async () => {
    await Promise.all([loadWorkflows(wfPage, wfSearch), loadRuns(runsPage, runsSearch, runsStatus)])
  }

  const showLimitToast = (err: unknown, fallbackKey: string) => {
    const limit = extractAutomationLimit(err)
    if (limit) {
      // 弹确认框：用户点「前往开通」才跳转（portal），避免无声跳走
      setEntitlementLimit(limit)
      return true
    }
    const msg = err instanceof Error ? err.message : String(err)
    toast(t(fallbackKey), { type: 'error', message: msg })
    return false
  }

  const openCreate = () => {
    // 权益未加载完时提示等待，避免填完表单才在提交时被拒。
    if (entitlements === null) {
      toast(t('workflows.entitlementsLoading', { defaultValue: '权益信息加载中，请稍后再试' }), { type: 'warning' })
      return
    }
    if (!entitlements.can_create_workflow) {
      toast(t('portal.automationFreeHint'), { type: 'warning' })
      if (isPortal && entitlements.upgrade_template_id) {
        navigate(
          automationCheckoutPath({
            upgrade_template_id: entitlements.upgrade_template_id,
            upgrade_channel_id: entitlements.upgrade_channel_id,
          }),
        )
      }
      return
    }
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
      await refreshAll()
      toast(t('workflows.toastCreated'), { type: 'success' })
    } catch (err: unknown) {
      showLimitToast(err, 'workflows.toastSaveFailed')
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
      await refreshAll()
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
      setRunsPage(1)
      setActiveTab('runs')
      if (detail?.id) {
        setRuns((prev) => [detail as WorkflowRun, ...prev.filter((r) => r.id !== detail.id)])
        setRunsTotal((prev) => prev + 1)
        setSelectedRunDetail(detail)
        setRunDetailOpen(true)
      } else {
        await loadRuns(1, runsSearch, runsStatus)
      }
    } catch (err: unknown) {
      showLimitToast(err, 'workflows.toastRunFailed')
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

  const batchDeleteRuns = async () => {
    if (selectedRunIds.size === 0) return
    if (!window.confirm(t('workflows.batchDeleteRunConfirm', { count: selectedRunIds.size }))) return
    setBatchDeleting(true)
    let deleted = 0
    for (const id of selectedRunIds) {
      try {
        await api.delete(`/workflows/runs/${id}`)
        deleted++
      } catch { /* skip */ }
    }
    setSelectedRunIds(new Set())
    setBatchDeleting(false)
    await loadRuns(runsPage, runsSearch, runsStatus)
    toast(t('workflows.toastBatchDeleted', { count: deleted }), { type: 'success' })
  }

  const toggleRunSelect = (runId: string) => {
    setSelectedRunIds((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else next.add(runId)
      return next
    })
  }

  const toggleSelectAllRuns = () => {
    const nonRunning = runs.filter((r) => r.status !== 'running')
    if (selectedRunIds.size === nonRunning.length) {
      setSelectedRunIds(new Set())
    } else {
      setSelectedRunIds(new Set(nonRunning.map((r) => r.id)))
    }
  }

  const runOnce = async (row: WorkflowItem, payload: Record<string, unknown> = {}) => {
    setRunningMap((prev) => ({ ...prev, [row.id]: true }))
    try {
      const detail = await api.post<WorkflowRunDetail>(`/workflows/${row.id}/run-once`, {
        payload,
      })
      toast(t('workflows.toastRunQueued'), { type: 'success' })
      // Jump to the run records tab + page 1 so the user sees the new run.
      setRunsPage(1)
      setActiveTab('runs')
      if (detail?.id) {
        setRuns((prev) => [detail as WorkflowRun, ...prev.filter((r) => r.id !== detail.id)])
        setRunsTotal((prev) => prev + 1)
        setSelectedRunDetail(detail)
        setRunDetailOpen(true)
      } else {
        await loadRuns(1, runsSearch, runsStatus)
      }
    } catch (err: unknown) {
      showLimitToast(err, 'workflows.toastRunFailed')
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
    for (const f of fields) defaults[f.key] = f.default || ''
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
      await refreshAll()
    } catch (err: unknown) {
      showLimitToast(err, 'workflows.toastTemplateCreateFailed')
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
      await refreshAll()
    } catch (err: unknown) {
      showLimitToast(err, 'workflows.toastTemplateCreateFailed')
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
    setShareTemplateToCenter(false)
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
        visibility: shareTemplateToCenter ? 'shared' : 'private',
      })
      toast(t('workflows.toastTemplateSaved'), { type: 'success' })
      setSaveTemplateOpen(false)
      setSaveTemplateTarget(null)
      await refreshAll()
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
      await refreshAll()
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
    navigate(`${isPortal ? '/portal' : '/admin'}/workflows/${row.id}/graph`)
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

  const [approvalCandidates, setApprovalCandidates] = useState<Record<string, any[]>>({})
  const [selectedCandidate, setSelectedCandidate] = useState<Record<string, number>>({})

  const loadApprovalCandidates = async (task: WorkflowApprovalTask) => {
    try {
      const run = await api.get<any>(`/workflows/runs/${task.workflow_run_id}`)
      const payload = run?.output_payload || {}
      // Check both outputs (completed) and engine_state.outputs (paused)
      const outputs = payload.outputs || payload.engine_state?.outputs || {}
      for (const [, val] of Object.entries(outputs)) {
        const v = val as any
        if (v?.candidates && Array.isArray(v.candidates) && v.candidates.length > 0) {
          setApprovalCandidates((prev) => ({ ...prev, [task.id]: v.candidates }))
          return
        }
      }
      // Fallback: check node_runs for multi-content-writer result
      const nodeRuns = payload.node_runs || []
      for (const nr of nodeRuns) {
        const r = nr?.result
        if (r?.candidates && Array.isArray(r.candidates) && r.candidates.length > 0) {
          setApprovalCandidates((prev) => ({ ...prev, [task.id]: r.candidates }))
          return
        }
      }
      toast(t('workflows.noCandidates', '未找到候选内容'), { type: 'warning' })
    } catch (e: any) {
      toast(t('workflows.loadCandidatesFailed', '加载候选失败'), { type: 'error', message: e?.message })
    }
  }

  const approveTask = async (task: WorkflowApprovalTask) => {
    const candidates = approvalCandidates[task.id]
    const selectedIdx = selectedCandidate[task.id]
    const decision: Record<string, any> = {}

    if (candidates && selectedIdx !== undefined && candidates[selectedIdx]) {
      const chosen = candidates[selectedIdx]
      decision.selected_index = selectedIdx
      decision.selected_title = chosen.title
      decision.selected_content = chosen.content
    }

    try {
      await api.post(`/workflows/approvals/${task.id}/approve`, {
        comment: null,
        auto_resume: true,
        decision_payload: decision,
      })
      toast(t('workflows.toastApprovalApproved'), { type: 'success' })
      setApprovalCandidates((prev) => { const n = { ...prev }; delete n[task.id]; return n })
      setSelectedCandidate((prev) => { const n = { ...prev }; delete n[task.id]; return n })
      await refreshAll()
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
      await refreshAll()
    } catch (err: any) {
      toast(t('workflows.toastApprovalActionFailed'), { type: 'error', message: err.message })
    }
  }

  const resumeRun = async (runId: string) => {
    try {
      await api.post(`/workflows/runs/${runId}/resume`, { payload: {} })
      toast(t('workflows.toastRunResumed'), { type: 'success' })
      await refreshAll()
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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('workflows.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('workflows.pageSubtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<LayoutTemplate className="w-4 h-4" />}
            onClick={() => setShowTemplateGallery(true)}
          >
            {t('workflows.sidebarTemplates', '模板')}
          </Button>
          <Button variant="ghost" size="sm" leftIcon={<RefreshCw className="w-4 h-4" />} onClick={refreshAll}>
            {t('common.refresh')}
          </Button>
          <Button
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={openCreate}
          >
            {t('workflows.newWorkflow')}
          </Button>
        </div>
      </div>

      {/* Entitlement banner hidden — only show when limits are hit */}

      {pendingApprovals.length > 0 && (
      <Card className="border-amber-200 dark:border-amber-800">
        <CardHeader className="flex items-center gap-2">
          <span className="text-amber-600 dark:text-amber-400">⚠</span>
          {t('workflows.approvalsTitle')}
          <Badge variant="warning">{pendingApprovals.length}</Badge>
        </CardHeader>
        <CardContent className="p-0">
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {pendingApprovals.map((task) => (
                <div key={task.id} className="px-6 py-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
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
                  {/* N-pick-1 candidates */}
                  {approvalCandidates[task.id] && approvalCandidates[task.id].length > 1 && (
                    <div className="space-y-2 pl-2 border-l-2 border-blue-200 dark:border-blue-800">
                      <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                        {t('workflows.pickOne', '请选择一篇发布（选中后点审批通过）')}：
                      </p>
                      {approvalCandidates[task.id].map((cand: any, idx: number) => {
                        const expandKey = `expand-${task.id}-${idx}`
                        const isExpanded = (selectedCandidate as any)[expandKey]
                        return (
                        <div
                          key={idx}
                          className={`p-2 rounded border ${selectedCandidate[task.id] === idx ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700'}`}
                        >
                          <label className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name={`cand-${task.id}`}
                              checked={selectedCandidate[task.id] === idx}
                              onChange={() => setSelectedCandidate((prev) => ({ ...prev, [task.id]: idx }))}
                              className="mt-1"
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate">{cand.title || `候选 ${idx + 1}`}</p>
                              {(() => {
                                const url = cand.content || ''
                                const isVideo = /\.(mp4|webm|mov|avi)($|\?)/i.test(url)
                                const isImage = /\.(jpg|jpeg|png|gif|webp|svg)($|\?)/i.test(url)
                                const absUrl = url.startsWith('http') ? url : `${window.location.origin}${url}`
                                if (isVideo) {
                                  return <video src={absUrl} controls className="mt-1 max-h-32 rounded" />
                                }
                                if (isImage) {
                                  return <img src={absUrl} alt={cand.title} className="mt-1 max-h-32 rounded" />
                                }
                                return <p className={`text-xs text-gray-500 whitespace-pre-wrap ${isExpanded ? '' : 'line-clamp-2'}`}>{cand.content}</p>
                              })()}
                            </div>
                          </label>
                          <button
                            type="button"
                            className="text-xs text-blue-500 hover:underline mt-1 ml-6"
                            onClick={() => setSelectedCandidate((prev: any) => ({ ...prev, [expandKey]: !prev[expandKey] }))}
                          >
                            {isExpanded ? t('workflows.collapse', '收起') : t('workflows.expandFull', '展开全文')}
                          </button>
                        </div>
                        )
                      })}
                    </div>
                  )}
                  {!approvalCandidates[task.id] && (
                    <Button size="sm" variant="ghost" onClick={() => loadApprovalCandidates(task)}>
                      {t('workflows.loadCandidates', '查看候选内容')}
                    </Button>
                  )}
                </div>
              ))}
            </div>
        </CardContent>
      </Card>
      )}

      {builtinTemplates.some((tpl) => tpl.category === 'notification') ? (
        <details className="group">
          <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 select-none py-1">
            {t('workflows.notifyTestCardTitle')} →
          </summary>
        <Card className="mt-1">
          <CardContent className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
            <ol className="list-decimal list-inside space-y-1">
              <li>{t('workflows.notifyTestStep1')}</li>
              <li>{t('workflows.notifyTestStep2')}</li>
              <li>{t('workflows.notifyTestStep3')}</li>
            </ol>
            <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">{t('workflows.notifyTestDoc')}</p>
          </CardContent>
        </Card>
        </details>
      ) : null}


      <Tabs
        tabs={[
          { id: 'workflows', label: t('workflows.listTitle'), badge: wfTotal },
          { id: 'runs', label: t('workflows.runsTitle'), badge: runsTotal },
        ]}
        activeTab={activeTab}
        onChange={(id) => setActiveTab(id as 'workflows' | 'runs')}
        className="mb-4"
      />

      <TabPanel id="workflows" activeTab={activeTab}>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <span>{t('workflows.listTitle')}</span>
            <div className="w-64">
              <Input
                value={wfSearchInput}
                onChange={(e) => setWfSearchInput(e.target.value)}
                placeholder={t('workflows.searchPlaceholder', { defaultValue: '搜索工作流…' })}
                leftIcon={<Search className="w-4 h-4" />}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {wfLoading ? (
            <div className="flex justify-center py-14"><Spinner size="lg" /></div>
          ) : workflows.length === 0 ? (
            <div className="py-14 text-center text-gray-500 dark:text-gray-400">
              <Workflow className="w-10 h-10 mx-auto mb-2 opacity-60" />
              {wfSearch ? t('workflows.noSearchResults', { defaultValue: '无匹配的工作流' }) : t('workflows.empty')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {workflows.map((row) => {
                const hasGraph = row.graph_json?.nodes?.length || 0
                return (
                <div key={row.id} className="px-6 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{row.name}</p>
                      {!hasGraph ? (
                        <Badge variant="default" className="text-[10px]">未编排</Badge>
                      ) : (
                        <Badge variant={row.enabled ? 'success' : 'default'} className="text-[10px]">
                          {hasGraph} 节点
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                      {row.description || t('workflows.noDescription')}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<Play className="w-3.5 h-3.5" />}
                      isLoading={!!runningMap[row.id]}
                      onClick={() => {
                        // If every required input has a default, run directly (one-click);
                        // otherwise open the input dialog.
                        if (canQuickRun(row.graph_json?.nodes || [], { t, skills: skillOpts })) {
                          const defaults: Record<string, string> = {}
                          for (const f of extractStartInputFields(row.graph_json?.nodes || [], { t, skills: skillOpts })) {
                            defaults[f.key] = f.default || ''
                          }
                          runOnce(row, { ...defaults, _locale: uiLocale })
                        } else {
                          openRunDialog(row)
                        }
                      }}
                      disabled={!hasGraph || (entitlements !== null && !entitlements.can_run_workflow)}
                    >
                      {t('workflows.runOnce')}
                    </Button>
                    <Button size="sm" variant="outline" leftIcon={<Network className="w-3.5 h-3.5" />} onClick={() => openGraphEditor(row)}>
                      {t('workflows.editGraph')}
                    </Button>
                    <Button size="sm" variant="danger" leftIcon={<Trash2 className="w-3.5 h-3.5" />} onClick={() => deleteWorkflow(row)}>
                      {t('common.delete')}
                    </Button>
                    <div className="relative">
                      <button
                        type="button"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                        title={t('common.more', '更多')}
                        onClick={() => setMoreMenuId(moreMenuId === row.id ? null : row.id)}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                      {moreMenuId === row.id ? (
                        <>
                          <div className="fixed inset-0 z-10" onClick={() => setMoreMenuId(null)} />
                          <div className="absolute right-0 top-9 z-20 min-w-[140px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg py-1">
                            <button type="button" onClick={() => { setMoreMenuId(null); openEdit(row) }} className="block w-full px-3 py-1.5 text-left text-xs text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
                              <Pencil className="inline w-3 h-3 mr-1.5" />{t('common.edit')}
                            </button>
                            <button type="button" onClick={() => { setMoreMenuId(null); openSaveTemplate(row) }} className="block w-full px-3 py-1.5 text-left text-xs text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
                              <LayoutTemplate className="inline w-3 h-3 mr-1.5" />{t('workflows.saveAsTemplate')}
                            </button>
                            <button type="button" onClick={() => { setMoreMenuId(null); deleteWorkflow(row) }} className="block w-full px-3 py-1.5 text-left text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40">
                              <Trash2 className="inline w-3 h-3 mr-1.5" />{t('common.delete')}
                            </button>
                          </div>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>
                )
              })}
            </div>
          )}
        </CardContent>
        <Pagination
          page={wfPage}
          total={wfTotal}
          pageSize={PAGE_SIZE}
          onPageChange={setWfPage}
        />
      </Card>
      </TabPanel>

      <TabPanel id="runs" activeTab={activeTab}>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <span>{t('workflows.runsTitle')}</span>
            {runs.length > 0 && (
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={selectedRunIds.size > 0 && selectedRunIds.size === runs.filter(r => r.status !== 'running').length}
                    onChange={toggleSelectAllRuns}
                    className="h-3.5 w-3.5"
                  />
                  {t('workflows.selectAll')}
                </label>
                {selectedRunIds.size > 0 && (
                  <Button size="sm" variant="danger" isLoading={batchDeleting} onClick={batchDeleteRuns}>
                    {t('workflows.batchDelete')} ({selectedRunIds.size})
                  </Button>
                )}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="flex items-center gap-2 px-6 py-3 border-b border-gray-100 dark:border-gray-700">
            <div className="flex-1 max-w-xs">
              <Input
                value={runsSearchInput}
                onChange={(e) => setRunsSearchInput(e.target.value)}
                placeholder={t('workflows.searchRunsPlaceholder', { defaultValue: '搜索运行记录…' })}
                leftIcon={<Search className="w-4 h-4" />}
              />
            </div>
            <select
              value={runsStatus}
              onChange={(e) => { setRunsStatus(e.target.value); setRunsPage(1) }}
              className="h-9 rounded-md border border-gray-200 bg-white px-2 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
            >
              <option value="">{t('workflows.statusAll', { defaultValue: '全部状态' })}</option>
              <option value="running">{t('workflows.statusRunning', { defaultValue: '运行中' })}</option>
              <option value="success">{t('workflows.statusCompleted', { defaultValue: '已完成' })}</option>
              <option value="failed">{t('workflows.statusFailed', { defaultValue: '失败' })}</option>
              <option value="paused">{t('workflows.statusPaused', { defaultValue: '已暂停' })}</option>
            </select>
          </div>
          {runsLoading ? (
            <div className="flex justify-center py-10"><Spinner size="lg" /></div>
          ) : runs.length === 0 ? (
            <div className="py-10 text-center text-gray-500 dark:text-gray-400">
              {runsSearch || runsStatus ? t('workflows.noSearchResults', { defaultValue: '无匹配的记录' }) : t('workflows.noRuns')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {runs.map((run) => {
                const runTitle = resolveRunDisplayName(run)
                const runSubtitle = runListSubtitle(run)
                return (
                <div key={run.id} className="px-6 py-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <input
                      type="checkbox"
                      checked={selectedRunIds.has(run.id)}
                      disabled={run.status === 'running'}
                      onChange={() => toggleRunSelect(run.id)}
                      className="h-3.5 w-3.5 shrink-0"
                    />
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
        <Pagination
          page={runsPage}
          total={runsTotal}
          pageSize={PAGE_SIZE}
          onPageChange={setRunsPage}
        />
      </Card>
      </TabPanel>

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
                <p className="text-xs text-blue-700/90 dark:text-blue-300/90 pl-6">
                  {t('workflows.runInProgressFirstRunHint', { defaultValue: '首次运行可能需要安装依赖（约 1 分钟），请耐心等待。' })}
                </p>
              </div>
            ) : null}
            {selectedRunDetail.status === 'failed' && selectedRunDetail.error ? (
              <RunErrorBlock error={selectedRunDetail.error} />
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

            {/* Content preview for text-based results (e.g. web-scraped content) */}
            {(() => {
              const textResults: Array<{ nodeName: string; content: string }> = []
              for (const nr of selectedRunDetail.node_runs || []) {
                const r = nr.result
                if (!r || typeof r !== 'object') continue
                const text = r.stdout || r.content
                if (typeof text === 'string' && text.trim().length > 10) {
                  textResults.push({ nodeName: nr.node_name || nr.node_id, content: text.trim() })
                }
              }
              if (textResults.length === 0) return null
              return (
                <div className="space-y-3">
                  {textResults.map((tr, i) => (
                    <div key={i} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                        {tr.nodeName} {t('workflows.contentPreview')}
                      </p>
                      <pre className="text-xs whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 p-3 max-h-96 overflow-auto text-gray-800 dark:text-gray-200">
                        {tr.content}
                      </pre>
                    </div>
                  ))}
                </div>
              )
            })()}

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
                        <RunErrorBlock error={node.error} compact />
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
          {        runTarget &&
            extractStartInputFields(runTarget.graph_json?.nodes || [], {
              t,
              skills: skillOpts,
            }).map((field) => {
              if (field.type === 'multiline') {
                return (
                  <div key={field.key} className="space-y-1">
                    <label className="text-sm text-gray-600 dark:text-gray-300">{field.label}</label>
                    <textarea
                      className="w-full min-h-[120px] rounded border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                      placeholder={field.placeholder}
                      value={runInputValues[field.key] || ''}
                      onChange={(e) => handleRunInputChange(field.key, e.target.value)}
                    />
                  </div>
                )
              }
              if (field.type === 'file') {
                return (
                  <div key={field.key} className="space-y-1">
                    <label className="text-sm text-gray-600 dark:text-gray-300">{field.label}</label>
                    <input
                      type="file"
                      className="block w-full text-sm text-gray-500 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 dark:file:bg-gray-700 dark:file:text-gray-200"
                      onChange={async (e) => {
                        const file = e.target.files?.[0]
                        if (!file) return
                        const text = await file.text()
                        handleRunInputChange(field.key, text)
                      }}
                    />
                    {runInputValues[field.key] ? (
                      <p className="text-xs text-green-600 dark:text-green-400">{t('workflows.fileLoaded', { size: runInputValues[field.key].length })}</p>
                    ) : null}
                  </div>
                )
              }
              if (field.type === 'select') {
                return (
                  <div key={field.key} className="space-y-1">
                    <label className="text-sm text-gray-600 dark:text-gray-300">{field.label}{field.required ? ' *' : ''}</label>
                    <select
                      className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                      value={runInputValues[field.key] || ''}
                      onChange={(e) => handleRunInputChange(field.key, e.target.value)}
                    >
                      <option value="">请选择</option>
                      {(field.options || []).map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                )
              }
              if (field.type === 'publishing_account') {
                return (
                  <div key={field.key} className="space-y-1">
                    <label className="text-sm text-gray-600 dark:text-gray-300">{field.label}{field.required ? ' *' : ''}</label>
                    <select
                      className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                      value={runInputValues[field.key] || ''}
                      onChange={(e) => handleRunInputChange(field.key, e.target.value)}
                    >
                      <option value="">{t('workflows.selectAccount', '请选择发布账号')}</option>
                      {publishingAccounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>{acc.name} ({acc.channel_type})</option>
                      ))}
                    </select>
                  </div>
                )
              }
              return (
                <Input
                  key={field.key}
                  type={field.type === 'number' ? 'number' : 'text'}
                  label={field.label}
                  value={runInputValues[field.key] || ''}
                  placeholder={field.placeholder}
                  onChange={(e) => handleRunInputChange(field.key, e.target.value)}
                />
              )
            })}
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
          <label className="flex items-start gap-3 text-sm text-gray-600 dark:text-gray-300 cursor-pointer">
            <Switch checked={shareTemplateToCenter} onChange={setShareTemplateToCenter} />
            <span>
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {t('workflowCenter.shareOnSave')}
              </span>
              <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {t('workflowCenter.shareOnSaveHint')}
              </span>
            </span>
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setSaveTemplateOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={confirmSaveTemplate} isLoading={saving} disabled={!templateNameInput.trim()}>{t('common.save')}</Button>
          </div>
        </div>
      </Dialog>

      {/* Template gallery modal */}
      <WorkflowTemplateGallery
        open={showTemplateGallery}
        onClose={() => setShowTemplateGallery(false)}
        onApplied={() => void refreshAll()}
      />
      <EntitlementConfirmDialog
        limit={entitlementLimit}
        onClose={() => setEntitlementLimit(null)}
        isPortal={isPortal}
      />
    </div>
  )
}

/** 友好的运行/节点错误展示：顶部一句话提示 + 可折叠的原始错误日志。 */
function RunErrorBlock({ error, compact }: { error: string; compact?: boolean }) {
  const { t } = useTranslation()
  const humanized = humanizeRunError(error)
  return (
    <div className={'rounded-lg border border-red-200 dark:border-red-800 bg-red-50/80 dark:bg-red-950/40 ' + (compact ? 'px-2 py-1.5 mt-2' : 'px-3 py-2 space-y-1')}>
      <p className={'font-medium text-red-800 dark:text-red-200 ' + (compact ? 'text-xs' : 'text-sm')}>
        {humanized.title}
      </p>
      {humanized.hint ? (
        <p className="text-xs text-red-700/90 dark:text-red-300/90">{humanized.hint}</p>
      ) : null}
      <details className="mt-1">
        <summary className="text-xs cursor-pointer text-red-600 dark:text-red-300/80 hover:underline">
          {t('workflows.viewRawError', { defaultValue: '查看详细错误日志' })}
        </summary>
        <pre className="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap break-words mt-1 max-h-64 overflow-auto">
{error}
        </pre>
      </details>
    </div>
  )
}
