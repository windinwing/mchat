import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'

interface BridgeProviderSettings {
  enabled: boolean | null
  source_root: string
  extra_source_roots: string[]
  write_enabled: boolean | null
  publish_enabled: boolean | null
  data_root: string
  build_command: string
  auto_build_after_patch: boolean | null
  build_timeout_seconds: number | null
  cocos_creator_bin: string
  playables_root: string
  sync_extracted_root: string
  playable_base_url: string
  playable_base_urls: string[]
  project_allowlist: string
  bridge_group_scope_only: boolean | null
  release_keep_builds: number | null
  release_keep: number | null
}

interface CustomBridgeProviderSettings extends BridgeProviderSettings {
  key: string
  title: string
}

interface DevBridgeAdminSettings {
  gamecenter: BridgeProviderSettings
  custom_providers: CustomBridgeProviderSettings[]
}

const emptyProvider = (): BridgeProviderSettings => ({
  enabled: true,
  source_root: '',
  extra_source_roots: [],
  write_enabled: true,
  publish_enabled: true,
  data_root: '',
  build_command: '',
  auto_build_after_patch: false,
  build_timeout_seconds: 3600,
  cocos_creator_bin: '',
  playables_root: '',
  sync_extracted_root: '',
  playable_base_url: '',
  playable_base_urls: [],
  project_allowlist: '',
  bridge_group_scope_only: true,
  release_keep_builds: 10,
  release_keep: 20,
})

const emptyCustomProvider = (): CustomBridgeProviderSettings => ({
  ...emptyProvider(),
  key: '',
  title: '',
  publish_enabled: false,
})

const emptySettings = (): DevBridgeAdminSettings => ({
  gamecenter: emptyProvider(),
  custom_providers: [],
})

function ProviderFields({
  prefix,
  values,
  extraRootsText,
  playableUrlsText,
  onChange,
  onExtraRootsChange,
  onPlayableUrlsChange,
}: {
  prefix: string
  values: BridgeProviderSettings
  extraRootsText: string
  playableUrlsText: string
  onChange: (patch: Partial<BridgeProviderSettings>) => void
  onExtraRootsChange: (text: string) => void
  onPlayableUrlsChange: (text: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input label={t('devbridgeSettings.sourceRoot')} value={values.source_root} onChange={(e) => onChange({ source_root: e.target.value })} />
        <Input label={t('devbridgeSettings.cocosBin')} value={values.cocos_creator_bin} onChange={(e) => onChange({ cocos_creator_bin: e.target.value })} />
        <Input label={t('devbridgeSettings.playablesRoot')} value={values.playables_root} onChange={(e) => onChange({ playables_root: e.target.value })} />
        <Input label={t('devbridgeSettings.syncExtractedRoot')} value={values.sync_extracted_root} onChange={(e) => onChange({ sync_extracted_root: e.target.value })} />
        <Input label={t('devbridgeSettings.dataRoot')} value={values.data_root} onChange={(e) => onChange({ data_root: e.target.value })} />
        <Input label={t('devbridgeSettings.buildTimeout')} type="number" value={String(values.build_timeout_seconds ?? '')} onChange={(e) => onChange({ build_timeout_seconds: Number(e.target.value) || null })} />
      </div>
      <Input label={t('devbridgeSettings.buildCommand')} value={values.build_command} onChange={(e) => onChange({ build_command: e.target.value })} />
      <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2">{t('devbridgeSettings.buildCommandHint')}</p>
      <label className="inline-flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={values.auto_build_after_patch ?? false}
          onChange={(e) => onChange({ auto_build_after_patch: e.target.checked })}
        />
        {t('devbridgeSettings.autoBuildAfterPatch')}
      </label>
      <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2">{t('devbridgeSettings.autoBuildAfterPatchHint')}</p>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('devbridgeSettings.extraSourceRoots')}</label>
        <textarea
          id={`${prefix}-extra-roots`}
          className="w-full min-h-[72px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
          value={extraRootsText}
          onChange={(e) => onExtraRootsChange(e.target.value)}
          placeholder="/opt/xiaoxiao/gamecenter/src"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('devbridgeSettings.playableUrls')}</label>
        <textarea
          id={`${prefix}-playable-urls`}
          className="w-full min-h-[60px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
          value={playableUrlsText}
          onChange={(e) => onPlayableUrlsChange(e.target.value)}
          placeholder={'http://10.98.8.15:5099\nhttps://xyx.9235.net'}
        />
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={values.enabled ?? true} onChange={(e) => onChange({ enabled: e.target.checked })} />{t('devbridgeSettings.enabled')}</label>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={values.write_enabled ?? true} onChange={(e) => onChange({ write_enabled: e.target.checked })} />{t('devbridgeSettings.writeEnabled')}</label>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={values.publish_enabled ?? false} onChange={(e) => onChange({ publish_enabled: e.target.checked })} />{t('devbridgeSettings.publishEnabled')}</label>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={values.bridge_group_scope_only ?? true} onChange={(e) => onChange({ bridge_group_scope_only: e.target.checked })} />{t('devbridgeSettings.groupScopeOnly')}</label>
      </div>
    </div>
  )
}

