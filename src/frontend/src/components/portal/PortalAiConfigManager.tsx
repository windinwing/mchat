import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { portalApi, type PortalAiConfigOption } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'moonshot', label: 'Moonshot' },
  { value: 'zhipu', label: 'Zhipu' },
  { value: 'ollama', label: 'Ollama' },
]

export function PortalAiConfigManager({ onUpdated }: { onUpdated?: () => void }) {
  const { t } = useTranslation()
  const [list, setList] = useState<PortalAiConfigOption[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '',
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: '',
    api_base: '',
  })

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

  const handleCreate = async () => {
    if (!form.name.trim() || !form.api_key.trim()) {
      toast(t('portal.aiConfigFieldsRequired'), { type: 'error' })
      return
    }
    setSaving(true)
    try {
      await portalApi.createAiConfig({
        name: form.name.trim(),
        provider: form.provider,
        model: form.model.trim(),
        api_key: form.api_key.trim(),
        api_base: form.api_base.trim() || undefined,
      })
      setForm({ name: '', provider: 'openai', model: 'gpt-4o-mini', api_key: '', api_base: '' })
      reload()
      onUpdated?.()
      toast(t('portal.aiConfigCreated'), { type: 'success' })
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
    <div className="space-y-4">
      {list.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {list.map((c) => (
            <li
              key={c.id}
              className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700 text-gray-800 dark:text-gray-200"
            >
              <span>
                <span className="font-medium">{c.name}</span>
                <span className="text-gray-500 dark:text-gray-400 ml-2">
                  {c.provider}/{c.model}
                </span>
              </span>
              <span className="text-xs text-gray-400">
                {c.has_api_key ? t('portal.apiKeySet') : t('portal.apiKeyMissing')}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.noAiConfigs')}</p>
      )}

      <div className="pt-4 border-t border-gray-100 dark:border-gray-700 space-y-3">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
          {t('portal.addAiConfig')}
        </p>
        <Input
          label={t('common.name')}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="My OpenAI"
        />
        <Select
          label={t('portal.provider')}
          value={form.provider}
          onChange={(e) => setForm({ ...form, provider: e.target.value })}
          options={PROVIDERS}
        />
        <Input
          label={t('portal.model')}
          value={form.model}
          onChange={(e) => setForm({ ...form, model: e.target.value })}
        />
        <Input
          label="API Key"
          type="password"
          value={form.api_key}
          onChange={(e) => setForm({ ...form, api_key: e.target.value })}
        />
        <Input
          label={t('portal.apiBaseOptional')}
          value={form.api_base}
          onChange={(e) => setForm({ ...form, api_base: e.target.value })}
        />
        <Button onClick={handleCreate} isLoading={saving} disabled={!form.api_key.trim()}>
          {t('portal.createAiConfig')}
        </Button>
      </div>
    </div>
  )
}
