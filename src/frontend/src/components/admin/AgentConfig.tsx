import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Bot, Save, Plus, Trash2 } from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Switch } from '@/components/ui/Switch'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { useAuthStore } from '@/stores/auth'
import {
  getDefaultModel,
  PROVIDER_DEFAULT_BASE_URLS,
} from '@/lib/providerDefaults'

interface AgentConfig {
  id: string
  name: string
  provider: string
  model: string
  api_key: string
  api_base: string | null
  system_prompt: string | null
  temperature: number
  max_tokens: number
  thinking_enabled?: boolean
  top_p?: number
  is_default: boolean
  created_at: string
  updated_at: string
  /** True for a system-wide default owned by another account (read-only here). */
  shared?: boolean
}

export function AgentConfig() {
  const { t } = useTranslation()
  // Admins may edit shared system defaults (owned by another account).
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')
  const tabs = useMemo(
    () => [
      { id: 'prompt', label: t('agents.tabPrompt') },
      { id: 'model', label: t('agents.tabModel') },
    ],
    [t],
  )

  const [agents, setAgents] = useState<AgentConfig[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [config, setConfig] = useState<Partial<AgentConfig>>({
    provider: 'deepseek',
    model: getDefaultModel('deepseek'),
    temperature: 0.7,
    max_tokens: 2048,
    api_key: '',
    api_base: PROVIDER_DEFAULT_BASE_URLS.deepseek,
    is_default: true,
  })
  const [activeTab, setActiveTab] = useState('prompt')
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      const data = await api.get<AgentConfig[]>('/agents/ai-configs')
      setAgents(data)
      if (data.length > 0) {
        // Restore the previously selected config across tabs (shared with the
        // model workbench via localStorage) so switching tabs keeps the same
        // config selected instead of jumping back to the first one.
        const stored = localStorage.getItem('mchat:agents:selectedId')
        const initial = data.find((a) => a.id === stored) ?? data[0]
        setSelectedAgentId(initial.id)
        setConfig(initial)
      }
    } catch (err) {
      console.error('Failed to load agents:', err)
      toast(t('agents.toastLoadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const selectAgent = async (id: string) => {
    setSelectedAgentId(id)
    localStorage.setItem('mchat:agents:selectedId', id)
    try {
      const data = await api.get<AgentConfig>(`/agents/ai-configs/${id}`)
      setConfig(data)
    } catch (err) {
      console.error('Failed to load agent config:', err)
    }
  }

  const handleSave = async () => {
    if (!selectedAgentId) return
    setSaving(true)
    try {
      // Only persist fields edited here (system_prompt, temperature, max_tokens,
      // is_default). Provider/model/api_key/api_base are managed by the model
      // workbench — sending them would overwrite workbench values with stale ones.
      const payload: Partial<AgentConfig> = {
        system_prompt: config.system_prompt ?? null,
        temperature: config.temperature ?? 0.7,
        max_tokens: config.max_tokens ?? 2048,
        thinking_enabled: config.thinking_enabled ?? true,
        is_default: config.is_default ?? false,
      }

      const updated = await api.put<AgentConfig>(
        `/agents/ai-configs/${selectedAgentId}`,
        payload,
      )
      setConfig({ ...config, ...updated })
      setAgents((prev) =>
        prev.map((a) => (a.id === selectedAgentId ? { ...a, ...updated } : a)),
      )
      toast(t('agents.toastSaveSuccess'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const created = await api.post<AgentConfig>('/agents/ai-configs', {
        name: newName.trim(),
        provider: config.provider || 'deepseek',
        model: config.model || getDefaultModel(config.provider || 'deepseek'),
        api_key: config.api_key || '',
        api_base: config.api_base || '',
        system_prompt: config.system_prompt || '',
        temperature: config.temperature ?? 0.7,
        max_tokens: config.max_tokens ?? 2048,
        is_default: agents.length === 0,
      })
      setAgents((prev) => [...prev, created])
      setSelectedAgentId(created.id)
      setConfig(created)
      setCreateOpen(false)
      setNewName('')
      toast(t('agents.toastCreateSuccess'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastCreateFailed'), { type: 'error', message: err.message })
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/agents/ai-configs/${id}`)
      setAgents((prev) => prev.filter((a) => a.id !== id))
      if (selectedAgentId === id) {
        setSelectedAgentId(agents[0]?.id === id ? null : agents[0]?.id || null)
        if (agents.length > 1) {
          setConfig(agents[0]?.id === id ? agents[1] : agents[0])
        }
      }
      toast(t('agents.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="md" />
      </div>
    )
  }

  const selectedLabel = agents.find((a) => a.id === selectedAgentId)?.name
  const isShared = !!config.shared && !isAdmin

  return (
    <div className="space-y-4">
      {/* Agent selector */}
      <div className="flex items-center gap-3">
        <Select
          options={agents.map((a) => ({
            value: a.id,
            label: a.shared ? `${a.name} · ${t('agents.workbenchSharedBadge')}` : a.name,
          }))}
          value={selectedAgentId || ''}
          onChange={(e: any) => selectAgent(e.target.value)}
          className="w-60"
        />
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<Plus className="w-4 h-4" />}
          onClick={() => setCreateOpen(true)}
          className="!w-[150px] justify-center"
        >
          {t('agents.newConfig')}
        </Button>
        {selectedAgentId && (
          <Button
            size="sm"
            variant="ghost"
            disabled={isShared}
            onClick={() => handleDelete(selectedAgentId)}
          >
            <Trash2 className="w-4 h-4 text-red-500" />
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-primary-600" />
              <h3 className="font-medium text-gray-900 dark:text-gray-100">
                {selectedLabel || t('agents.cardTitleFallback')}
                {isShared && (
                  <span className="ml-2 align-middle text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
                    {t('agents.workbenchSharedBadge')}
                  </span>
                )}
              </h3>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">{t('agents.defaultToggle')}</span>
                <Switch
                  checked={config.is_default ?? false}
                  disabled={isShared}
                  onChange={(checked) => setConfig({ ...config, is_default: checked })}
                />
              </div>
              <Button
                leftIcon={<Save className="w-4 h-4" />}
                onClick={handleSave}
                disabled={isShared}
                isLoading={saving}
              >
                {t('common.save')}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

          <TabPanel id="model" activeTab={activeTab}>
            <div className="space-y-4 pt-4">
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label={t('agents.temperature')}
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  disabled={isShared}
                  value={config.temperature ?? 0.7}
                  onChange={(e: any) =>
                    setConfig({
                      ...config,
                      temperature: parseFloat(e.target.value),
                    })
                  }
                />
                <Input
                  label={t('agents.maxTokens')}
                  type="number"
                  min={1}
                  max={65536}
                  step={1}
                  disabled={isShared}
                  value={config.max_tokens ?? 2048}
                  onChange={(e: any) =>
                    setConfig({
                      ...config,
                      max_tokens: Math.min(65536, Math.max(1, parseInt(e.target.value, 10) || 1)),
                    })
                  }
                />
                <div className="flex flex-col justify-center">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('agents.thinkingMode')}
                  </label>
                  <div className="flex items-center gap-2 h-[38px]">
                    <Switch
                      checked={config.thinking_enabled ?? true}
                      disabled={isShared}
                      onChange={(checked) =>
                        setConfig({ ...config, thinking_enabled: checked })
                      }
                    />
                    <span className="text-xs text-gray-400">
                      {config.thinking_enabled === false
                        ? t('agents.thinkingOff')
                        : t('agents.thinkingOn')}
                    </span>
                  </div>
                </div>
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {t('agents.thinkingHint')}
              </p>
            </div>
          </TabPanel>

          <TabPanel id="prompt" activeTab={activeTab}>
            <div className="pt-4">
              <Textarea
                label={t('agents.systemPromptLabel')}
                value={config.system_prompt || ''}
                disabled={isShared}
                onChange={(e: any) =>
                  setConfig({ ...config, system_prompt: e.target.value })
                }
                placeholder={t('agents.systemPromptPlaceholder')}
                rows={10}
              />
              <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
                {t('agents.systemPromptHint')}
              </p>
            </div>
          </TabPanel>
        </CardContent>
      </Card>

      {/* Create Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title={t('agents.dialogCreateAiTitle')} size="sm">
        <div className="space-y-4">
          <Input
            label={t('agents.configName')}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('agents.configNamePlaceholder')}
            onKeyDown={(e: any) => e.key === 'Enter' && handleCreate()}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={!newName.trim()}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