export function DevBridgeSettingsPanel() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<DevBridgeAdminSettings>(emptySettings())
  const [gcExtraRootsText, setGcExtraRootsText] = useState('')
  const [gcPlayableUrlsText, setGcPlayableUrlsText] = useState('')
  const [customExtraRootsText, setCustomExtraRootsText] = useState<string[]>([])
  const [customPlayableUrlsText, setCustomPlayableUrlsText] = useState<string[]>([])

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.get<DevBridgeAdminSettings>('/devbridge/admin/settings')
      const merged: DevBridgeAdminSettings = {
        ...emptySettings(),
        ...data,
        gamecenter: { ...emptyProvider(), ...data?.gamecenter },
        custom_providers: (data?.custom_providers || []).map((item) => ({
          ...emptyCustomProvider(),
          ...item,
        })),
      }
      setForm(merged)
      setGcExtraRootsText((merged.gamecenter.extra_source_roots || []).join('\n'))
      setGcPlayableUrlsText((merged.gamecenter.playable_base_urls || []).join('\n'))
      setCustomExtraRootsText(
        merged.custom_providers.map((item) => (item.extra_source_roots || []).join('\n')),
      )
      setCustomPlayableUrlsText(
        merged.custom_providers.map((item) => (item.playable_base_urls || []).join('\n')),
      )
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridgeSettings.loadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const updateGc = (patch: Partial<BridgeProviderSettings>) => {
    setForm((prev) => ({ ...prev, gamecenter: { ...prev.gamecenter, ...patch } }))
  }

  const updateCustom = (index: number, patch: Partial<CustomBridgeProviderSettings>) => {
    setForm((prev) => ({
      ...prev,
      custom_providers: prev.custom_providers.map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    }))
  }

  const addCustomProvider = () => {
    setForm((prev) => ({
      ...prev,
      custom_providers: [...prev.custom_providers, emptyCustomProvider()],
    }))
    setCustomExtraRootsText((prev) => [...prev, ''])
    setCustomPlayableUrlsText((prev) => [...prev, ''])
  }

  const removeCustomProvider = (index: number) => {
    setForm((prev) => ({
      ...prev,
      custom_providers: prev.custom_providers.filter((_, i) => i !== index),
    }))
    setCustomExtraRootsText((prev) => prev.filter((_, i) => i !== index))
    setCustomPlayableUrlsText((prev) => prev.filter((_, i) => i !== index))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: DevBridgeAdminSettings = {
        gamecenter: {
          ...form.gamecenter,
          extra_source_roots: gcExtraRootsText.split('\n').map((s) => s.trim()).filter(Boolean),
          playable_base_urls: gcPlayableUrlsText.split('\n').map((s) => s.trim()).filter(Boolean),
        },
        custom_providers: form.custom_providers.map((item, index) => ({
          ...item,
          key: item.key.trim().toLowerCase(),
          title: item.title.trim() || item.key.trim(),
          extra_source_roots: (customExtraRootsText[index] || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
          playable_base_urls: (customPlayableUrlsText[index] || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
        })),
      }
      await api.put('/devbridge/admin/settings', payload)
      toast(t('devbridgeSettings.saved'), { type: 'success' })
      await load()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridgeSettings.saveFailed'), { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>{t('devbridgeSettings.gamecenterTitle')}</CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('devbridgeSettings.gamecenterHint')}</p>
          <ProviderFields
            prefix="gc"
            values={form.gamecenter}
            extraRootsText={gcExtraRootsText}
            playableUrlsText={gcPlayableUrlsText}
            onChange={updateGc}
            onExtraRootsChange={setGcExtraRootsText}
            onPlayableUrlsChange={setGcPlayableUrlsText}
          />
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('devbridgeSettings.customProvidersTitle')}</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('devbridgeSettings.customProvidersHint')}</p>
          </div>
          <Button variant="outline" leftIcon={<Plus className="w-4 h-4" />} onClick={addCustomProvider}>
            {t('devbridgeSettings.addCustomProvider')}
          </Button>
        </div>

        {form.custom_providers.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-sm text-gray-500 dark:text-gray-400 text-center">
              {t('devbridgeSettings.noCustomProviders')}
            </CardContent>
          </Card>
        ) : (
          form.custom_providers.map((provider, index) => (
            <Card key={`custom-provider-${index}`}>
              <CardHeader className="flex flex-row items-center justify-between gap-3">
                <span>{provider.title || provider.key || t('devbridgeSettings.customProviderFallback', { index: index + 1 })}</span>
                <Button variant="ghost" size="sm" leftIcon={<Trash2 className="w-4 h-4" />} onClick={() => removeCustomProvider(index)}>
                  {t('common.delete')}
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label={t('devbridgeSettings.providerKey')}
                    value={provider.key}
                    onChange={(e) => updateCustom(index, { key: e.target.value })}
                    placeholder="my-repo"
                  />
                  <Input
                    label={t('devbridgeSettings.providerTitle')}
                    value={provider.title}
                    onChange={(e) => updateCustom(index, { title: e.target.value })}
                    placeholder="My Repo"
                  />
                </div>
                <ProviderFields
                  prefix={`custom-${index}`}
                  values={provider}
                  extraRootsText={customExtraRootsText[index] || ''}
                  playableUrlsText={customPlayableUrlsText[index] || ''}
                  onChange={(patch) => updateCustom(index, patch)}
                  onExtraRootsChange={(text) =>
                    setCustomExtraRootsText((prev) => prev.map((item, i) => (i === index ? text : item)))
                  }
                  onPlayableUrlsChange={(text) =>
                    setCustomPlayableUrlsText((prev) => prev.map((item, i) => (i === index ? text : item)))
                  }
                />
              </CardContent>
            </Card>
          ))
        )}
      </div>

      <div className="flex justify-end">
        <Button isLoading={saving} onClick={() => void handleSave()}>{t('common.save')}</Button>
      </div>
    </div>
  )
}
