import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Save } from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Switch } from '@/components/ui/Switch'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { Select } from '@/components/ui/Select'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

interface AppSettings {
  site_name: string
  site_description: string
  language: string
  timezone: string
  max_file_size: number
  allowed_file_types: string[]
  enable_websocket: boolean
  enable_streaming: boolean
  rate_limit_per_min: number
  maintenance_mode: boolean
  server_ops_skills_enabled: boolean
  server_ops_skill_allowlist: string[]
  server_ops_shell_allowlist: { id: string; command: string }[]
  storage_backend: 'local' | 's3' | 'minio'
  upload_dir: string
  max_upload_size_mb: number
  s3_endpoint: string
  s3_region: string
  s3_access_key: string
  s3_secret_key: string
  s3_bucket: string
  s3_use_ssl: boolean
  s3_public_base_url: string
  s3_force_path_style: boolean
  worker_enabled: boolean
  worker_timezone: string
  worker_log_cleanup_enabled: boolean
  worker_log_retention_days: number
  worker_usage_reset_enabled: boolean
}

interface AppLogResponse {
  source: string
  lines: string[]
}

function shellAllowlistEntriesToText(
  entries: { id: string; command: string }[]
): string {
  return (entries || [])
    .map((e) => `${e.id} | ${e.command}`)
    .join('\n')
}

function textToShellAllowlistEntries(text: string): { id: string; command: string }[] {
  const out: { id: string; command: string }[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const pipe = line.indexOf('|')
    if (pipe < 0) continue
    const id = line.slice(0, pipe).trim()
    const command = line.slice(pipe + 1).trim()
    if (id && command) out.push({ id, command })
  }
  return out
}

