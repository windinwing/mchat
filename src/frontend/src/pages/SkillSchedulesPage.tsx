import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Clock3, Eye, Play, Plus, RefreshCw, Trash2 } from 'lucide-react'

import api from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Switch } from '@/components/ui/Switch'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import {
  WorkflowEntitlementBanner,
  useWorkflowEntitlements,
} from '@/components/portal/WorkflowEntitlementBanner'
import { automationCheckoutPath, extractAutomationLimit } from '@/lib/automationLimit'
import {
  CRON_PRESETS,
  COMMON_TIMEZONES,
  timezoneLabel,
  describeCron,
  isValidCron,
  nextRunTimes,
  formatRunTime,
} from '@/lib/cronPresets'
import { extractStartInputFields, type InputFieldDef } from '@/lib/workflowSkillMeta'
import { WorkflowReportPanel } from '@/components/workflow/WorkflowReportPanel'

interface Skill {
  id: string
  name: string
  enabled: boolean
}

interface WorkflowItem {
  id: string
  name: string
  enabled: boolean
}

interface SkillSchedule {
  id: string
  target_type: 'skill' | 'workflow'
  target_name: string
  skill_id?: string | null
  skill_name?: string | null
  workflow_id?: string | null
  workflow_name?: string | null
  name: string
  cron_expr: string
  timezone: string
  payload?: Record<string, unknown> | null
  enabled: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  created_at: string
  updated_at: string
}

interface SkillScheduleRun {
  id: string
  schedule_id?: string | null
  target_type: 'skill' | 'workflow'
  target_name?: string | null
  skill_id?: string | null
  skill_name?: string | null
  workflow_id?: string | null
  workflow_name?: string | null
  trigger_type: string
  status: 'success' | 'failed' | 'running'
  payload?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  error?: string | null
  duration_ms?: number | null
  started_at: string
  finished_at?: string | null
}

const DEFAULT_CRON = '*/30 * * * *'

