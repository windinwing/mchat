import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Download,
  Globe,
  Plus,
  CheckCircle,
  XCircle,
  Upload,
  X,
  Zap,
  Settings2,
  Trash2,
} from 'lucide-react'
import { getChannelTypes } from '@/i18n/channelTypes'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate } from '@/lib/utils'

interface Channel {
  id: string
  user_id: string
  name: string
  channel_type: string
  config: Record<string, any> | null
  enabled: boolean
  is_connected: boolean
  created_at: string
  updated_at: string
}

interface CustomerConfigOption {
  id: string
  name: string
}

interface WorkflowOption {
  id: string
  name: string
  enabled: boolean
}

interface ChannelWorkflowBinding {
  id?: string
  workflow_id: string
  workflow_name: string
  enabled: boolean
  priority: number
  match_type: 'all' | 'contains' | 'regex'
  match_expr?: string | null
}

interface ChannelWorkflowPreviewResponse {
  event_type: string
  dispatch_mode: 'all' | 'first_match'
  matched_workflow_ids: string[]
  evaluations: Array<{
    workflow_id: string
    workflow_name: string
    priority: number
    match_type: 'all' | 'contains' | 'regex'
    match_expr?: string | null
    matched: boolean
    selected: boolean
    reason_code: string
    reason_detail?: string | null
    error?: string | null
    matched_text?: string | null
    match_start?: number | null
    match_end?: number | null
  }>
}

interface ChannelWorkflowStatsResponse {
  channel_id: string
  days: number
  items: Array<{
    workflow_id: string
    workflow_name: string
    total_runs: number
    success_runs: number
    failed_runs: number
    last_run_at?: string | null
  }>
}