export function SettingsPage() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<AppSettings>({
    site_name: 'MChat',
    site_description: '',
    language: 'zh-CN',
    timezone: 'Asia/Shanghai',
    max_file_size: 10,
    allowed_file_types: ['txt', 'pdf', 'doc', 'docx', 'md'],
    enable_websocket: true,
    enable_streaming: true,
    rate_limit_per_min: 60,
    maintenance_mode: false,
    server_ops_skills_enabled: false,
    server_ops_skill_allowlist: [],
    server_ops_shell_allowlist: [],
    storage_backend: 'local',
    upload_dir: '../../uploads',
    max_upload_size_mb: 50,
    s3_endpoint: '',
    s3_region: '',
    s3_access_key: '',
    s3_secret_key: '',
    s3_bucket: 'mchat-uploads',
    s3_use_ssl: false,
    s3_public_base_url: '',
    s3_force_path_style: true,
    worker_enabled: false,
    worker_timezone: 'Asia/Shanghai',
    worker_log_cleanup_enabled: true,
    worker_log_retention_days: 14,
    worker_usage_reset_enabled: true,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('general')
  const [logSource, setLogSource] = useState<'app' | 'error'>('app')
  const [logLines, setLogLines] = useState<string[]>([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [shellAllowlistText, setShellAllowlistText] = useState('')

  useEffect(() => {
    loadSettings()
  }, [])

  useEffect(() => {
    if (activeTab === 'logs') {
      loadLogs(logSource)
    }
  }, [activeTab, logSource])

  const loadSettings = async () => {
    try {
      const data = await api.get<AppSettings>('/settings')
      if (data) {
        setSettings(data)
        setShellAllowlistText(
          shellAllowlistEntriesToText(data.server_ops_shell_allowlist || [])
        )
      }
    } catch (err) {
      console.error('Failed to load settings:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put('/settings', settings)
      toast(t('settings.toastSaved'), { type: 'success' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('settings.toastSaveFailed')
      toast(message, { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const loadLogs = async (source: 'app' | 'error') => {
    setLogsLoading(true)
    try {
      const data = await api.get<AppLogResponse>(`/settings/logs?source=${source}&lines=300`)
      setLogLines(data.lines || [])
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('settings.toastLoadLogsFailed')
      toast(message, { type: 'error' })
      setLogLines([])
    } finally {
      setLogsLoading(false)
    }
  }

  const tabs = [
    { id: 'general', label: t('settings.tabGeneral') },
    { id: 'upload', label: t('settings.tabUpload') },
    { id: 'storage', label: t('settings.tabStorage') },
    { id: 'api', label: t('settings.tabApi') },
    { id: 'security', label: t('settings.tabSecurity') },
    { id: 'worker', label: t('settings.tabWorker') },
    { id: 'logs', label: t('settings.tabLogs') },
  ]

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('settings.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('settings.pageSubtitle')}
          </p>
        </div>
        <Button
          leftIcon={<Save className="w-4 h-4" />}
          onClick={handleSave}
          isLoading={saving}
        >
          {t('common.save')}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
        </CardHeader>
        <CardContent>
          <TabPanel id="general" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label={t('settings.siteName')}
                  value={settings.site_name}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setSettings({ ...settings, site_name: e.target.value })
                  }
                />
                <Select
                  label={t('settings.siteLanguage')}
                  options={[
                    { value: 'zh-CN', label: t('settings.langZh') },
                    { value: 'en-US', label: t('settings.langEn') },
                  ]}
                  value={settings.language}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                    setSettings({ ...settings, language: e.target.value })
                  }
                />
              </div>
              <Textarea
                label={t('settings.siteDescription')}
                value={settings.site_description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setSettings({ ...settings, site_description: e.target.value })
                }
                rows={3}
              />
              <Select
                label={t('settings.timezone')}
                options={[
                  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (UTC+8)' },
                  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (UTC+9)' },
                  { value: 'America/New_York', label: 'America/New_York (UTC-5)' },
                  { value: 'Europe/London', label: 'Europe/London (UTC+0)' },
                ]}
                value={settings.timezone}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setSettings({ ...settings, timezone: e.target.value })
                }
              />
            </div>
          </TabPanel>

          <TabPanel id="upload" activeTab={activeTab}>
            <div className="space-y-4">
              <Input
                label={t('settings.maxFileSize')}
                type="number"
                min={1}
                max={100}
                value={settings.max_file_size}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({
                    ...settings,
                    max_file_size: parseInt(e.target.value, 10),
                  })
                }
              />
              <Input
                label={t('settings.maxUploadSize')}
                type="number"
                min={1}
                max={2048}
                value={settings.max_upload_size_mb}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({
                    ...settings,
                    max_upload_size_mb: parseInt(e.target.value, 10),
                  })
                }
              />
              <Input
                label={t('settings.allowedFileTypes')}
                value={settings.allowed_file_types.join(', ')}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({
                    ...settings,
                    allowed_file_types: e.target.value
                      .split(',')
                      .map((s: string) => s.trim()),
                  })
                }
                placeholder={t('settings.allowedFileTypesPlaceholder')}
              />
            </div>
          </TabPanel>

          <TabPanel id="storage" activeTab={activeTab}>
            <div className="space-y-4">
              <Select
                label={t('settings.storageBackend')}
                value={settings.storage_backend}
                options={[
                  { value: 'local', label: t('settings.storageLocal') },
                  { value: 's3', label: t('settings.storageS3') },
                  { value: 'minio', label: t('settings.storageMinio') },
                ]}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setSettings({
                    ...settings,
                    storage_backend: e.target.value as AppSettings['storage_backend'],
                  })
                }
              />

              <Input
                label={t('settings.uploadDir')}
                value={settings.upload_dir}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({ ...settings, upload_dir: e.target.value })
                }
                placeholder="../../uploads"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2">
                {t('settings.uploadDirHint')}
              </p>

              {settings.storage_backend !== 'local' && (
                <>
                  <Input
                    label={t('settings.s3Endpoint')}
                    value={settings.s3_endpoint}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setSettings({ ...settings, s3_endpoint: e.target.value })
                    }
                    placeholder="https://s3.amazonaws.com or minio:9000"
                  />
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label={t('settings.s3Region')}
                      value={settings.s3_region}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setSettings({ ...settings, s3_region: e.target.value })
                      }
                      placeholder="us-east-1"
                    />
                    <Input
                      label={t('settings.s3Bucket')}
                      value={settings.s3_bucket}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setSettings({ ...settings, s3_bucket: e.target.value })
                      }
                      placeholder="mchat-uploads"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label={t('settings.s3AccessKey')}
                      value={settings.s3_access_key}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setSettings({ ...settings, s3_access_key: e.target.value })
                      }
                    />
                    <Input
                      label={t('settings.s3SecretKey')}
                      type="password"
                      value={settings.s3_secret_key}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setSettings({ ...settings, s3_secret_key: e.target.value })
                      }
                      autoComplete="off"
                    />
                  </div>
                  <Input
                    label={t('settings.s3PublicBaseUrl')}
                    value={settings.s3_public_base_url}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setSettings({ ...settings, s3_public_base_url: e.target.value })
                    }
                    placeholder="https://cdn.example.com/mchat"
                  />
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {t('settings.s3UseSsl')}
                      </p>
                    </div>
                    <Switch
                      checked={settings.s3_use_ssl}
                      onChange={(checked) =>
                        setSettings({ ...settings, s3_use_ssl: checked })
                      }
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {t('settings.s3ForcePathStyle')}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {t('settings.s3ForcePathStyleHint')}
                      </p>
                    </div>
                    <Switch
                      checked={settings.s3_force_path_style}
                      onChange={(checked) =>
                        setSettings({ ...settings, s3_force_path_style: checked })
                      }
                    />
                  </div>
                </>
              )}
            </div>
          </TabPanel>

          <TabPanel id="api" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.enableWebsocket')}
                  </p>
                  <p className="text-xs text-gray-500">
                    {t('settings.enableWebsocketHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.enable_websocket}
                  onChange={(checked) =>
                    setSettings({ ...settings, enable_websocket: checked })
                  }
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.enableStreaming')}
                  </p>
                  <p className="text-xs text-gray-500">
                    {t('settings.enableStreamingHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.enable_streaming}
                  onChange={(checked) =>
                    setSettings({ ...settings, enable_streaming: checked })
                  }
                />
              </div>
              <Input
                label={t('settings.rateLimit')}
                type="number"
                min={1}
                max={1000}
                value={settings.rate_limit_per_min}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({
                    ...settings,
                    rate_limit_per_min: parseInt(e.target.value, 10),
                  })
                }
              />
            </div>
          </TabPanel>

          <TabPanel id="security" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.maintenanceMode')}
                  </p>
                  <p className="text-xs text-gray-500">
                    {t('settings.maintenanceModeHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.maintenance_mode}
                  onChange={(checked) =>
                    setSettings({ ...settings, maintenance_mode: checked })
                  }
                />
              </div>
              <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-4">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.serverOpsSkills')}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('settings.serverOpsSkillsHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.server_ops_skills_enabled}
                  onChange={(checked) =>
                    setSettings({ ...settings, server_ops_skills_enabled: checked })
                  }
                />
              </div>
              {settings.server_ops_skills_enabled && (
                <Input
                  label={t('settings.serverOpsAllowlist')}
                  value={(settings.server_ops_skill_allowlist || []).join(', ')}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setSettings({
                      ...settings,
                      server_ops_skill_allowlist: e.target.value
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder={t('settings.serverOpsAllowlistPlaceholder')}
                />
              )}
              {settings.server_ops_skills_enabled && (
                <Textarea
                  label={t('settings.serverOpsShellAllowlist')}
                  value={shellAllowlistText}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                    const text = e.target.value
                    setShellAllowlistText(text)
                    setSettings({
                      ...settings,
                      server_ops_shell_allowlist: textToShellAllowlistEntries(text),
                    })
                  }}
                  rows={6}
                  placeholder={t('settings.serverOpsShellAllowlistPlaceholder')}
                />
              )}
            </div>
          </TabPanel>

          <TabPanel id="logs" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="w-48">
                  <Select
                    value={logSource}
                    options={[
                      { value: 'app', label: t('settings.logSourceApp') },
                      { value: 'error', label: t('settings.logSourceError') },
                    ]}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                      setLogSource(e.target.value as 'app' | 'error')
                    }
                  />
                </div>
                <Button
                  variant="secondary"
                  leftIcon={<RefreshCw className="w-4 h-4" />}
                  onClick={() => loadLogs(logSource)}
                  isLoading={logsLoading}
                >
                  {t('settings.refreshLogs')}
                </Button>
              </div>
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3">
                <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap max-h-[420px] overflow-y-auto">
                  {logsLoading
                    ? t('common.loading')
                    : logLines.length > 0
                      ? logLines.join('\n')
                      : t('settings.emptyLogs')}
                </pre>
              </div>
            </div>
          </TabPanel>

          <TabPanel id="worker" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.workerEnabled')}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('settings.workerEnabledHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.worker_enabled}
                  onChange={(checked) =>
                    setSettings({ ...settings, worker_enabled: checked })
                  }
                />
              </div>

              <Input
                label={t('settings.workerTimezone')}
                value={settings.worker_timezone}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({ ...settings, worker_timezone: e.target.value })
                }
                placeholder="Asia/Shanghai"
              />

              <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-4">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.workerUsageResetEnabled')}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('settings.workerUsageResetEnabledHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.worker_usage_reset_enabled}
                  onChange={(checked) =>
                    setSettings({ ...settings, worker_usage_reset_enabled: checked })
                  }
                />
              </div>

              <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-4">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t('settings.workerLogCleanupEnabled')}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('settings.workerLogCleanupEnabledHint')}
                  </p>
                </div>
                <Switch
                  checked={settings.worker_log_cleanup_enabled}
                  onChange={(checked) =>
                    setSettings({ ...settings, worker_log_cleanup_enabled: checked })
                  }
                />
              </div>

              <Input
                label={t('settings.workerLogRetentionDays')}
                type="number"
                min={1}
                max={3650}
                value={settings.worker_log_retention_days}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setSettings({
                    ...settings,
                    worker_log_retention_days: parseInt(e.target.value, 10) || 14,
                  })
                }
              />
            </div>
          </TabPanel>
        </CardContent>
      </Card>
    </div>
  )
}