export function SkillSchedulesPage() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const isPortal = location.pathname.startsWith('/portal')
  const entitlements = useWorkflowEntitlements()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [runningMap, setRunningMap] = useState<Record<string, boolean>>({})
  const [schedules, setSchedules] = useState<SkillSchedule[]>([])
  const [runs, setRuns] = useState<SkillScheduleRun[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [runDetailOpen, setRunDetailOpen] = useState(false)
  const [selectedRun, setSelectedRun] = useState<SkillScheduleRun | null>(null)
  const [editing, setEditing] = useState<SkillSchedule | null>(null)
  const [search, setSearch] = useState('')

  const [formName, setFormName] = useState('')
  const [formTargetType, setFormTargetType] = useState<'skill' | 'workflow'>('skill')
  const [formSkillId, setFormSkillId] = useState('')
  const [formWorkflowId, setFormWorkflowId] = useState('')
  const [formCron, setFormCron] = useState(DEFAULT_CRON)
  const [formTimezone, setFormTimezone] = useState('UTC')
  const [formPayload, setFormPayload] = useState('{}')
  const [formEnabled, setFormEnabled] = useState(true)
  // Structured payload: for workflows, key→value map of the start-node input fields.
  const [workflowFields, setWorkflowFields] = useState<InputFieldDef[]>([])
  const [payloadValues, setPayloadValues] = useState<Record<string, string>>({})
  // Raw JSON (advanced fallback), synced from structured values.
  const [rawMode, setRawMode] = useState(false)

  useEffect(() => {
    loadAll()
  }, [])

  // When the selected workflow changes, fetch its graph to render structured input fields.
  useEffect(() => {
    if (formTargetType !== 'workflow' || !formWorkflowId) {
      setWorkflowFields([])
      setPayloadValues({})
      return
    }
    let cancelled = false
    api
      .get<{ graph_json?: { nodes?: Array<{ type: string; config?: Record<string, unknown> | null }> } | null }>(
        `/workflows/wf/${formWorkflowId}`,
      )
      .then((detail) => {
        if (cancelled) return
        const nodes = detail?.graph_json?.nodes || []
        const fields = extractStartInputFields(nodes)
        setWorkflowFields(fields)
        // Preserve existing values for keys that match, prefill defaults for new ones.
        setPayloadValues((prev) => {
          const next: Record<string, string> = {}
          for (const f of fields) next[f.key] = prev[f.key] ?? f.default ?? ''
          return next
        })
      })
      .catch(() => {
        if (cancelled) return
        setWorkflowFields([])
      })
    return () => {
      cancelled = true
    }
  }, [formTargetType, formWorkflowId])

  const filteredSchedules = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return schedules
    return schedules.filter(
      (item) =>
        item.name.toLowerCase().includes(needle) ||
        item.target_name.toLowerCase().includes(needle) ||
        item.cron_expr.toLowerCase().includes(needle),
    )
  }, [schedules, search])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [skillList, workflowEnvelope, scheduleList, runList] = await Promise.all([
        api.get<Skill[]>('/skills'),
        api.get<{ items?: WorkflowItem[] }>('/workflows'),
        api.get<SkillSchedule[]>('/skills/schedules'),
        api.get<SkillScheduleRun[]>('/skills/schedules/runs', { limit: '40' }),
      ])
      setSkills(skillList)
      setWorkflows(workflowEnvelope.items ?? [])
      setSchedules(scheduleList)
      setRuns(runList)
    } catch (err: any) {
      toast(t('schedules.toastLoadFailed'), { type: 'error', message: err.message })
    } finally {
      setLoading(false)
    }
  }

  const resetForm = () => {
    setEditing(null)
    setFormName('')
    setFormTargetType('skill')
    setFormSkillId(skills[0]?.id || '')
    setFormWorkflowId('')
    setFormCron(DEFAULT_CRON)
    setFormTimezone('Asia/Shanghai')
    setFormPayload('{}')
    setPayloadValues({})
    setWorkflowFields([])
    setRawMode(false)
    setFormEnabled(true)
  }

  const showLimitToast = (err: unknown, fallbackKey: string) => {
    const limit = extractAutomationLimit(err)
    if (limit) {
      toast(limit.message || t(fallbackKey), { type: 'error' })
      if (isPortal && limit.upgrade_template_id) {
        navigate(automationCheckoutPath(limit))
      }
      return true
    }
    const msg = err instanceof Error ? err.message : String(err)
    toast(t(fallbackKey), { type: 'error', message: msg })
    return false
  }

  const openCreateDialog = () => {
    if (entitlements && !entitlements.can_create_schedule) {
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
    resetForm()
    setDialogOpen(true)
  }

  const openEditDialog = (item: SkillSchedule) => {
    setEditing(item)
    setFormName(item.name)
    setFormTargetType(item.target_type)
    setFormSkillId(item.skill_id || '')
    setFormWorkflowId(item.workflow_id || '')
    setFormCron(item.cron_expr)
    setFormTimezone(item.timezone || 'Asia/Shanghai')
    const stored = item.payload || {}
    // Seed structured payload values from stored JSON (stringified scalars).
    const seed: Record<string, string> = {}
    for (const [k, v] of Object.entries(stored)) {
      if (typeof v === 'string' || typeof v === 'number') seed[k] = String(v)
    }
    setPayloadValues(seed)
    setWorkflowFields([])
    setRawMode(false)
    setFormPayload(JSON.stringify(stored, null, 2))
    setFormEnabled(item.enabled)
    setDialogOpen(true)
  }

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault()
    if (formTargetType === 'skill' && !formSkillId) {
      toast(t('schedules.toastSelectSkill'), { type: 'error' })
      return
    }
    if (formTargetType === 'workflow' && !formWorkflowId) {
      toast(t('schedules.toastSelectWorkflow'), { type: 'error' })
      return
    }

    // Client-side cron validation (mirrors backend APScheduler parsing).
    if (!isValidCron(formCron.trim())) {
      toast(t('schedules.toastCronInvalid'), { type: 'error' })
      return
    }

    let payload: Record<string, unknown> | null = null
    if (rawMode) {
      // Advanced: parse the raw JSON textarea.
      const payloadText = formPayload.trim()
      if (payloadText) {
        try {
          const parsed = JSON.parse(payloadText)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            payload = parsed
          } else {
            throw new Error('payload must be object')
          }
        } catch {
          toast(t('schedules.toastPayloadInvalid'), { type: 'error' })
          return
        }
      }
    } else {
      // Structured: build payload from the field values (omit empty).
      const obj: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(payloadValues)) {
        if (v && v.trim() !== '') obj[k] = v
      }
      payload = Object.keys(obj).length > 0 ? obj : null
    }

    setSaving(true)
    try {
      const requestBody = {
        name: formName.trim(),
        target_type: formTargetType,
        skill_id: formTargetType === 'skill' ? formSkillId : null,
        workflow_id: formTargetType === 'workflow' ? formWorkflowId : null,
        cron_expr: formCron.trim(),
        timezone: formTimezone.trim(),
        payload,
        enabled: formEnabled,
      }
      if (editing) {
        await api.patch(`/skills/schedules/${editing.id}`, requestBody)
        toast(t('schedules.toastUpdated'), { type: 'success' })
      } else {
        await api.post('/skills/schedules', requestBody)
        toast(t('schedules.toastCreated'), { type: 'success' })
      }
      setDialogOpen(false)
      await loadAll()
    } catch (err: unknown) {
      showLimitToast(err, 'schedules.toastSaveFailed')
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async (item: SkillSchedule, enabled: boolean) => {
    try {
      await api.patch(`/skills/schedules/${item.id}`, { enabled })
      setSchedules((prev) =>
        prev.map((row) => (row.id === item.id ? { ...row, enabled } : row)),
      )
      toast(enabled ? t('common.enabled') : t('common.disabled'), { type: 'success' })
    } catch (err: any) {
      toast(t('schedules.toastSaveFailed'), { type: 'error', message: err.message })
    }
  }

  const deleteSchedule = async (item: SkillSchedule) => {
    if (!window.confirm(t('schedules.deleteConfirm', { name: item.name }))) return
    try {
      await api.delete(`/skills/schedules/${item.id}`)
      setSchedules((prev) => prev.filter((row) => row.id !== item.id))
      toast(t('schedules.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('schedules.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  const runOnce = async (item: SkillSchedule) => {
    setRunningMap((prev) => ({ ...prev, [item.id]: true }))
    try {
      await api.post(`/skills/schedules/${item.id}/run-once`, {})
      toast(t('schedules.toastTriggered'), { type: 'success' })
      await loadAll()
    } catch (err: any) {
      toast(t('schedules.toastTriggerFailed'), { type: 'error', message: err.message })
    } finally {
      setRunningMap((prev) => ({ ...prev, [item.id]: false }))
    }
  }

  const openRunDetail = (run: SkillScheduleRun) => {
    setSelectedRun(run)
    setRunDetailOpen(true)
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
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('schedules.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('schedules.pageSubtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            leftIcon={<RefreshCw className="w-4 h-4" />}
            onClick={loadAll}
          >
            {t('common.refresh')}
          </Button>
          <Button
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={openCreateDialog}
            disabled={entitlements !== null && !entitlements.can_create_schedule}
          >
            {t('schedules.newSchedule')}
          </Button>
        </div>
      </div>

      <WorkflowEntitlementBanner />

      <Card>
        <CardContent className="py-4">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('schedules.searchPlaceholder')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>{t('schedules.listTitle')}</CardHeader>
        <CardContent className="p-0">
          {filteredSchedules.length === 0 ? (
            <div className="py-14 text-center text-gray-500 dark:text-gray-400">
              <Clock3 className="w-10 h-10 mx-auto mb-2 opacity-60" />
              {t('schedules.empty')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {filteredSchedules.map((item) => (
                <div
                  key={item.id}
                  className="px-6 py-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {item.name}
                      </p>
                      <Badge variant={item.enabled ? 'success' : 'default'}>
                        {item.enabled ? t('common.enabled') : t('common.disabled')}
                      </Badge>
                      <Badge variant="info">{item.target_name}</Badge>
                      <Badge variant="default">{item.target_type}</Badge>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {describeCron(item.cron_expr)} · <code className="text-[10px]">{item.cron_expr}</code> · {timezoneLabel(item.timezone)}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {t('schedules.nextRun')}: {item.next_run_at ? formatDate(item.next_run_at) : '-'} ·{' '}
                      {t('schedules.lastRun')}: {item.last_run_at ? formatDate(item.last_run_at) : '-'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Switch checked={item.enabled} onChange={(v) => toggleEnabled(item, v)} />
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<Play className="w-4 h-4" />}
                      isLoading={!!runningMap[item.id]}
                      onClick={() => runOnce(item)}
                    >
                      {t('schedules.runOnce')}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => openEditDialog(item)}>
                      {t('common.edit')}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      leftIcon={<Trash2 className="w-4 h-4" />}
                      onClick={() => deleteSchedule(item)}
                    >
                      {t('common.delete')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>{t('schedules.recentRunsTitle')}</CardHeader>
        <CardContent className="p-0">
          {runs.length === 0 ? (
            <div className="py-10 text-center text-gray-500 dark:text-gray-400">
              {t('schedules.noRuns')}
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {runs.map((run) => (
                <div
                  key={run.id}
                  className="px-6 py-3 flex items-center justify-between gap-3 text-sm"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 dark:text-gray-100 truncate">
                      {run.target_name || run.skill_name || run.workflow_name || '-'}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {formatDate(run.started_at)} · {run.trigger_type}
                      {run.error ? ` · ${run.error}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge
                      variant={
                        run.status === 'success' ? 'success' : run.status === 'failed' ? 'danger' : 'warning'
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
                      {t('schedules.viewDetail')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? t('schedules.editDialogTitle') : t('schedules.createDialogTitle')}
        size="md"
      >
        <form className="space-y-4" onSubmit={submitForm}>
          <Input
            label={t('schedules.formName')}
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder={t('schedules.formNamePlaceholder')}
            required
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('schedules.formTargetType')}
            </label>
            <select
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
              value={formTargetType}
              onChange={(e) => setFormTargetType(e.target.value as 'skill' | 'workflow')}
              required
            >
              <option value="skill">{t('schedules.targetSkill')}</option>
              <option value="workflow">{t('schedules.targetWorkflow')}</option>
            </select>
          </div>

          {formTargetType === 'skill' ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('schedules.formSkill')}
              </label>
              <select
                className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                value={formSkillId}
                onChange={(e) => setFormSkillId(e.target.value)}
                required
              >
                <option value="">{t('schedules.formSkillPlaceholder')}</option>
                {skills.map((skill) => (
                  <option key={skill.id} value={skill.id}>
                    {skill.name}
                    {!skill.enabled ? ' (disabled)' : ''}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('schedules.formWorkflow')}
              </label>
              <select
                className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                value={formWorkflowId}
                onChange={(e) => setFormWorkflowId(e.target.value)}
                required
              >
                <option value="">{t('schedules.formWorkflowPlaceholder')}</option>
                {workflows.map((workflow) => (
                  <option key={workflow.id} value={workflow.id}>
                    {workflow.name}
                    {!workflow.enabled ? ' (disabled)' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('schedules.formCron')}
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {CRON_PRESETS.map((preset) => {
                const active = formCron.trim() === preset.cron
                return (
                  <button
                    key={preset.cron}
                    type="button"
                    onClick={() => setFormCron(preset.cron)}
                    className={
                      'rounded-full px-2.5 py-1 text-xs border transition-colors ' +
                      (active
                        ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-950 dark:text-primary-300'
                        : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800')
                    }
                  >
                    {t(preset.labelKey)}
                  </button>
                )
              })}
            </div>
            <Input
              value={formCron}
              onChange={(e) => setFormCron(e.target.value)}
              placeholder="*/30 * * * *"
              required
            />
            {formCron.trim() && isValidCron(formCron.trim()) ? (
              <div className="mt-1.5 space-y-0.5">
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  {t('schedules.cronMeaning')}: <span className="font-medium text-primary-600 dark:text-primary-400">{describeCron(formCron.trim())}</span>
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-500">
                  {t('schedules.cronNextRuns')}: {nextRunTimes(formCron.trim(), 3, new Date(), formTimezone).map((iso) => formatRunTime(iso, formTimezone)).join('、')}
                </p>
              </div>
            ) : (
              <p className="mt-1.5 text-xs text-red-500">{t('schedules.cronInvalidHint')}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('schedules.formTimezone')}
            </label>
            <select
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
              value={COMMON_TIMEZONES.includes(formTimezone) ? formTimezone : '__other'}
              onChange={(e) => {
                const v = e.target.value
                if (v === '__other') {
                  setFormTimezone('UTC')
                } else {
                  setFormTimezone(v)
                }
              }}
            >
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {timezoneLabel(tz)}
                </option>
              ))}
              {!COMMON_TIMEZONES.includes(formTimezone) ? <option value="__other">{formTimezone}</option> : null}
            </select>
          </div>

          {/* Execution payload: structured fields for workflows, raw JSON otherwise. */}
          {formTargetType === 'workflow' && !rawMode ? (
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('schedules.formPayload')}
                </label>
                <button
                  type="button"
                  onClick={() => {
                    // Sync structured values into the raw JSON box before switching.
                    const obj: Record<string, unknown> = {}
                    for (const [k, v] of Object.entries(payloadValues)) {
                      if (v && v.trim() !== '') obj[k] = v
                    }
                    setFormPayload(JSON.stringify(obj, null, 2))
                    setRawMode(true)
                  }}
                  className="text-xs text-primary-600 hover:underline dark:text-primary-400"
                >
                  {t('schedules.payloadAdvanced')}
                </button>
              </div>
              {workflowFields.length > 0 ? (
                <div className="space-y-2">
                  {workflowFields.map((field) => (
                    <div key={field.key}>
                      <label className="block text-xs text-gray-600 dark:text-gray-300 mb-0.5">
                        {field.label}{field.required ? ' *' : ''}
                      </label>
                      {field.type === 'multiline' ? (
                        <textarea
                          className="w-full min-h-[80px] text-sm rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                          placeholder={field.placeholder}
                          value={payloadValues[field.key] ?? ''}
                          onChange={(e) =>
                            setPayloadValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                        />
                      ) : field.type === 'select' ? (
                        <select
                          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                          value={payloadValues[field.key] ?? ''}
                          onChange={(e) =>
                            setPayloadValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                        >
                          <option value="">{t('common.select', '请选择')}</option>
                          {(field.options || []).map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      ) : (
                        <Input
                          type={field.type === 'number' ? 'number' : 'text'}
                          placeholder={field.placeholder}
                          value={payloadValues[field.key] ?? ''}
                          onChange={(e) =>
                            setPayloadValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                        />
                      )}
                    </div>
                  ))}
                  <p className="text-xs text-gray-400 dark:text-gray-500">{t('schedules.payloadWorkflowHint')}</p>
                </div>
              ) : (
                <p className="text-xs text-gray-400 dark:text-gray-500">{t('schedules.payloadLoading')}</p>
              )}
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('schedules.formPayload')}
                </label>
                {formTargetType === 'workflow' && rawMode ? (
                  <button
                    type="button"
                    onClick={() => {
                      // Parse raw JSON back into structured values.
                      try {
                        const parsed = JSON.parse(formPayload || '{}')
                        const seed: Record<string, string> = {}
                        for (const [k, v] of Object.entries(parsed)) {
                          if (typeof v === 'string' || typeof v === 'number') seed[k] = String(v)
                        }
                        setPayloadValues((prev) => ({ ...seed, ...prev }))
                      } catch {
                        /* keep raw as-is */
                      }
                      setRawMode(false)
                    }}
                    className="text-xs text-primary-600 hover:underline dark:text-primary-400"
                  >
                    {t('schedules.payloadStructured')}
                  </button>
                ) : null}
              </div>
              <textarea
                className="w-full h-28 text-xs font-mono rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-3"
                value={formPayload}
                onChange={(e) => setFormPayload(e.target.value)}
                placeholder={formTargetType === 'skill' ? '{"query":"status"}' : '{"keyword":"无人机"}'}
              />
              {formTargetType === 'skill' ? (
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{t('schedules.payloadSkillHint')}</p>
              ) : null}
            </div>
          )}

          <div className="flex items-center justify-between">
            <Switch checked={formEnabled} onChange={setFormEnabled} label={t('schedules.formEnabled')} />
            <div className="flex gap-2">
              <Button variant="secondary" type="button" onClick={() => setDialogOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" isLoading={saving}>
                {t('common.save')}
              </Button>
            </div>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={runDetailOpen}
        onClose={() => setRunDetailOpen(false)}
        title={t('schedules.detailDialogTitle')}
        size="lg"
      >
        {selectedRun && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
              <p className="text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t('schedules.detailSkill')}:</span>{' '}
                {selectedRun.target_name || selectedRun.skill_name || selectedRun.workflow_name || '-'}
              </p>
              <p className="text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t('schedules.detailStatus')}:</span> {selectedRun.status}
              </p>
              <p className="text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t('schedules.detailTriggerType')}:</span> {selectedRun.trigger_type}
              </p>
              <p className="text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t('schedules.detailDuration')}:</span>{' '}
                {selectedRun.duration_ms != null ? `${selectedRun.duration_ms}ms` : '-'}
              </p>
              <p className="text-gray-600 dark:text-gray-300 md:col-span-2">
                <span className="font-medium">{t('schedules.detailStartedAt')}:</span>{' '}
                {formatDate(selectedRun.started_at)}
              </p>
            </div>

            {selectedRun.error ? (
              <div className="space-y-1">
                <p className="text-sm font-medium text-red-700 dark:text-red-300">
                  {t('schedules.detailError')}
                </p>
                <pre className="text-xs rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 text-red-800 dark:text-red-200 overflow-auto max-h-52">
{selectedRun.error}
                </pre>
              </div>
            ) : null}

            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {t('schedules.detailPayload')}
              </p>
              <pre className="text-xs rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-3 text-gray-800 dark:text-gray-200 overflow-auto max-h-52">
{JSON.stringify(selectedRun.payload || {}, null, 2)}
              </pre>
            </div>

            {(() => {
              // For workflow schedule runs, the result is the workflow output_payload
              // (with node_runs). Render the report panel so charts/files are visible.
              const res = (selectedRun.result || {}) as Record<string, unknown>
              const nodeRuns = Array.isArray(res.node_runs) ? res.node_runs : undefined
              if (!nodeRuns) return null
              return (
                <WorkflowReportPanel
                  nodeRuns={nodeRuns as Array<{ node_id: string; node_type: string; node_name?: string; result?: unknown }>}
                  outputPayload={res as Record<string, unknown> | undefined}
                />
              )
            })()}

            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {t('schedules.detailResult')}
              </p>
              <pre className="text-xs rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-3 text-gray-800 dark:text-gray-200 overflow-auto max-h-72">
{JSON.stringify(selectedRun.result || {}, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  )
}
