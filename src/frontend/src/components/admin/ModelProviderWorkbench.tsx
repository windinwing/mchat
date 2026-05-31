import React, { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Bot,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Zap,
} from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/utils'
import {
  applyProviderDefaults,
  getDefaultBaseUrl,
  getDefaultModel,
  normalizeModelId,
  PROVIDER_DEFAULT_BASE_URLS,
  PROVIDER_STATIC_MODEL_IDS,
} from '@/lib/providerDefaults'

interface AIConfig {
  id: string
  name: string
  provider: string
  model: string
  api_key: string
  api_base: string | null
  system_prompt: string | null
  temperature: number
  max_tokens: number
  is_default: boolean
}

function connectionKey(c: Pick<AIConfig, 'provider' | 'api_base'>) {
  return `${c.provider}::${c.api_base || getDefaultBaseUrl(c.provider) || ''}`
}

function withProviderDefaults(data: Partial<AIConfig>): Partial<AIConfig> {
  const provider = data.provider || 'deepseek'
  return {
    ...data,
    provider,
    api_base: data.api_base?.trim() || getDefaultBaseUrl(provider),
    model: data.model
      ? normalizeModelId(provider, data.model)
      : getDefaultModel(provider),
  }
}

export function ModelProviderWorkbench() {
  const { t } = useTranslation()
  const providerOptions = useMemo(
    () => [
      { value: 'openai', label: t('agents.providerOpenai') },
      { value: 'anthropic', label: t('agents.providerAnthropic') },
      { value: 'google', label: t('agents.providerGoogle') },
      { value: 'deepseek', label: t('agents.providerDeepseek') },
      { value: 'ollama', label: t('agents.providerOllama') },
      { value: 'groq', label: t('agents.providerGroq') },
      { value: 'zhipu', label: t('agents.providerZhipu') },
      { value: 'moonshot', label: t('agents.providerMoonshot') },
      { value: 'siliconflow', label: t('agents.providerSiliconflow') },
      { value: 'together', label: t('agents.providerTogether') },
      { value: 'openai-compatible', label: t('agents.providerOpenAiCompatible') },
    ],
    [t],
  )

  const [configs, setConfigs] = useState<AIConfig[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Partial<AIConfig>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fetchingModels, setFetchingModels] = useState(false)
  const [testing, setTesting] = useState(false)
  const [remoteModels, setRemoteModels] = useState<string[]>([])
  const [modelSearch, setModelSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')

  useEffect(() => {
    loadConfigs()
  }, [])

  const loadConfigs = async () => {
    try {
      const data = await api.get<AIConfig[]>('/agents/ai-configs')
      setConfigs(data)
      if (data.length && !selectedId) {
        setSelectedId(data[0].id)
        const first = withProviderDefaults(data[0])
        setDraft(first)
        setRemoteModels(PROVIDER_STATIC_MODEL_IDS[first.provider!] || [])
      }
    } catch {
      toast(t('agents.workbenchToastLoadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const selectConfig = async (id: string) => {
    setSelectedId(id)
    setRemoteModels([])
    setModelSearch('')
    try {
      const data = await api.get<AIConfig>(`/agents/ai-configs/${id}`)
      const next = withProviderDefaults(data)
      setDraft(next)
      setRemoteModels(PROVIDER_STATIC_MODEL_IDS[next.provider!] || [])
    } catch {
      toast(t('agents.workbenchToastLoadConfigFailed'), { type: 'error' })
    }
  }

  const grouped = useMemo(() => {
    const map = new Map<string, AIConfig[]>()
    for (const c of configs) {
      const key = connectionKey(c)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(c)
    }
    return map
  }, [configs])

  const filteredModels = useMemo(() => {
    const q = modelSearch.trim().toLowerCase()
    if (!q) return remoteModels
    return remoteModels.filter((m) => m.toLowerCase().includes(q))
  }, [remoteModels, modelSearch])

  const enabledModels = useMemo(() => {
    if (!selectedId) return new Set<string>()
    const key = connectionKey(draft as AIConfig)
    const same = configs.filter((c) => connectionKey(c) === key)
    return new Set(same.map((c) => c.model))
  }, [configs, draft, selectedId])

  const handleSave = async () => {
    if (!selectedId) return
    setSaving(true)
    try {
      const payload = { ...draft }
      delete (payload as any).id
      delete (payload as any).created_at
      delete (payload as any).updated_at
      const updated = await api.put<AIConfig>(
        `/agents/ai-configs/${selectedId}`,
        payload,
      )
      setDraft({ ...draft, ...updated, api_key: updated.api_key || draft.api_key })
      setConfigs((prev) =>
        prev.map((c) => (c.id === selectedId ? { ...c, ...updated } : c)),
      )
      toast(t('agents.workbenchToastSaved'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const fetchModels = async () => {
    if (!draft.provider) return
    setFetchingModels(true)
    try {
      const res = await api.post<{ models: string[] }>('/agents/ai-configs/models', {
        provider: draft.provider,
        api_key: draft.api_key || '',
        api_base: draft.api_base || getDefaultBaseUrl(draft.provider) || '',
        config_id: selectedId || undefined,
      })
      setRemoteModels(res.models)
      if (!res.models.length) {
        toast(t('agents.workbenchToastNoModels'), { type: 'info' })
      }
    } catch (err: any) {
      toast(t('agents.workbenchToastFetchModelsFailed'), { type: 'error', message: err.message })
    } finally {
      setFetchingModels(false)
    }
  }

  const testConnection = async () => {
    setTesting(true)
    try {
      const res = await api.post<{ ok: boolean; message: string }>(
        '/agents/ai-configs/test',
        {
          provider: draft.provider,
          api_key: draft.api_key || '',
          api_base: draft.api_base,
          model: draft.model,
          config_id: selectedId || undefined,
        },
      )
      toast(res.message, { type: res.ok ? 'success' : 'error' })
    } catch (err: any) {
      toast(t('agents.workbenchToastTestFailed'), { type: 'error', message: err.message })
    } finally {
      setTesting(false)
    }
  }

  const applyModel = (modelId: string) => {
    setDraft({ ...draft, model: modelId })
    toast(t('agents.workbenchToastModelSelected', { model: modelId }), { type: 'info' })
  }

  const addModelAsConfig = async (modelId: string) => {
    const name = `${draft.provider}/${modelId}`.slice(0, 100)
    try {
      const created = await api.post<AIConfig>('/agents/ai-configs', {
        name,
        provider: draft.provider || 'deepseek',
        model: modelId,
        api_key: draft.api_key || '',
        api_base: draft.api_base || '',
        system_prompt: draft.system_prompt || '',
        temperature: draft.temperature ?? 0.7,
        max_tokens: draft.max_tokens ?? 2048,
        is_default: false,
      })
      setConfigs((prev) => [...prev, created])
      setSelectedId(created.id)
      setDraft(created)
      toast(t('agents.workbenchToastModelConfigAdded'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.workbenchToastAddFailed'), { type: 'error', message: err.message })
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const created = await api.post<AIConfig>('/agents/ai-configs', {
        name: newName.trim(),
        provider: 'deepseek',
        model: getDefaultModel('deepseek'),
        api_key: '',
        api_base: PROVIDER_DEFAULT_BASE_URLS.deepseek,
        is_default: configs.length === 0,
      })
      setConfigs((prev) => [...prev, created])
      setSelectedId(created.id)
      setDraft(created)
      setCreateOpen(false)
      setNewName('')
      toast(t('agents.workbenchToastConnectionCreated'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastCreateFailed'), { type: 'error', message: err.message })
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/agents/ai-configs/${id}`)
      const next = configs.filter((c) => c.id !== id)
      setConfigs(next)
      if (selectedId === id) {
        const first = next[0]
        setSelectedId(first?.id ?? null)
        setDraft(first ?? {})
      }
      toast(t('agents.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      toast(t('agents.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[560px]">
      <Card className="lg:w-72 shrink-0">
        <CardContent className="p-3 space-y-2">
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
              {t('agents.workbenchConnectionsTitle')}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setCreateOpen(true)}
              aria-label={t('agents.workbenchNewConnectionAria')}
            >
              <Plus className="w-4 h-4" />
            </Button>
          </div>
          <div className="max-h-[480px] overflow-y-auto space-y-3">
            {Array.from(grouped.entries()).map(([key, items]) => (
              <div key={key}>
                <p className="text-xs text-gray-400 dark:text-gray-500 px-2 mb-1 truncate" title={key}>
                  {items[0].provider}
                  {items[0].api_base ? ` · ${items[0].api_base}` : ''}
                </p>
                {items.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selectConfig(c.id)}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors',
                      selectedId === c.id
                        ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-700/50',
                    )}
                  >
                    <Bot className="w-4 h-4 shrink-0 opacity-60 text-gray-500 dark:text-gray-300" />
                    <span className="flex-1 truncate text-gray-900 dark:text-gray-100">
                      {c.name}
                    </span>
                    {c.is_default && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary-100 dark:bg-primary-800 text-primary-700 dark:text-primary-200">
                        {t('agents.workbenchDefaultBadge')}
                      </span>
                    )}
                    <ChevronRight className="w-3 h-3 opacity-40" />
                  </button>
                ))}
              </div>
            ))}
            {configs.length === 0 && (
              <p className="text-sm text-gray-400 dark:text-gray-500 px-2 py-4">{t('agents.workbenchEmptyConnections')}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="flex-1">
        <CardContent className="p-5 space-y-5">
          {!selectedId ? (
            <p className="text-gray-500 dark:text-gray-400 py-12 text-center">{t('agents.workbenchSelectConnection')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                    {draft.name || t('agents.workbenchUnnamed')}
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {t('agents.workbenchCredentialHint')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t('agents.workbenchDefaultModel')}</span>
                  <Switch
                    checked={draft.is_default ?? false}
                    onChange={(checked) =>
                      setDraft({ ...draft, is_default: checked })
                    }
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={testConnection}
                    isLoading={testing}
                    leftIcon={<Zap className="w-4 h-4" />}
                  >
                    {t('agents.workbenchTestConnection')}
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSave}
                    isLoading={saving}
                    leftIcon={<Save className="w-4 h-4" />}
                  >
                    {t('common.save')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(selectedId)}
                  >
                    <Trash2 className="w-4 h-4 text-red-500" />
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  label={t('agents.workbenchConfigName')}
                  value={draft.name || ''}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
                <Select
                  label={t('agents.workbenchProvider')}
                  options={providerOptions}
                  value={draft.provider || 'deepseek'}
                  onChange={(e) => {
                    const provider = e.target.value
                    const next = applyProviderDefaults(draft, provider)
                    setDraft(next)
                    setRemoteModels(PROVIDER_STATIC_MODEL_IDS[provider] || [])
                  }}
                />
                <Input
                  label={t('agents.workbenchApiKey')}
                  type="password"
                  value={draft.api_key || ''}
                  onChange={(e) =>
                    setDraft({ ...draft, api_key: e.target.value })
                  }
                  autoComplete="off"
                />
                <div>
                  <Input
                    label={t('agents.workbenchApiBaseUrl')}
                    value={draft.api_base || getDefaultBaseUrl(draft.provider || '')}
                    onChange={(e) =>
                      setDraft({ ...draft, api_base: e.target.value })
                    }
                    placeholder={getDefaultBaseUrl(draft.provider || 'deepseek')}
                  />
                  <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                    {t('agents.workbenchApiBaseSwitchHint')}
                  </p>
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <div className="flex flex-wrap items-center gap-3 mb-4">
                  <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {t('agents.workbenchAvailableModels')}
                  </h4>
                  <div className="flex-1 min-w-[160px] max-w-xs relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500"
                      placeholder={t('agents.workbenchSearchModelsPlaceholder')}
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                    />
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={fetchModels}
                    isLoading={fetchingModels}
                    leftIcon={<RefreshCw className="w-4 h-4" />}
                  >
                    {t('agents.workbenchFetchModels')}
                  </Button>
                  {draft.model && (
                    <span className="text-xs text-primary-600 dark:text-primary-400">
                      {t('agents.workbenchCurrentModel', { model: draft.model })}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2 max-h-[320px] overflow-y-auto">
                  {filteredModels.length === 0 && (
                    <p className="col-span-full text-sm text-gray-400 dark:text-gray-500 py-8 text-center">
                      {t('agents.workbenchEmptyModelsHint')}
                    </p>
                  )}
                  {filteredModels.map((modelId) => {
                    const enabled = enabledModels.has(modelId)
                    const active = draft.model === modelId
                    return (
                      <div
                        key={modelId}
                        className={cn(
                          'flex items-center justify-between gap-2 p-3 rounded-xl border text-sm transition-colors',
                          active
                            ? 'border-primary-500 bg-primary-50/50 dark:bg-primary-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-primary-300',
                        )}
                      >
                        <span
                          className="truncate font-mono text-xs text-gray-700 dark:text-gray-300"
                          title={modelId}
                        >
                          {modelId}
                        </span>
                        <div className="flex gap-1 shrink-0">
                          {enabled && (
                            <span className="text-[10px] text-green-600">{t('agents.workbenchConfigured')}</span>
                          )}
                          <Button
                            size="sm"
                            variant={active ? 'primary' : 'ghost'}
                            onClick={() => applyModel(modelId)}
                          >
                            {t('common.apply')}
                          </Button>
                          {!enabled && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => addModelAsConfig(modelId)}
                              title={t('agents.workbenchAddSameCredential')}
                            >
                              +
                            </Button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('agents.workbenchDialogNewConnection')}
        size="sm"
      >
        <div className="space-y-4">
          <Input
            label={t('common.name')}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('agents.workbenchNamePlaceholder')}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />
          <div className="flex justify-end gap-2">
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
