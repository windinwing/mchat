import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Plus, RefreshCw, Zap } from 'lucide-react'
import api from '@/lib/api'
import { portalApi, type PortalAiConfigOption } from '@/lib/portalApi'
import {
  applyProviderDefaults,
  getDefaultBaseUrl,
  getDefaultModel,
  normalizeModelId,
  PROVIDER_MODEL_OPTIONS,
  PROVIDER_STATIC_MODEL_IDS,
} from '@/lib/providerDefaults'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/utils'

interface AiConfigDetail {
  id: string
  name: string
  provider: string
  model: string
  api_key: string
  api_base: string | null
}

const DEFAULT_PROVIDER = 'deepseek'

function emptyForm() {
  return {
    name: '',
    api_key: '',
    ...applyProviderDefaults(
      { provider: DEFAULT_PROVIDER, api_base: '', model: '' },
      DEFAULT_PROVIDER,
    ),
  }
}

export function PortalAiConfigManager({ onUpdated }: { onUpdated?: () => void }) {
  const { t } = useTranslation()
  const [list, setList] = useState<PortalAiConfigOption[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fetchingModels, setFetchingModels] = useState(false)
  const [testing, setTesting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [remoteModels, setRemoteModels] = useState<string[]>([])
  const [form, setForm] = useState(emptyForm)

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

  const modelSelectOptions = useMemo(() => {
    const provider = form.provider || DEFAULT_PROVIDER
    const staticOpts = modelOptions[provider] || [
      { value: 'custom-model', label: t('agents.customModel') },
    ]
    const staticValues = new Set(staticOpts.map((o) => o.value))
    const extra = remoteModels
      .filter((m) => !staticValues.has(m))
      .map((m) => ({ value: m, label: m }))
    const current = form.model && !staticValues.has(form.model) && !remoteModels.includes(form.model)
      ? [{ value: form.model, label: form.model }]
      : []
    return [...staticOpts, ...extra, ...current]
  }, [form.model, form.provider, modelOptions, remoteModels, t])

  const reload = useCallback(() => {
    setLoading(true)
    portalApi
      .listAiConfigs()
      .then(setList)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    setRemoteModels(PROVIDER_STATIC_MODEL_IDS[form.provider] || [])
  }, [form.provider])

  const resetForm = () => {
    setEditingId(null)
    setForm(emptyForm())
    setRemoteModels(PROVIDER_STATIC_MODEL_IDS[DEFAULT_PROVIDER] || [])
  }

  const loadForEdit = async (id: string) => {
    try {
      const detail = await api.get<AiConfigDetail>(`/agents/ai-configs/${id}`)
      const provider = detail.provider || DEFAULT_PROVIDER
      setEditingId(id)
      setForm({
        name: detail.name,
        provider,
        model: normalizeModelId(provider, detail.model || getDefaultModel(provider)),
        api_key: detail.api_key || '',
        api_base: detail.api_base?.trim() || getDefaultBaseUrl(provider),
      })
      setRemoteModels(PROVIDER_STATIC_MODEL_IDS[provider] || [])
    } catch (err) {
      toast(err instanceof Error ? err.message : t('agents.workbenchToastLoadConfigFailed'), {
        type: 'error',
      })
    }
  }

  const handleProviderChange = (provider: string) => {
    setForm((prev) => applyProviderDefaults(prev, provider))
    setRemoteModels(PROVIDER_STATIC_MODEL_IDS[provider] || [])
  }

  const fetchModels = async () => {
    if (!form.provider) return
    setFetchingModels(true)
    try {
      const res = await api.post<{ models: string[] }>('/agents/ai-configs/models', {
        provider: form.provider,
        api_key: form.api_key || '',
        api_base: form.api_base?.trim() || getDefaultBaseUrl(form.provider) || '',
        config_id: editingId || undefined,
      })
      setRemoteModels(res.models.length ? res.models : PROVIDER_STATIC_MODEL_IDS[form.provider] || [])
      if (!res.models.length) {
        toast(t('agents.workbenchToastNoModels'), { type: 'info' })
      } else {
        toast(t('portal.aiModelsFetched', { count: res.models.length }), { type: 'success' })
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : t('agents.workbenchToastFetchModelsFailed'), {
        type: 'error',
      })
    } finally {
      setFetchingModels(false)
    }
  }

  const testConnection = async () => {
    setTesting(true)
    try {
      const res = await api.post<{ ok: boolean; message: string }>('/agents/ai-configs/test', {
        provider: form.provider,
        model: form.model,
        api_key: form.api_key || '',
        api_base: form.api_base?.trim() || getDefaultBaseUrl(form.provider) || '',
        config_id: editingId || undefined,
      })
      toast(res.message, { type: res.ok ? 'success' : 'error' })
    } catch (err) {
      toast(err instanceof Error ? err.message : t('agents.workbenchToastTestFailed'), {
        type: 'error',
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast(t('portal.aiConfigNameRequired'), { type: 'error' })
      return
    }
    if (!form.api_key.trim() && !editingId) {
      toast(t('portal.aiConfigFieldsRequired'), { type: 'error' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(),
        provider: form.provider,
        model: normalizeModelId(form.provider, form.model.trim()),
        api_base: form.api_base?.trim() || getDefaultBaseUrl(form.provider) || undefined,
        ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
      }
      if (editingId) {
        await portalApi.updateAiConfig(editingId, payload)
        toast(t('portal.aiConfigUpdated'), { type: 'success' })
      } else {
        await portalApi.createAiConfig({
          ...payload,
          api_key: form.api_key.trim(),
        })
        toast(t('portal.aiConfigCreated'), { type: 'success' })
      }
      resetForm()
      reload()
      onUpdated?.()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.aiConfigCreateFailed'), {
        type: 'error',
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner />

  return (
    <div className="space-y-5">
      {list.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {list.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => loadForEdit(c.id)}
                className={cn(
                  'w-full flex justify-between items-center py-2.5 px-3 rounded-xl border text-left transition-colors',
                  editingId === c.id
                    ? 'border-primary-400 bg-primary-50 dark:bg-primary-950/30'
                    : 'border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/40',
                )}
              >
                <span className="text-gray-800 dark:text-gray-200">
                  <span className="font-medium">{c.name}</span>
                  <span className="text-gray-500 dark:text-gray-400 ml-2">
                    {c.provider}/{c.model}
                  </span>
                </span>
                <span className="text-xs text-gray-400 shrink-0 ml-2">
                  {c.has_api_key ? t('portal.apiKeySet') : t('portal.apiKeyMissing')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.noAiConfigs')}</p>
      )}

      <div className="pt-4 border-t border-gray-100 dark:border-gray-700 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
            {editingId ? t('portal.editAiConfig') : t('portal.addAiConfig')}
          </p>
          {editingId && (
            <Button type="button" variant="ghost" size="sm" leftIcon={<Plus className="w-4 h-4" />} onClick={resetForm}>
              {t('portal.newAiConfig')}
            </Button>
          )}
        </div>

        <Input
          label={t('agents.configName')}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder={t('agents.configNamePlaceholder')}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label={t('agents.providerLabel')}
            value={form.provider}
            onChange={(e) => handleProviderChange(e.target.value)}
            options={providerOptions}
          />
          <Select
            label={t('agents.modelLabel')}
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            options={modelSelectOptions}
          />
        </div>

        <div>
          <Input
            label={t('agents.apiKeyLabel')}
            type="password"
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            placeholder={editingId ? t('portal.apiKeyKeepHint') : t('agents.apiKeyPlaceholder')}
            autoComplete="off"
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{t('agents.apiKeyHint')}</p>
        </div>

        <div>
          <Input
            label={t('agents.apiBaseLabel')}
            value={form.api_base || ''}
            onChange={(e) => setForm({ ...form, api_base: e.target.value })}
            placeholder={t('agents.apiBasePlaceholder')}
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{t('agents.apiBaseHint')}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            leftIcon={fetchingModels ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            onClick={fetchModels}
            disabled={fetchingModels}
          >
            {t('agents.workbenchFetchModels')}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            leftIcon={testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            onClick={testConnection}
            disabled={testing}
          >
            {t('agents.workbenchTestConnection')}
          </Button>
        </div>

        <div className="flex justify-end">
          <Button
            onClick={handleSave}
            isLoading={saving}
            disabled={!form.name.trim() || (!editingId && !form.api_key.trim())}
          >
            {editingId ? t('common.save') : t('portal.createAiConfig')}
          </Button>
        </div>
      </div>
    </div>
  )
}
