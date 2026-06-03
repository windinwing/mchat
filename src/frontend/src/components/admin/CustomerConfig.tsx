import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Palette,
  Globe,
  MessageSquare,
  MessageCircle,
  Save,
  Smartphone,
  Plus,
  Code,
  Copy,
  Bot,
  Headphones,
  Sparkles,
  BookOpen,
  Paperclip,
  Trash2,
} from 'lucide-react'
import i18n from '@/i18n'
import api from '@/lib/api'
import { tenantSelectableSkills } from '@/lib/skillUtils'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import { Select } from '@/components/ui/Select'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

interface SkillOption {
  id: string
  name: string
  description: string | null
  skill_type: string
  enabled: boolean
  config?: Record<string, unknown> | null
}

interface KnowledgeBaseOption {
  id: string
  name: string
}

interface AutoReplyAsset {
  url: string
  name?: string
  title?: string
  mime?: string
  type?: string
}

interface AutoReplyRule {
  id: string
  name: string
  enabled: boolean
  trigger_text: string
  keywords: string[]
  keywords_text: string
  channels: string[]
  reply_text: string | null
  threshold: number
  asset: AutoReplyAsset
}

const AUTO_REPLY_CHANNEL_VALUES = ['widget', 'wechat', 'admin'] as const

interface CustomerServiceConfig {
  id: string
  name: string
  short_code: string | null
  user_id?: string
  ai_config_id: string | null
  skill_ids: string[]
  knowledge_base_ids: string[]
  auto_reply_rules: AutoReplyRule[]
  channel_prompt: string | null
  welcome_message: string | null
  offline_message: string | null
  theme: {
    primaryColor?: string
    buttonColor?: string
    botName?: string
    widgetTitle?: string
    launcherIcon?: string
    launcherText?: string
    showcaseSkillIds?: string[]
    showBranding?: boolean
  } | null
  domains: string | null
  position: string
  enabled: boolean
  widget_session_ttl_hours?: number
  workspace_mode?: string | null
  workspace_container_allowed?: boolean | null
  created_at?: string
  updated_at?: string
}

interface UploadedAssetResponse {
  url: string
  name: string
  mime: string
  size: number
  type: string
}

function normalizeAutoReplyRule(
  rule: Partial<AutoReplyRule> | null | undefined,
  index = 0,
): AutoReplyRule {
  return {
    id: String(rule?.id || `rule-${Date.now()}-${index}`),
    name: String(rule?.name || ''),
    enabled: rule?.enabled !== false,
    trigger_text: String(rule?.trigger_text || ''),
    keywords: Array.isArray(rule?.keywords) ? rule.keywords.filter(Boolean).map(String) : [],
    keywords_text: Array.isArray(rule?.keywords)
      ? rule.keywords.filter(Boolean).map(String).join(', ')
      : '',
    channels: Array.isArray(rule?.channels)
      ? rule.channels
          .filter((channel): channel is string => typeof channel === 'string')
          .map((channel) => channel.trim().toLowerCase())
          .filter((channel, index, all) => AUTO_REPLY_CHANNEL_VALUES.includes(channel as (typeof AUTO_REPLY_CHANNEL_VALUES)[number]) && all.indexOf(channel) === index)
      : [],
    reply_text: rule?.reply_text ? String(rule.reply_text) : null,
    threshold: typeof rule?.threshold === 'number' ? rule.threshold : 0.78,
    asset: {
      url: String(rule?.asset?.url || ''),
      name: rule?.asset?.name ? String(rule.asset.name) : undefined,
      title: rule?.asset?.title ? String(rule.asset.title) : undefined,
      mime: rule?.asset?.mime ? String(rule.asset.mime) : undefined,
      type: rule?.asset?.type ? String(rule.asset.type) : undefined,
    },
  }
}