export function ChannelsPage() {
  const { t, i18n } = useTranslation()
  const CHANNEL_TYPES = useMemo(() => getChannelTypes(t), [t, i18n.language])
  const [channels, setChannels] = useState<Channel[]>([])
  const [customerConfigs, setCustomerConfigs] = useState<CustomerConfigOption[]>([])
  const [workflows, setWorkflows] = useState<WorkflowOption[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null)
  const [saving, setSaving] = useState(false)
  const [newChannel, setNewChannel] = useState({
    name: '',
    channel_type: 'web_widget',
    config: {} as Record<string, any>,
    enabled: false,
  })
  const [editConfig, setEditConfig] = useState<Record<string, any>>({})
  const [editName, setEditName] = useState('')
  const [editEnabled, setEditEnabled] = useState(false)
  const [webhookInfo, setWebhookInfo] = useState<{
    webhook_url: string
    hint: string
  } | null>(null)
  const [editWorkflowIds, setEditWorkflowIds] = useState<string[]>([])
  const [editWorkflowBindings, setEditWorkflowBindings] = useState<ChannelWorkflowBinding[]>([])
  const [workflowDispatchMode, setWorkflowDispatchMode] = useState<'all' | 'first_match'>('all')
  const [previewMessage, setPreviewMessage] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewMatchedIds, setPreviewMatchedIds] = useState<string[]>([])
  const [previewEvaluations, setPreviewEvaluations] = useState<
    ChannelWorkflowPreviewResponse['evaluations']
  >([])
  const [draggingWorkflowId, setDraggingWorkflowId] = useState<string | null>(null)
  const [workflowTestOpen, setWorkflowTestOpen] = useState(false)
  const [workflowStatsOpen, setWorkflowStatsOpen] = useState(false)
  const [statsDays, setStatsDays] = useState(7)
  const [statsData, setStatsData] = useState<ChannelWorkflowStatsResponse['items']>([])

  useEffect(() => {
    loadChannels()
    loadCustomerConfigs()
    loadWorkflows()
  }, [])

  const loadCustomerConfigs = async () => {
    try {
      const data = await api.get<CustomerConfigOption[]>('/agents/customer-configs')
      setCustomerConfigs(data)
    } catch {
      /* optional */
    }
  }

  const loadChannels = async () => {
    try {
      const data = await api.get<Channel[]>('/channels')
      setChannels(data)
    } catch (err) {
      console.error('Failed to load channels:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadWorkflows = async () => {
    try {
      const data = await api.get<WorkflowOption[]>('/workflows')
      setWorkflows(data)
    } catch {
      /* optional */
    }
  }

  const handleCreate = async () => {
    if (!newChannel.name.trim()) return
    setSaving(true)
    try {
      const created = await api.post<Channel>('/channels', {
        name: newChannel.name,
        channel_type: newChannel.channel_type,
        config: newChannel.config,
        enabled: newChannel.enabled,
      })
      setChannels((prev) => [...prev, created])
      setCreateOpen(false)
      setNewChannel({ name: '', channel_type: 'web_widget', config: {}, enabled: false })
      toast(t('channels.toastCreated'), { type: 'success' })
    } catch (err: any) {
      toast(t('channels.toastCreateFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const openEdit = async (ch: Channel) => {
    setEditingChannel(ch)
    setEditConfig(ch.config || {})
    setEditName(ch.name)
    setEditEnabled(ch.enabled)
    setEditWorkflowIds([])
    setEditWorkflowBindings([])
    const modeRaw = String((ch.config || {}).workflow_dispatch_mode || 'all')
    setWorkflowDispatchMode(modeRaw === 'first_match' ? 'first_match' : 'all')
    setPreviewMessage('')
    setPreviewMatchedIds([])
    setPreviewEvaluations([])
    setWebhookInfo(null)
    setEditOpen(true)
    const webhookTypes = new Set([
      'wechat',
      'telegram',
      'dingtalk',
      'whatsapp',
      'slack',
      'line',
      'custom',
    ])
    if (webhookTypes.has(ch.channel_type)) {
      try {
        const info = await api.get<{ webhook_url: string; hint: string }>(
          `/channels/${ch.id}/webhook-info`,
        )
        if (info.webhook_url) setWebhookInfo(info)
      } catch {
        /* optional */
      }
    }
    try {
      const bindings = await api.get<ChannelWorkflowBinding[]>(`/channels/${ch.id}/workflows`)
      setEditWorkflowBindings(bindings)
      setEditWorkflowIds(bindings.filter((b) => b.enabled).map((b) => b.workflow_id))
    } catch {
      setEditWorkflowIds([])
      setEditWorkflowBindings([])
    }
    setWorkflowTestOpen(false)
    setWorkflowStatsOpen(false)
    setStatsData([])
    setPreviewMatchedIds([])
    setPreviewEvaluations([])
  }

  const handleUpdate = async () => {
    if (!editingChannel) return
    setSaving(true)
    try {
      await api.put(`/channels/${editingChannel.id}`, {
        name: editName,
        config: {
          ...editConfig,
          workflow_dispatch_mode: workflowDispatchMode,
        },
        enabled: editEnabled,
      })
      await api.put(`/channels/${editingChannel.id}/workflows`, {
        bindings: editWorkflowIds
          .map((workflowId, idx) => {
            const binding = editWorkflowBindings.find((item) => item.workflow_id === workflowId)
            if (!binding) return null
            return {
              workflow_id: workflowId,
              enabled: true,
              priority: idx + 1,
              match_type: binding.match_type,
              match_expr: binding.match_expr || null,
            }
          })
          .filter(Boolean)
          .map((item) => ({
            workflow_id: item!.workflow_id,
            enabled: true,
            priority: item!.priority,
            match_type: item!.match_type,
            match_expr: item!.match_expr,
          })),
      })
      setChannels((prev) =>
        prev.map((c) =>
          c.id === editingChannel.id
            ? { ...c, name: editName, config: editConfig, enabled: editEnabled }
            : c,
        ),
      )
      setEditOpen(false)
      toast(t('channels.toastUpdated'), { type: 'success' })
    } catch (err: any) {
      toast(t('channels.toastUpdateFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const moveWorkflowPriority = (workflowId: string, direction: 'up' | 'down') => {
    setEditWorkflowIds((prev) => {
      const idx = prev.indexOf(workflowId)
      if (idx < 0) return prev
      const target = direction === 'up' ? idx - 1 : idx + 1
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[target]] = [next[target], next[idx]]
      return next
    })
  }

  const reorderWorkflowByDrag = (targetWorkflowId: string) => {
    if (!draggingWorkflowId || draggingWorkflowId === targetWorkflowId) return
    setEditWorkflowIds((prev) => {
      const from = prev.indexOf(draggingWorkflowId)
      const to = prev.indexOf(targetWorkflowId)
      if (from < 0 || to < 0) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
    setDraggingWorkflowId(null)
  }

  const runWorkflowPreview = async () => {
    if (!editingChannel) return
    setPreviewLoading(true)
    try {
      const bindings = editWorkflowIds
        .map((workflowId, idx) => {
          const binding = editWorkflowBindings.find((item) => item.workflow_id === workflowId)
          if (!binding) return null
          return {
            workflow_id: workflowId,
            enabled: true,
            priority: idx + 1,
            match_type: binding.match_type,
            match_expr: binding.match_expr || null,
          }
        })
        .filter(Boolean)
      const resp = await api.post<ChannelWorkflowPreviewResponse>(
        `/channels/${editingChannel.id}/workflows/preview`,
        {
          event_type: 'message',
          content: previewMessage,
          dispatch_mode: workflowDispatchMode,
          bindings,
        },
      )
      setPreviewMatchedIds(resp.matched_workflow_ids || [])
      setPreviewEvaluations(resp.evaluations || [])
      toast(
        t('channels.previewMatchedCount', {
          count: (resp.matched_workflow_ids || []).length,
        }),
        { type: 'success' },
      )
    } catch (err: any) {
      toast(t('channels.previewFailed'), { type: 'error', message: err.message })
    } finally {
      setPreviewLoading(false)
    }
  }

  const exportWorkflowBundle = async () => {
    if (!editingChannel) return
    try {
      const data = await api.get<{ dispatch_mode: string; bindings: any[] }>(
        `/channels/${editingChannel.id}/workflows/export`,
      )
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2))
      toast(t('channels.exportCopied'), { type: 'success' })
    } catch (err: any) {
      toast(t('channels.exportFailed'), { type: 'error', message: err.message })
    }
  }

  const importWorkflowBundle = async () => {
    if (!editingChannel) return
    const raw = window.prompt(t('channels.importPrompt'))
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      await api.post(`/channels/${editingChannel.id}/workflows/import`, parsed)
      toast(t('channels.importSuccess'), { type: 'success' })
      await openEdit(editingChannel)
    } catch (err: any) {
      toast(t('channels.importFailed'), { type: 'error', message: err.message })
    }
  }

  const loadWorkflowStats = async (channelId: string, days: number) => {
    try {
      const data = await api.get<ChannelWorkflowStatsResponse>(`/channels/${channelId}/workflows/stats`, {
        days: String(days),
      })
      setStatsData(data.items || [])
    } catch {
      setStatsData([])
    }
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await api.put(`/channels/${id}`, { enabled })
      setChannels((prev) =>
        prev.map((c) => (c.id === id ? { ...c, enabled } : c)),
      )
    } catch (err: any) {
      toast(t('channels.toastOpFailed'), { type: 'error', message: err.message })
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/channels/${id}`)
      setChannels((prev) => prev.filter((c) => c.id !== id))
      toast(t('channels.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('channels.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  const handleTest = async (ch: Channel) => {
    try {
      const result = await api.post<{
        ok: boolean
        message: string
        preview_url?: string
      }>('/channels/test', {
        channel_type: ch.channel_type,
        config: ch.config || {},
      })
      if (result.ok) {
        toast(result.message, { type: 'success' })
        if (ch.channel_type === 'web_widget' && result.preview_url) {
          window.open(result.preview_url, '_blank', 'noopener,noreferrer')
        }
      } else {
        toast(result.message, { type: 'error' })
      }
    } catch (err: any) {
      toast(t('channels.toastTestFailed'), { type: 'error', message: err.message })
    }
  }

  const renderConfigField = (
    field: { key: string; label: string; placeholder: string; type?: string },
    config: Record<string, string>,
    onChange: (key: string, value: string) => void,
    channelType: string,
  ) => {
    if (
      (channelType === 'web_widget' && field.key === 'widget_id') ||
      (channelType === 'wechat' && field.key === 'customer_id')
    ) {
      const valueKey = channelType === 'wechat' ? 'customer_id' : 'widget_id'
      return (
        <div key={field.key} className="space-y-1">
          <Select
            label={field.label}
            options={[
              { value: '', label: t('channels.selectCustomerConfig') },
              ...customerConfigs.map((c) => ({
                value: c.id,
                label: `${c.name} (${c.id.slice(0, 8)}…)`,
              })),
            ]}
            value={config[valueKey] || ''}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
              onChange(valueKey, e.target.value)
            }
          />
          {channelType === 'web_widget' && (
            <p className="text-xs text-gray-500">
              {t('channels.widgetTestHint')}{' '}
              <a href="/widget/demo" className="text-primary-600 hover:underline" target="_blank" rel="noreferrer">
                {t('channels.widgetDemoLink')}
              </a>
            </p>
          )}
          {channelType === 'wechat' && (
            <p className="text-xs text-gray-500">
              {t('channels.wechatAgentHint')}
            </p>
          )}
        </div>
      )
    }
    return (
      <Input
        key={field.key}
        label={field.label}
        type={field.type || 'text'}
        value={config[field.key] || ''}
        onChange={(e) => onChange(field.key, e.target.value)}
        placeholder={field.placeholder}
      />
    )
  }

  const selectedType = newChannel.channel_type
  const typeFields = CHANNEL_TYPES[selectedType]?.fields || []
  const selectedWorkflowSet = new Set(editWorkflowIds)
  const availableWorkflowsToAdd = workflows.filter((wf) => !selectedWorkflowSet.has(wf.id))

  const addWorkflowBinding = (workflowId: string) => {
    const wf = workflows.find((w) => w.id === workflowId)
    if (!wf || selectedWorkflowSet.has(workflowId)) return
    setEditWorkflowIds((prev) => [...prev, workflowId])
    setEditWorkflowBindings((prev) => [
      ...prev,
      {
        workflow_id: workflowId,
        workflow_name: wf.name,
        enabled: true,
        priority: 100,
        match_type: 'all',
        match_expr: '',
      },
    ])
  }

  const removeWorkflowBinding = (workflowId: string) => {
    setEditWorkflowIds((prev) => prev.filter((id) => id !== workflowId))
    setEditWorkflowBindings((prev) => prev.filter((item) => item.workflow_id !== workflowId))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('channels.pageTitle')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('channels.pageSubtitle')}
          </p>
        </div>
        <Button
          leftIcon={<Plus className="w-4 h-4" />}
          onClick={() => setCreateOpen(true)}
        >
          {t('channels.addChannel')}
        </Button>
      </div>

      {channels.length === 0 ? (
        <Card>
          <CardContent>
            <div className="flex flex-col items-center py-16 text-gray-400">
              <Globe className="w-16 h-16 mb-4 opacity-30" />
              <p className="text-base font-medium mb-1">{t('channels.emptyTitle')}</p>
              <p className="text-sm mb-4">{t('channels.emptyHint')}</p>
              <Button onClick={() => setCreateOpen(true)} leftIcon={<Plus className="w-4 h-4" />}>
                {t('channels.addFirst')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {channels.map((ch) => {
            const typeInfo = CHANNEL_TYPES[ch.channel_type] || CHANNEL_TYPES.custom
            const Icon = typeInfo.icon
            return (
              <Card key={ch.id} hover>
                <CardContent className="py-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                        ch.enabled
                          ? 'bg-green-50 dark:bg-green-900/20'
                          : 'bg-gray-100 dark:bg-gray-700'
                      }`}>
                        <Icon className={`w-5 h-5 ${
                          ch.enabled ? 'text-green-600 dark:text-green-400' : 'text-gray-400'
                        }`} />
                      </div>
                      <div>
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">{ch.name}</h3>
                        <p className="text-xs text-gray-500">{typeInfo.label}</p>
                      </div>
                    </div>
                    <Switch
                      checked={ch.enabled}
                      onChange={(checked) => handleToggle(ch.id, checked)}
                    />
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-gray-700">
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      {ch.enabled ? (
                        <Badge variant="success" size="sm">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          {t('common.enabled')}
                        </Badge>
                      ) : (
                        <Badge variant="default" size="sm">
                          <XCircle className="w-3 h-3 mr-1" />
                          {t('common.disabled')}
                        </Badge>
                      )}
                      <span>{formatDate(ch.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleTest(ch)}
                        className="p-1.5 rounded text-gray-400 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                        title={t('channels.testConnection')}
                      >
                        <Zap className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openEdit(ch)}
                        className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
                        title={t('common.configure')}
                      >
                        <Settings2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(ch.id)}
                        className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                        title={t('common.delete')}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('channels.dialogAdd')}
        size="md"
      >
        <div className="space-y-4">
          <Select
            label={t('channels.channelType')}
            options={Object.entries(CHANNEL_TYPES).map(([k, v]) => ({ value: k, label: v.label }))}
            value={selectedType}
            onChange={(e: any) => {
              setNewChannel({ ...newChannel, channel_type: e.target.value, config: {} })
            }}
          />
          <Input
            label={t('channels.channelName')}
            value={newChannel.name}
            onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })}
            placeholder={t('channels.channelNamePlaceholder')}
          />
          <p className="text-xs text-gray-500">{CHANNEL_TYPES[selectedType]?.description}</p>
          {typeFields.map((field) =>
            renderConfigField(
              field,
              newChannel.config,
              (key, value) =>
                setNewChannel({
                  ...newChannel,
                  config: { ...newChannel.config, [key]: value },
                }),
              selectedType,
            ),
          )}
          {selectedType === 'wechat' && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('channels.wechatActivePushHint')}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreate} isLoading={saving} disabled={!newChannel.name.trim()}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={t('channels.dialogEdit')}
        size="md"
      >
        {editingChannel && (
          <div className="space-y-4">
            <Input
              label={t('channels.channelName')}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
            <p className="text-xs text-gray-500">
              {t('channels.typeLabel')}: {CHANNEL_TYPES[editingChannel.channel_type]?.label || editingChannel.channel_type}
            </p>
            {(CHANNEL_TYPES[editingChannel.channel_type]?.fields || []).map((field) =>
              renderConfigField(
                field,
                editConfig,
                (key, value) => setEditConfig({ ...editConfig, [key]: value }),
                editingChannel.channel_type,
              ),
            )}
            {editingChannel.channel_type === 'wechat' && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                {t('channels.wechatActivePushHint')}
              </p>
            )}
            {webhookInfo && (
              <div className="rounded-lg bg-gray-50 dark:bg-gray-900 p-3 space-y-2 text-xs">
                <p className="font-medium text-gray-700 dark:text-gray-300">{t('channels.webhookUrlLabel')}</p>
                <code className="block break-all text-primary-700 dark:text-primary-400">
                  {webhookInfo.webhook_url}
                </code>
                <p className="text-gray-500">{webhookInfo.hint}</p>
              </div>
            )}
            <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {t('channels.workflowRulesTitle')}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {t('channels.workflowRulesHint')}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    title={t('channels.exportBundle')}
                    aria-label={t('channels.exportBundle')}
                    onClick={exportWorkflowBundle}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    title={t('channels.importBundle')}
                    aria-label={t('channels.importBundle')}
                    onClick={importWorkflowBundle}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    <Upload className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {workflows.length === 0 ? (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('channels.bindWorkflowsEmpty')}
                </p>
              ) : (
                <>
                  {editWorkflowIds.length >= 2 && (
                    <div className="space-y-1">
                      <label className="text-xs text-gray-600 dark:text-gray-400">
                        {t('channels.workflowDispatchMode')}
                      </label>
                      <select
                        className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                        value={workflowDispatchMode}
                        onChange={(e) => setWorkflowDispatchMode(e.target.value as 'all' | 'first_match')}
                      >
                        <option value="all">{t('channels.workflowDispatchModeAll')}</option>
                        <option value="first_match">{t('channels.workflowDispatchModeFirstMatch')}</option>
                      </select>
                    </div>
                  )}

                  {editWorkflowIds.length === 0 ? (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {t('channels.workflowRulesEmpty')}
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {editWorkflowIds.map((workflowId, idx) => {
                        const wf = workflows.find((w) => w.id === workflowId)
                        const binding = editWorkflowBindings.find((b) => b.workflow_id === workflowId)
                        if (!wf || !binding) return null
                        return (
                          <div
                            key={workflowId}
                            className="rounded-lg border border-gray-200 dark:border-gray-700 p-2 space-y-2"
                            draggable
                            onDragStart={() => setDraggingWorkflowId(workflowId)}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={() => reorderWorkflowByDrag(workflowId)}
                            onDragEnd={() => setDraggingWorkflowId(null)}
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium text-gray-400 w-4">{idx + 1}</span>
                              <span className="flex-1 truncate text-sm font-medium text-gray-800 dark:text-gray-200">
                                {wf.name}
                              </span>
                              {!wf.enabled && (
                                <span className="text-xs text-amber-600">({t('common.disabled')})</span>
                              )}
                              <div className="flex items-center gap-0.5">
                                <button
                                  type="button"
                                  className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
                                  onClick={() => moveWorkflowPriority(workflowId, 'up')}
                                  disabled={idx === 0}
                                  title={t('channels.moveUp')}
                                >
                                  <ArrowUp className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  type="button"
                                  className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
                                  onClick={() => moveWorkflowPriority(workflowId, 'down')}
                                  disabled={idx === editWorkflowIds.length - 1}
                                  title={t('channels.moveDown')}
                                >
                                  <ArrowDown className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  type="button"
                                  className="p-1 rounded text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                                  onClick={() => removeWorkflowBinding(workflowId)}
                                  title={t('common.delete')}
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pl-6">
                              <select
                                className="block w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                                value={binding.match_type}
                                onChange={(e) => {
                                  const value = e.target.value as 'all' | 'contains' | 'regex'
                                  setEditWorkflowBindings((prev) =>
                                    prev.map((item) =>
                                      item.workflow_id === workflowId ? { ...item, match_type: value } : item,
                                    ),
                                  )
                                }}
                              >
                                <option value="all">{t('channels.matchTypeAll')}</option>
                                <option value="contains">{t('channels.matchTypeContains')}</option>
                                <option value="regex">{t('channels.matchTypeRegex')}</option>
                              </select>
                              <Input
                                value={binding.match_expr || ''}
                                onChange={(e) => {
                                  const value = e.target.value
                                  setEditWorkflowBindings((prev) =>
                                    prev.map((item) =>
                                      item.workflow_id === workflowId ? { ...item, match_expr: value } : item,
                                    ),
                                  )
                                }}
                                placeholder={t('channels.matchExprPlaceholder')}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {availableWorkflowsToAdd.length > 0 && (
                    <select
                      className="block w-full rounded-lg border border-dashed border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-300"
                      value=""
                      onChange={(e) => {
                        if (e.target.value) addWorkflowBinding(e.target.value)
                      }}
                    >
                      <option value="">{t('channels.workflowAddPlaceholder')}</option>
                      {availableWorkflowsToAdd.map((wf) => (
                        <option key={wf.id} value={wf.id}>
                          {wf.name}
                          {!wf.enabled ? ` (${t('common.disabled')})` : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </>
              )}

              {editWorkflowIds.length > 0 && (
                <>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between rounded-md px-1 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800/60"
                    onClick={() => setWorkflowTestOpen((v) => !v)}
                  >
                    <span>{t('channels.previewTitle')}</span>
                    {workflowTestOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                  {workflowTestOpen && (
                    <div className="space-y-2 pl-1">
                      <Input
                        value={previewMessage}
                        onChange={(e) => setPreviewMessage(e.target.value)}
                        placeholder={t('channels.previewInputPlaceholder')}
                      />
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={runWorkflowPreview}
                          isLoading={previewLoading}
                        >
                          {t('channels.previewRun')}
                        </Button>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {t('channels.previewMatched')} {previewMatchedIds.length}
                        </span>
                      </div>
                      {previewMatchedIds.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {previewMatchedIds.map((id) => {
                            const wf = workflows.find((item) => item.id === id)
                            return (
                              <Badge key={id} variant="success" size="sm">
                                {wf?.name || id}
                              </Badge>
                            )
                          })}
                        </div>
                      )}
                      {previewEvaluations.length > 0 && (
                        <div className="space-y-1 max-h-40 overflow-auto pr-1">
                          {previewEvaluations.map((item) => (
                            <div
                              key={item.workflow_id}
                              className="rounded border border-gray-200 dark:border-gray-700 px-2 py-1.5 text-xs"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{item.workflow_name || item.workflow_id}</span>
                                <Badge variant={item.selected ? 'success' : 'default'} size="sm">
                                  {item.selected ? t('channels.previewSelected') : t('channels.previewNotSelected')}
                                </Badge>
                              </div>
                              <p className="text-gray-600 dark:text-gray-400 mt-1">
                                {t(`channels.previewReason.${item.reason_code}`)}
                                {item.reason_detail ? `：${item.reason_detail}` : ''}
                              </p>
                              {item.error ? (
                                <p className="text-red-600 dark:text-red-400 mt-1">{item.error}</p>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    type="button"
                    className="flex w-full items-center justify-between rounded-md px-1 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800/60"
                    onClick={() => {
                      setWorkflowStatsOpen((v) => {
                        const next = !v
                        if (next && editingChannel) loadWorkflowStats(editingChannel.id, statsDays)
                        return next
                      })
                    }}
                  >
                    <span>{t('channels.matchStats')}</span>
                    {workflowStatsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                  {workflowStatsOpen && (
                    <div className="space-y-2 pl-1">
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          value={String(statsDays)}
                          onChange={(e) => setStatsDays(Math.max(1, Math.min(90, Number(e.target.value) || 7)))}
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => editingChannel && loadWorkflowStats(editingChannel.id, statsDays)}
                        >
                          {t('channels.refreshStats')}
                        </Button>
                      </div>
                      {statsData.length === 0 ? (
                        <p className="text-xs text-gray-500 dark:text-gray-400">{t('channels.statsEmpty')}</p>
                      ) : (
                        <div className="space-y-1 max-h-32 overflow-auto pr-1">
                          {statsData.map((item) => (
                            <div
                              key={item.workflow_id}
                              className="rounded border border-gray-200 dark:border-gray-700 px-2 py-1.5 text-xs"
                            >
                              <p className="font-medium">{item.workflow_name || item.workflow_id}</p>
                              <p className="text-gray-500">
                                {t('channels.statsTotal')}: {item.total_runs} · {t('channels.statsSuccess')}:{' '}
                                {item.success_runs} · {t('channels.statsFailed')}: {item.failed_runs}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center justify-between pt-2">
              <span className="text-sm text-gray-700 dark:text-gray-300">{t('channels.enable')}</span>
              <Switch checked={editEnabled} onChange={setEditEnabled} />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setEditOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleUpdate} isLoading={saving}>
                {t('common.save')}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  )
}
