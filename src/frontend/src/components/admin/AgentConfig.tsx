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
import {
  applyProviderDefaults,
  getDefaultModel,
  PROVIDER_DEFAULT_BASE_URLS,
  PROVIDER_MODEL_OPTIONS,
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
  top_p?: number
  is_default: boolean
  created_at: string
  updated_at: string
}

export function AgentConfig() {
  const { t } = useTranslation()
  const modelOptions = useMemo(() => {
    const opts = { ...PROVIDER_MODEL_OPTIONS }
    opts.deepseek = [
      { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
      { value: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
      {
        value: 'deepseek-chat',
        label: t('agents.modelDeepseekChatDeprecated'),
      },
      {
        value: 'deepseek-reasoner',
        label: t('agents.modelDeepseekReasonerDeprecated'),
      },
    ]
    opts['openai-compatible'] = [
      { value: 'custom-model', label: t('agents.customModel') },
    ]
    return opts
  }, [t])
  const providerOptions = useMemo(
    () => [
      { value: 'openai', label: t('agents.providerOpenai') },
      { value: 'anthropic', label: t('agents.providerAnthropic') },
      { value: 'google', label: t('agents.providerGoogle') },
      { value: 'deepseek', label: t('agents.providerDeepseek') },
      { value: 'ollama', label: t('agents.providerOllama') },
      { value: 'groq', label: t('agents.providerGroqFast') },
      { value: 'zhipu', label: t('agents.providerZhipu') },
      { value: 'zhipu-coding', label: t('agents.providerZhipuCoding') },
      { value: 'moonshot', label: t('agents.providerMoonshot') },
      { value: 'siliconflow', label: t('agents.providerSiliconflow') },
      { value: 'together', label: t('agents.providerTogether') },
      { value: 'openai-compatible', label: t('agents.providerOpenAiCompatible') },
    ],
    [t],
  )

  const tabs = useMemo(
    () => [
      { id: 'basic', label: t('agents.tabBasic') },
      { id: 'api', label: t('agents.tabApi') },
      { id: 'model', label: t('agents.tabModel') },
      { id: 'prompt', label: t('agents.tabPrompt') },
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
  const [activeTab, setActiveTab] = useState('basic')
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
        setSelectedAgentId(data[0].id)
        setConfig(data[0])
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
      const currentKey = config.api_key  // Remember current key
      const payload: any = { ...config }
      delete payload.id
      delete payload.created_at
      delete payload.updated_at
      delete payload.user_id

      const updated = await api.put<AgentConfig>(
        `/agents/ai-configs/${selectedAgentId}`,
        payload,
      )
      // Merge: response api_key wins, fallback to what user typed
      setConfig({ ...config, ...updated, api_key: updated.api_key || currentKey || '' })
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

  return (
    <div className="space-y-4">
      {/* Agent selector */}
      <div className="flex items-center gap-3">
        <Select
          options={agents.map((a) => ({ value: a.id, label: a.name }))}
          value={selectedAgentId || ''}
          onChange={(e: any) => selectAgent(e.target.value)}
          className="w-60"
        />
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<Plus className="w-4 h-4" />}
          onClick={() => setCreateOpen(true)}
        >
          {t('agents.newConfig')}
        </Button>
        {selectedAgentId && (
          <Button
            size="sm"
            variant="ghost"
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
              </h3>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">{t('agents.defaultToggle')}</span>
                <Switch
                  checked={config.is_default ?? false}
                  onChange={(checked) => setConfig({ ...config, is_default: checked })}
                />
              </div>
              <Button
                leftIcon={<Save className="w-4 h-4" />}
                onClick={handleSave}
                isLoading={saving}
              >
                {t('common.save')}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

          <TabPanel id="basic" activeTab={activeTab}>
            <div className="space-y-4 pt-4">
              <Input
                label={t('agents.configName')}
                value={selectedLabel || ''}
                onChange={(e: any) => setConfig({ ...config, name: e.target.value })}
                placeholder={t('agents.configNamePlaceholder')}
              />
              <div className="grid grid-cols-2 gap-4">
                <Select
                  label={t('agents.providerLabel')}
                  options={providerOptions}
                  value={config.provider || 'deepseek'}
                  onChange={(e: any) => {
                    setConfig(applyProviderDefaults(config, e.target.value))
                  }}
                />
                <Select
                  label={t('agents.modelLabel')}
                  options={modelOptions[config.provider || 'deepseek'] || [
                    { value: 'custom', label: t('agents.customModel') },
                  ]}
                  value={config.model || ''}
                  onChange={(e: any) =>
                    setConfig({ ...config, model: e.target.value })
                  }
                />
              </div>
            </div>
          </TabPanel>

          <TabPanel id="api" activeTab={activeTab}>
            <div className="space-y-4 pt-4">
              <div>
                <Input
                  label={t('agents.apiKeyLabel')}
                  type="password"
                  value={config.api_key || ''}
                  onChange={(e: any) => setConfig({ ...config, api_key: e.target.value })}
                  placeholder={t('agents.apiKeyPlaceholder')}
                  autoComplete="off"
                />
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                  {t('agents.apiKeyHint')}
                </p>
              </div>
              <div>
                <Input
                  label={t('agents.apiBaseLabel')}
                  value={config.api_base || ''}
                  onChange={(e: any) => setConfig({ ...config, api_base: e.target.value })}
                  placeholder={t('agents.apiBasePlaceholder')}
                />
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                  {t('agents.apiBaseHint')}
                </p>
              </div>
            </div>
          </TabPanel>

          <TabPanel id="model" activeTab={activeTab}>
            <div className="space-y-4 pt-4">
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label={t('agents.temperature')}
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
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
                  step={1}
                  value={config.max_tokens ?? 2048}
                  onChange={(e: any) =>
                    setConfig({
                      ...config,
                      max_tokens: Math.max(1, parseInt(e.target.value, 10) || 1),
                    })
                  }
                />
                <div />
              </div>
            </div>
          </TabPanel>

          <TabPanel id="prompt" activeTab={activeTab}>
            <div className="pt-4">
              <Textarea
                label={t('agents.systemPromptLabel')}
                value={config.system_prompt || ''}
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