function normalizeCustomerConfig(
  raw?: Partial<CustomerServiceConfig> | null,
): CustomerServiceConfig {
  const theme = raw?.theme || {}
  return {
    id: String(raw?.id || ''),
    name: String(raw?.name || i18n.t('customerAgents.defaultConfigName')),
    short_code: raw?.short_code || null,
    user_id: raw?.user_id,
    ai_config_id: raw?.ai_config_id || null,
    skill_ids: Array.isArray(raw?.skill_ids) ? raw.skill_ids.filter(Boolean).map(String) : [],
    knowledge_base_ids: Array.isArray(raw?.knowledge_base_ids) ? raw.knowledge_base_ids.filter(Boolean).map(String) : [],
    auto_reply_rules: Array.isArray(raw?.auto_reply_rules)
      ? raw.auto_reply_rules.map((rule, index) => normalizeAutoReplyRule(rule, index))
      : [],
    channel_prompt: raw?.channel_prompt || null,
    welcome_message: raw?.welcome_message || null,
    offline_message: raw?.offline_message || null,
    theme: {
      primaryColor: String(theme.primaryColor || '#3b82f6'),
      buttonColor: theme.buttonColor ? String(theme.buttonColor) : undefined,
      botName: String(theme.botName || i18n.t('customerAgents.defaultBotName')),
      widgetTitle: String(theme.widgetTitle || i18n.t('customerAgents.defaultWidgetTitle')),
      launcherIcon: theme.launcherIcon ? String(theme.launcherIcon) : 'chat',
      launcherText: theme.launcherText ? String(theme.launcherText) : '',
      showcaseSkillIds: Array.isArray(theme.showcaseSkillIds)
        ? theme.showcaseSkillIds.filter(Boolean).map(String)
        : [],
      showBranding: typeof theme.showBranding === 'boolean' ? theme.showBranding : true,
    },
    domains: raw?.domains || null,
    position: String(raw?.position || 'right'),
    enabled: raw?.enabled ?? true,
    widget_session_ttl_hours: raw?.widget_session_ttl_hours ?? 24,
    workspace_mode: raw?.workspace_mode ?? null,
    workspace_container_allowed: raw?.workspace_container_allowed ?? null,
    created_at: raw?.created_at,
    updated_at: raw?.updated_at,
  }
}

function emptyCustomerConfig(): CustomerServiceConfig {
  return normalizeCustomerConfig({
    welcome_message: i18n.t('customerAgents.defaultWelcome'),
    offline_message: i18n.t('customerAgents.defaultOffline'),
  })
}

export function CustomerConfig() {
  const { t } = useTranslation()
  const [configs, setConfigs] = useState<CustomerServiceConfig[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [config, setConfig] = useState<CustomerServiceConfig>(() => emptyCustomerConfig())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [widgetSessionTtlInput, setWidgetSessionTtlInput] = useState('24')
  const [uploadingRuleId, setUploadingRuleId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('capabilities')
  const [domainInput, setDomainInput] = useState('')
  const [aiConfigs, setAiConfigs] = useState<{ id: string; name: string }[]>([])
  const [skills, setSkills] = useState<SkillOption[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseOption[]>([])
  const assetFileInputRef = React.useRef<HTMLInputElement | null>(null)

  const skillTypeLabel = (skillType: string) =>
    skillType === 'builtin' ? t('skills.builtin') : t('skills.custom')

  const tabs = useMemo(
    () => [
      { id: 'capabilities', label: t('customerAgents.tabCapabilities'), icon: <Bot className="w-4 h-4" /> },
      { id: 'widget', label: t('customerAgents.tabWidget'), icon: <Palette className="w-4 h-4" /> },
      { id: 'domain', label: t('customerAgents.tabDomain'), icon: <Globe className="w-4 h-4" /> },
      { id: 'message', label: t('customerAgents.tabMessage'), icon: <MessageSquare className="w-4 h-4" /> },
      { id: 'embed', label: t('customerAgents.tabEmbed'), icon: <Code className="w-4 h-4" /> },
    ],
    [t],
  )

  const autoReplyChannelOptions = useMemo(
    () => [
      { value: 'widget', label: t('customerAgents.autoReplyChannelWidget') },
      { value: 'wechat', label: t('customerAgents.autoReplyChannelWechat') },
      { value: 'admin', label: t('customerAgents.autoReplyChannelAdmin') },
    ],
    [t],
  )

  useEffect(() => {
    loadConfigs()
    loadAiConfigs()
    loadSkills()
    loadKnowledgeBases()
  }, [])

  useEffect(() => {
    setWidgetSessionTtlInput(String(config.widget_session_ttl_hours ?? 24))
  }, [config.id, config.widget_session_ttl_hours])

  const loadAiConfigs = async () => {
    try {
      const data = await api.get<{ id: string; name: string }[]>('/agents/ai-configs')
      setAiConfigs(data.map((c) => ({ id: c.id, name: c.name })))
    } catch {
      /* optional */
    }
  }

  const loadSkills = async () => {
    try {
      const data = await api.get<SkillOption[]>('/skills')
      setSkills(tenantSelectableSkills(data.filter((s) => s.enabled)))
    } catch {
      /* optional */
    }
  }

  const loadKnowledgeBases = async () => {
    try {
      const data = await api.get<KnowledgeBaseOption[]>('/knowledge/bases')
      setKnowledgeBases(data)
    } catch {
      /* optional */
    }
  }

  const selectedSkillIds = config.skill_ids ?? []
  const selectedKbIds = config.knowledge_base_ids ?? []
  const showcaseSkillIds = Array.isArray(config.theme?.showcaseSkillIds)
    ? config.theme?.showcaseSkillIds || []
    : []

  const toggleSkill = (skillId: string) => {
    const current = [...selectedSkillIds]
    const next = current.includes(skillId)
      ? current.filter((id) => id !== skillId)
      : [...current, skillId]
    setConfig({ ...config, skill_ids: next })
  }

  const toggleKnowledgeBase = (kbId: string) => {
    const current = [...selectedKbIds]
    const next = current.includes(kbId)
      ? current.filter((id) => id !== kbId)
      : [...current, kbId]
    setConfig({ ...config, knowledge_base_ids: next })
  }

  const toggleShowcaseSkill = (skillId: string) => {
    const next = showcaseSkillIds.includes(skillId)
      ? showcaseSkillIds.filter((id) => id !== skillId)
      : [...showcaseSkillIds, skillId]
    updateTheme('showcaseSkillIds', next)
  }

  const loadConfigs = async () => {
    try {
      const data = await api.get<CustomerServiceConfig[]>('/agents/customer-configs')
      const normalized = data.map((item) => normalizeCustomerConfig(item))
      setConfigs(normalized)
      if (normalized.length > 0) {
        setSelectedId(normalized[0].id)
        setConfig(normalized[0])
      }
    } catch (err) {
      console.error('Failed to load configs:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = (id: string) => {
    setSelectedId(id)
    const found = configs.find((c) => c.id === id)
    if (found) setConfig(normalizeCustomerConfig(found))
  }

  const handleCreate = async () => {
    try {
      const created = await api.post<CustomerServiceConfig>('/agents/customer-configs', {
        name: t('customerAgents.newConfigName'),
        position: 'right',
        enabled: true,
      })
      const normalized = normalizeCustomerConfig(created)
      setConfigs((prev) => [...prev, normalized])
      setSelectedId(normalized.id)
      setConfig(normalized)
      toast(t('customerAgents.toastCreated'), { type: 'success' })
    } catch (err: any) {
      toast(t('customerAgents.toastCreateFailed'), { type: 'error', message: err.message })
    }
  }

  const handleSave = async () => {
    const autoReplyRulesPayload = config.auto_reply_rules.map(({ keywords_text, ...rule }) => ({
      ...rule,
      keywords: keywords_text
        .split(/,|，/)
        .map((item) => item.trim())
        .filter(Boolean),
    }))

    if (!selectedId) {
      try {
        const created = await api.post<CustomerServiceConfig>('/agents/customer-configs', {
          name: config.name,
          short_code: config.short_code || undefined,
          ai_config_id: config.ai_config_id,
          skill_ids: config.skill_ids,
          knowledge_base_ids: config.knowledge_base_ids,
          auto_reply_rules: autoReplyRulesPayload,
          channel_prompt: config.channel_prompt || null,
          welcome_message: config.welcome_message,
          offline_message: config.offline_message,
          theme: config.theme,
          domains: config.domains,
          position: config.position,
          enabled: config.enabled,
          widget_session_ttl_hours: config.widget_session_ttl_hours ?? 24,
          workspace_mode: config.workspace_mode || null,
        })
        const normalized = normalizeCustomerConfig(created)
        setConfigs((prev) => [...prev, normalized])
        setSelectedId(normalized.id)
        setConfig(normalized)
        toast(t('customerAgents.toastSaveSuccess'), { type: 'success' })
      } catch (err: any) {
        toast(t('customerAgents.toastSaveFailed'), { type: 'error', message: err.message })
      }
      return
    }

    setSaving(true)
    try {
      const updated = await api.put<CustomerServiceConfig>(`/agents/customer-configs/${selectedId}`, {
        name: config.name,
        short_code: config.short_code || undefined,
        ai_config_id: config.ai_config_id,
        skill_ids: config.skill_ids,
        knowledge_base_ids: config.knowledge_base_ids,
        auto_reply_rules: autoReplyRulesPayload,
        channel_prompt: config.channel_prompt || null,
        welcome_message: config.welcome_message,
        offline_message: config.offline_message,
        theme: config.theme,
        domains: config.domains,
        position: config.position,
        enabled: config.enabled,
        widget_session_ttl_hours: config.widget_session_ttl_hours ?? 24,
        workspace_mode: config.workspace_mode || null,
      })
      const normalized = normalizeCustomerConfig(updated)
      setConfig(normalized)
      setConfigs((prev) => prev.map((item) => (item.id === normalized.id ? normalized : item)))
      toast(t('customerAgents.toastSaveSuccess'), { type: 'success' })
    } catch (err: any) {
      toast(t('customerAgents.toastSaveFailed'), { type: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  const updateTheme = (key: string, value: any) => {
    setConfig({
      ...config,
      theme: { ...(config.theme || {}), [key]: value },
    })
  }

  const toggleRuleEnabled = (ruleId: string) => {
    setConfig({
      ...config,
      auto_reply_rules: config.auto_reply_rules.map((rule) =>
        rule.id === ruleId ? { ...rule, enabled: !rule.enabled } : rule,
      ),
    })
  }

  const updateAutoReplyRule = (ruleId: string, patch: Partial<AutoReplyRule>) => {
    setConfig({
      ...config,
      auto_reply_rules: config.auto_reply_rules.map((rule) =>
        rule.id === ruleId ? { ...rule, ...patch } : rule,
      ),
    })
  }

  const toggleAutoReplyRuleChannel = (ruleId: string, channel: (typeof AUTO_REPLY_CHANNEL_VALUES)[number]) => {
    setConfig({
      ...config,
      auto_reply_rules: config.auto_reply_rules.map((rule) => {
        if (rule.id !== ruleId) return rule
        const channels = rule.channels.includes(channel)
          ? rule.channels.filter((item) => item !== channel)
          : [...rule.channels, channel]
        return { ...rule, channels }
      }),
    })
  }

  const updateAutoReplyRuleAsset = (ruleId: string, patch: Partial<AutoReplyAsset>) => {
    setConfig({
      ...config,
      auto_reply_rules: config.auto_reply_rules.map((rule) =>
        rule.id === ruleId
          ? { ...rule, asset: { ...rule.asset, ...patch } }
          : rule,
      ),
    })
  }

  const addAutoReplyRule = () => {
    setConfig({
      ...config,
      auto_reply_rules: [
        ...config.auto_reply_rules,
        normalizeAutoReplyRule(
          {
            id: `rule-${Date.now()}-${config.auto_reply_rules.length}`,
            name: t('customerAgents.autoReplyDefaultRuleName', {
              count: config.auto_reply_rules.length + 1,
            }),
          },
          config.auto_reply_rules.length,
        ),
      ],
    })
  }

  const removeAutoReplyRule = (ruleId: string) => {
    setConfig({
      ...config,
      auto_reply_rules: config.auto_reply_rules.filter((rule) => rule.id !== ruleId),
    })
  }

  const triggerRuleAssetUpload = (ruleId: string) => {
    setUploadingRuleId(ruleId)
    assetFileInputRef.current?.click()
  }

  const handleRuleAssetUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !uploadingRuleId) return

    const formData = new FormData()
    formData.append('file', file)
    try {
      const uploaded = await api.upload<UploadedAssetResponse>('/agents/customer-configs/upload-asset', formData)
      updateAutoReplyRuleAsset(uploadingRuleId, {
        url: uploaded.url,
        name: uploaded.name,
        title: uploaded.name,
        mime: uploaded.mime,
        type: uploaded.type,
      })
      toast(t('customerAgents.toastAssetUploadSuccess'), { type: 'success' })
    } catch (err: any) {
      toast(t('customerAgents.toastAssetUploadFailed'), { type: 'error', message: err.message })
    } finally {
      setUploadingRuleId(null)
      if (assetFileInputRef.current) assetFileInputRef.current.value = ''
    }
  }

  const addDomain = () => {
    const domain = domainInput.trim().toLowerCase()
    if (!domain) return
    const current = config.domains ? config.domains.split(',').map((d) => d.trim()).filter(Boolean) : []
    if (!current.includes(domain)) {
      current.push(domain)
      setConfig({ ...config, domains: current.join(',') })
    }
    setDomainInput('')
  }

  const removeDomain = (domain: string) => {
    const current = config.domains ? config.domains.split(',').map((d) => d.trim()).filter(Boolean) : []
    setConfig({ ...config, domains: current.filter((d) => d !== domain).join(',') })
  }

  const theme = config.theme || {}
  const domainList = config.domains ? config.domains.split(',').map((d) => d.trim()).filter(Boolean) : []
  const primaryColor = theme.primaryColor || '#3b82f6'
  const previewLauncherIcon =
    theme.launcherIcon === 'bot'
      ? Bot
      : theme.launcherIcon === 'spark'
        ? Sparkles
        : theme.launcherIcon === 'support'
          ? Headphones
          : MessageCircle

  const apiBase =
    typeof window !== 'undefined'
      ? `${window.location.origin}/api`
      : 'https://your-domain.com/api'
  const widgetOrigin =
    typeof window !== 'undefined' ? window.location.origin : 'https://your-domain.com'

  const defaultBot = i18n.t('customerAgents.defaultBotName')

  const embedScript = selectedId
    ? `<!-- MChat Widget -->
<script
  src="${widgetOrigin}/widget-loader.js"
  data-mchat-url="${apiBase}"
  data-agent-id="${selectedId}"
  data-position="${config.position}"
  data-primary-color="${primaryColor}"
  data-welcome-message="${(config.welcome_message || '').replace(/"/g, '&quot;')}"
  data-bot-name="${theme.botName || defaultBot}"
  data-launcher-icon="${theme.launcherIcon || 'chat'}"
  data-launcher-text="${(theme.launcherText || '').replace(/"/g, '&quot;')}"
></script>`
    : ''

  const copyEmbedCode = async () => {
    if (!embedScript) return
    try {
      await navigator.clipboard.writeText(embedScript)
      toast(t('customerAgents.toastCopySuccess'), { type: 'success' })
    } catch {
      toast(t('customerAgents.toastCopyFailed'), { type: 'error' })
    }
  }

  const previewPositionLabel =
    config.position === 'right'
      ? t('customerAgents.positionBottomRight')
      : t('customerAgents.positionBottomLeft')

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="md" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <input
        ref={assetFileInputRef}
        type="file"
        accept="image/*,video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm,.pdf,.doc,.docx,.txt,.md"
        className="hidden"
        title={t('customerAgents.autoReplyUploadAsset')}
        onChange={handleRuleAssetUpload}
      />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Select
            label=""
            options={configs.map((c) => ({ value: c.id, label: c.name }))}
            value={selectedId || ''}
            onChange={(e: any) => handleSelect(e.target.value)}
            className="w-52"
          />
          <Button size="action" variant="ghost" leftIcon={<Plus className="w-4 h-4" />} onClick={handleCreate}>
            {t('customerAgents.new')}
          </Button>
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
          <div className="flex items-center gap-2 mb-2">
            <Input
              label=""
              value={config.name}
              onChange={(e: any) => setConfig({ ...config, name: e.target.value })}
              placeholder={t('customerAgents.configNamePlaceholder')}
              className="w-48"
            />
            <Input
              label=""
              value={config.short_code || ''}
              onChange={(e: any) => {
                const v = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '')
                setConfig({ ...config, short_code: v || null })
              }}
              placeholder="short code"
              className="w-32 font-mono text-sm"
            />
            {config.short_code && (
              <span className="text-xs text-gray-400 whitespace-nowrap">
                → {window.location.origin}/go/{config.short_code}
              </span>
            )}
          </div>
          <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
        </CardHeader>
        <CardContent>
          <TabPanel id="capabilities" activeTab={activeTab}>
            <div className="space-y-6">
              <Input
                label={t('customerAgents.widgetSessionTtl')}
                type="text"
                inputMode="numeric"
                value={widgetSessionTtlInput}
                onFocus={(e: React.ChangeEvent<HTMLInputElement> | any) => e.target.select()}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  const raw = e.target.value.replace(/[^\d]/g, '')
                  setWidgetSessionTtlInput(raw)
                  setConfig({
                    ...config,
                    widget_session_ttl_hours: raw === ''
                      ? 0
                      : Math.min(8760, Math.max(0, parseInt(raw, 10) || 0)),
                  })
                }}
                onBlur={() => {
    setWidgetSessionTtlInput(String(config.widget_session_ttl_hours ?? 24))
                }}
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 -mt-4">
                {t('customerAgents.widgetSessionHint')}
              </p>
              <Select
                label={t('customerAgents.workspaceMode')}
                value={config.workspace_mode || 'auto'}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  const v = e.target.value
                  setConfig({
                    ...config,
                    workspace_mode: v === 'auto' ? null : v,
                  })
                }}
                options={[
                  { value: 'auto', label: t('customerAgents.workspaceModeAuto') },
                  { value: 'local', label: t('customerAgents.workspaceModeLocal') },
                  ...(config.workspace_container_allowed === false
                    ? []
                    : [{ value: 'container', label: t('customerAgents.workspaceModeContainer') }]),
                ]}
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 -mt-4">
                {config.workspace_container_allowed === false
                  ? t('customerAgents.workspaceModeContainerDisabled')
                  : t('customerAgents.workspaceModeHint')}
              </p>
              <Select
                label={t('customerAgents.bindAiModel')}
                options={[
                  { value: '', label: t('customerAgents.useDefaultModel') },
                  ...aiConfigs.map((c) => ({ value: c.id, label: c.name })),
                ]}
                value={config.ai_config_id || ''}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setConfig({
                    ...config,
                    ai_config_id: e.target.value || null,
                  })
                }
              />
              <Textarea
                label={t('customerAgents.channelPrompt')}
                value={config.channel_prompt || ''}
                onChange={(e: any) =>
                  setConfig({ ...config, channel_prompt: e.target.value || null })
                }
                rows={8}
                placeholder={t('customerAgents.channelPromptPlaceholder')}
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 -mt-4">
                {t('customerAgents.channelPromptHint')}
              </p>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-primary-600" />
                  <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('customerAgents.skillsSection')}</h4>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {t('customerAgents.skillsHint')}
                </p>
                {skills.map((skill) => (
                  <label key={skill.id} className="flex gap-2 text-sm text-gray-700 dark:text-gray-300 block mb-1">
                    <input
                      type="checkbox"
                      checked={selectedSkillIds.includes(skill.id)}
                      onChange={() => toggleSkill(skill.id)}
                    />
                    {skill.name} ({skillTypeLabel(skill.skill_type)})
                  </label>
                ))}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-primary-600" />
                  <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('customerAgents.showcaseSkillsSection')}</h4>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {t('customerAgents.showcaseSkillsHint')}
                </p>
                {skills.map((skill) => (
                  <label key={`showcase-${skill.id}`} className="flex gap-2 text-sm text-gray-700 dark:text-gray-300 block mb-1">
                    <input
                      type="checkbox"
                      checked={showcaseSkillIds.includes(skill.id)}
                      onChange={() => toggleShowcaseSkill(skill.id)}
                    />
                    {skill.name}
                  </label>
                ))}
                {showcaseSkillIds.length > 0 && (
                  <button
                    type="button"
                    className="text-xs text-primary-600"
                    onClick={() => updateTheme('showcaseSkillIds', [])}
                  >
                    {t('customerAgents.showcaseUseAll')}
                  </button>
                )}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                  <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('customerAgents.knowledgeSection')}</h4>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('customerAgents.knowledgeHint')}</p>
                {knowledgeBases.map((kb) => (
                  <label key={kb.id} className="flex gap-2 text-sm text-gray-700 dark:text-gray-300 block mb-1">
                    <input
                      type="checkbox"
                      checked={selectedKbIds.includes(kb.id)}
                      onChange={() => toggleKnowledgeBase(kb.id)}
                    />
                    {kb.name}
                  </label>
                ))}
              </div>
              <div>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div className="flex items-center gap-2">
                    <Paperclip className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('customerAgents.autoReplySection')}</h4>
                  </div>
                  <Button
                    type="button"
                    size="action"
                    variant="secondary"
                    leftIcon={<Plus className="w-4 h-4" />}
                    onClick={addAutoReplyRule}
                  >
                    {t('customerAgents.autoReplyAddRule')}
                  </Button>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  {t('customerAgents.autoReplyHint')}
                </p>
                {config.auto_reply_rules.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                    {t('customerAgents.autoReplyEmpty')}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {config.auto_reply_rules.map((rule, index) => (
                      <div
                        key={rule.id}
                        className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 space-y-3"
                      >
                        <div className="flex items-center gap-3">
                          <Input
                            label={t('customerAgents.autoReplyRuleName')}
                            value={rule.name}
                            onChange={(e) => updateAutoReplyRule(rule.id, { name: e.target.value })}
                          />
                          <label className="flex items-center gap-2 mt-6 text-sm text-gray-700 dark:text-gray-300 shrink-0">
                            <input
                              type="checkbox"
                              checked={rule.enabled}
                              onChange={() => toggleRuleEnabled(rule.id)}
                            />
                            {t('customerAgents.autoReplyEnabled')}
                          </label>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            leftIcon={<Trash2 className="w-4 h-4" />}
                            className="mt-6 shrink-0"
                            onClick={() => removeAutoReplyRule(rule.id)}
                          >
                            {t('common.delete')}
                          </Button>
                        </div>

                        <Textarea
                          label={t('customerAgents.autoReplyTriggerText')}
                          value={rule.trigger_text}
                          onChange={(e) => updateAutoReplyRule(rule.id, { trigger_text: e.target.value })}
                          placeholder={t('customerAgents.autoReplyTriggerPlaceholder')}
                        />

                        <Input
                          label={t('customerAgents.autoReplyKeywords')}
                          value={rule.keywords_text}
                          onChange={(e) =>
                            updateAutoReplyRule(rule.id, {
                              keywords_text: e.target.value,
                            })
                          }
                          placeholder={t('customerAgents.autoReplyKeywordsPlaceholder')}
                        />

                        <div className="space-y-2">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                            {t('customerAgents.autoReplyChannels')}
                          </p>
                          <div className="flex flex-wrap gap-3">
                            {autoReplyChannelOptions.map((option) => (
                              <label
                                key={`${rule.id}-${option.value}`}
                                className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"
                              >
                                <input
                                  type="checkbox"
                                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                                  checked={rule.channels.includes(option.value)}
                                  onChange={() => toggleAutoReplyRuleChannel(rule.id, option.value as (typeof AUTO_REPLY_CHANNEL_VALUES)[number])}
                                />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </div>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {t('customerAgents.autoReplyChannelsHint')}
                          </p>
                        </div>

                        <Textarea
                          label={t('customerAgents.autoReplyReplyText')}
                          value={rule.reply_text || ''}
                          onChange={(e) => updateAutoReplyRule(rule.id, { reply_text: e.target.value || null })}
                          placeholder={t('customerAgents.autoReplyReplyPlaceholder')}
                        />

                        <div className="grid grid-cols-1 md:grid-cols-[7.5rem_1fr_1fr] gap-3 items-end">
                          <Button
                            type="button"
                            variant="secondary"
                            size="action"
                            leftIcon={<Paperclip className="w-4 h-4" />}
                            isLoading={uploadingRuleId === rule.id}
                            onClick={() => triggerRuleAssetUpload(rule.id)}
                          >
                            {t('customerAgents.autoReplyUploadAsset')}
                          </Button>
                          <Input
                            label={t('customerAgents.autoReplyAssetTitle')}
                            value={rule.asset.title || ''}
                            onChange={(e) => updateAutoReplyRuleAsset(rule.id, { title: e.target.value })}
                            placeholder={t('customerAgents.autoReplyAssetTitlePlaceholder')}
                          />
                          <Input
                            label={t('customerAgents.autoReplyAssetUrl')}
                            value={rule.asset.url}
                            onChange={(e) => updateAutoReplyRuleAsset(rule.id, { url: e.target.value })}
                            placeholder={t('customerAgents.autoReplyAssetUrlPlaceholder')}
                          />
                        </div>

                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {t('customerAgents.autoReplyCurrentAsset', {
                            index: index + 1,
                            asset: rule.asset.title || rule.asset.name || rule.asset.url || t('customerAgents.autoReplyNoAsset'),
                          })}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </TabPanel>

          <TabPanel id="widget" activeTab={activeTab}>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label={t('customerAgents.widgetTitleLabel')}
                  value={theme.widgetTitle || config.name}
                  onChange={(e: any) => updateTheme('widgetTitle', e.target.value)}
                />
                <Input
                  label={t('customerAgents.botNameLabel')}
                  value={theme.botName || defaultBot}
                  onChange={(e: any) => updateTheme('botName', e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('customerAgents.themeColor')}
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={primaryColor}
                      onChange={(e) => updateTheme('primaryColor', e.target.value)}
                      title={t('customerAgents.themeColor')}
                      className="w-10 h-10 rounded-lg border border-gray-300 dark:border-gray-600 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={primaryColor}
                      onChange={(e) => updateTheme('primaryColor', e.target.value)}
                      title={t('customerAgents.themeColor')}
                      placeholder="#3b82f6"
                      className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('customerAgents.widgetPosition')}
                  </label>
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => setConfig({ ...config, position: 'right' })}
                      className={`flex-1 px-4 py-2 rounded-lg border text-sm transition-colors ${
                        config.position === 'right'
                          ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                          : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400'
                      }`}
                    >
                      <Smartphone className="w-4 h-4 mx-auto mb-1" />
                      {t('customerAgents.positionBottomRight')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfig({ ...config, position: 'left' })}
                      className={`flex-1 px-4 py-2 rounded-lg border text-sm transition-colors ${
                        config.position === 'left'
                          ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                          : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400'
                      }`}
                    >
                      <Smartphone className="w-4 h-4 mx-auto mb-1" />
                      {t('customerAgents.positionBottomLeft')}
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Select
                  label={t('customerAgents.launcherIconLabel')}
                  options={[
                    { value: 'chat', label: t('customerAgents.launcherIconChat') },
                    { value: 'bot', label: t('customerAgents.launcherIconBot') },
                    { value: 'spark', label: t('customerAgents.launcherIconSpark') },
                    { value: 'support', label: t('customerAgents.launcherIconSupport') },
                  ]}
                  value={theme.launcherIcon || 'chat'}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                    updateTheme('launcherIcon', e.target.value)
                  }
                />
                <Input
                  label={t('customerAgents.launcherTextLabel')}
                  value={theme.launcherText || ''}
                  onChange={(e: any) => updateTheme('launcherText', e.target.value)}
                  placeholder={t('customerAgents.launcherTextPlaceholder')}
                />
              </div>

              <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('customerAgents.previewLabel')}</p>
                <div className="rounded-2xl border border-dashed border-gray-200 dark:border-gray-600 bg-white/80 dark:bg-gray-800/60 px-4 py-6">
                  <div
                    className={`flex ${config.position === 'right' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className="inline-flex items-center gap-2 rounded-full bg-primary-600 px-4 py-3 text-white shadow-lg">
                      {React.createElement(previewLauncherIcon, {
                        className: theme.launcherText ? 'w-5 h-5' : 'w-6 h-6',
                      })}
                      {(theme.launcherText || '').trim() ? (
                        <span className="text-sm font-medium">{theme.launcherText}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                    <span>
                      {theme.widgetTitle || config.name} - {theme.botName || defaultBot}
                    </span>
                    <span className="text-xs text-gray-400">
                      {t('customerAgents.previewPositionSuffix', { position: previewPositionLabel })}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  {t('customerAgents.previewLauncher', {
                    icon: theme.launcherIcon || 'chat',
                    text: theme.launcherText || t('customerAgents.launcherTextEmpty'),
                  })}
                </p>
              </div>
            </div>
          </TabPanel>

          <TabPanel id="domain" activeTab={activeTab}>
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('customerAgents.domainHint')}
              </p>
              <div className="flex gap-2">
                <Input
                  placeholder={t('customerAgents.domainPlaceholder')}
                  value={domainInput}
                  onChange={(e) => setDomainInput(e.target.value)}
                  onKeyDown={(e: any) => e.key === 'Enter' && addDomain()}
                />
                <Button variant="secondary" onClick={addDomain}>
                  {t('customerAgents.add')}
                </Button>
              </div>
              {domainList.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {domainList.map((domain) => (
                    <span
                      key={domain}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 text-sm text-gray-700 dark:text-gray-300"
                    >
                      <Globe className="w-3.5 h-3.5" />
                      {domain}
                      <button
                        onClick={() => removeDomain(domain)}
                        className="ml-1 text-gray-400 hover:text-red-500"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </TabPanel>

          <TabPanel id="message" activeTab={activeTab}>
            <div className="space-y-4">
              <Textarea
                label={t('customerAgents.welcomeMessage')}
                value={config.welcome_message || ''}
                onChange={(e: any) =>
                  setConfig({ ...config, welcome_message: e.target.value })
                }
                rows={4}
                placeholder={t('customerAgents.welcomePlaceholder')}
              />
              <Textarea
                label={t('customerAgents.offlineMessage')}
                value={config.offline_message || ''}
                onChange={(e: any) =>
                  setConfig({ ...config, offline_message: e.target.value })
                }
                rows={3}
                placeholder={t('customerAgents.offlinePlaceholder')}
              />
            </div>
          </TabPanel>

          <TabPanel id="embed" activeTab={activeTab}>
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('customerAgents.embedHint')}
              </p>
              {selectedId ? (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-gray-500 font-mono">Agent ID: {selectedId}</span>
                    <Button size="sm" variant="secondary" leftIcon={<Copy className="w-4 h-4" />} onClick={copyEmbedCode}>
                      {t('customerAgents.copyCode')}
                    </Button>
                  </div>
                  <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-xs overflow-x-auto whitespace-pre-wrap">
                    {embedScript}
                  </pre>
                  <div className="flex flex-wrap gap-3 text-xs">
                    <a
                      className="text-primary-600 hover:underline"
                      href={`/widget?agentId=${selectedId}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('customerAgents.openStandaloneChat')}
                    </a>
                    <a
                      className="text-primary-600 hover:underline"
                      href={`/widget/demo?agentId=${selectedId}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('customerAgents.openWidgetDemo')}
                    </a>
                    <a
                      className="text-primary-600 hover:underline"
                      href={`/widget.html?agentId=${selectedId}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('customerAgents.openIframePage')}
                    </a>
                    <a
                      className="text-primary-600 hover:underline"
                      href={`/showcase?agentId=${selectedId}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('customerAgents.openShowcasePage')}
                    </a>
                  </div>
                </>
              ) : (
                <p className="text-sm text-amber-600">{t('customerAgents.saveFirstForEmbed')}</p>
              )}
            </div>
          </TabPanel>
        </CardContent>
      </Card>
    </div>
  )
}
