import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, BookOpen, Check, Copy, ExternalLink, MessageSquare } from 'lucide-react'
import {
  portalApi,
  type ChannelIntegrations,
  type MyChannel,
  type EmbedCode,
  type PortalAiConfigOption,
} from '@/lib/portalApi'
import {
  PortalAdvancedPanel,
  PortalAdvancedSubsection,
} from '@/components/portal/PortalAdvancedPanel'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'

type SkillBindingState = {
  override?: boolean
  secrets?: Record<string, string>
}

export function ChannelDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [channel, setChannel] = useState<MyChannel | null>(null)
  const [embed, setEmbed] = useState<EmbedCode | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [startingChat, setStartingChat] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', welcome_message: '' })
  const [integrations, setIntegrations] = useState<ChannelIntegrations | null>(null)
  const [skillBindings, setSkillBindings] = useState<Record<string, SkillBindingState>>({})
  const [aiConfigs, setAiConfigs] = useState<PortalAiConfigOption[]>([])
  const [aiOverride, setAiOverride] = useState(false)
  const [aiConfigId, setAiConfigId] = useState('')
  const [savingBindings, setSavingBindings] = useState(false)
  const [savingAi, setSavingAi] = useState(false)
  const [memoryMd, setMemoryMd] = useState('')
  const [dailyDates, setDailyDates] = useState<string[]>([])
  const [selectedDaily, setSelectedDaily] = useState<string | null>(null)
  const [dailyContent, setDailyContent] = useState('')
  const [memoryLoading, setMemoryLoading] = useState(false)
  const [memorySaving, setMemorySaving] = useState(false)

  const aiSelectOptions = useMemo(() => {
    const opts = aiConfigs.map((c) => ({
      value: c.id,
      label: `${c.name} (${c.provider}/${c.model})`,
    }))
    const currentId = aiConfigId || channel?.ai_config_id
    if (currentId && !opts.some((o) => o.value === currentId) && channel) {
      opts.unshift({
        value: currentId,
        label: `${channel.ai_provider}/${channel.ai_model} (${t('portal.aiCurrent')})`,
      })
    }
    return [{ value: '', label: t('portal.aiSelectPlaceholder') }, ...opts]
  }, [aiConfigs, aiConfigId, channel, t])

  const loadChannel = () => {
    if (!id) return
    setLoading(true)
    Promise.all([
      portalApi.getMyChannel(id),
      portalApi.getEmbedCode(id).catch(() => null),
      portalApi.getChannelIntegrations(id).catch(() => null),
      portalApi.listAiConfigs().catch(() => [] as PortalAiConfigOption[]),
      portalApi.getChannelMemory(id).catch(() => null),
    ])
      .then(([ch, em, integ, aiList, mem]) => {
        setChannel(ch)
        setEmbed(em)
        setForm({ name: ch.name, welcome_message: ch.welcome_message || '' })
        setIntegrations(integ)
        setSkillBindings((ch.skill_bindings || {}) as Record<string, SkillBindingState>)
        setAiConfigs(aiList)
        setAiOverride(!!ch.ai_override)
        setAiConfigId(ch.ai_config_id || '')
        if (mem) {
          setMemoryMd(mem.memory_md || '')
          setDailyDates(mem.daily_dates || [])
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadChannel()
  }, [id])

  useEffect(() => {
    const onFocus = () => {
      if (id) {
        portalApi.getMyChannel(id).then(setChannel).catch(() => {})
      }
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [id])

  const loadDaily = async (date: string) => {
    if (!id) return
    setSelectedDaily(date)
    setMemoryLoading(true)
    try {
      const data = await portalApi.getChannelDailyMemory(id, date)
      setDailyContent(data.content || '')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setMemoryLoading(false)
    }
  }

  const handleSaveMemory = async () => {
    if (!id) return
    setMemorySaving(true)
    try {
      const updated = await portalApi.updateChannelMemory(id, memoryMd)
      setMemoryMd(updated.memory_md || '')
      setDailyDates(updated.daily_dates || [])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setMemorySaving(false)
    }
  }

  const handleSave = async () => {
    if (!id) return
    setSaving(true)
    try {
      const updated = await portalApi.updateMyChannel(id, form)
      setChannel(updated)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleCopy = () => {
    if (!embed?.embed_script) return
    navigator.clipboard.writeText(embed.embed_script).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleStartChat = async () => {
    if (!id) return
    setStartingChat(true)
    try {
      const conv = await portalApi.resumeChannelChat(id, { title: channel?.name || 'Chat' })
      sessionStorage.setItem('mchat_portal_channel_id', id)
      navigate(`/chat/${conv.id}?channel=${id}`)
    } catch (e: any) {
      setError(e.message || 'Failed to start chat')
    } finally {
      setStartingChat(false)
    }
  }

  if (loading) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>
  if (!channel) return <div className="text-red-500 text-sm p-4">{error || 'Not found'}</div>

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/portal/channels')}
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400">
        <ArrowLeft className="w-4 h-4" /> {t('portal.myChannels')}
      </button>

      {error && <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">{error}</div>}

      {/* Direct Chat */}
      <div className="bg-primary-50 dark:bg-primary-900/20 rounded-2xl border border-primary-200 dark:border-primary-800 p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-primary-600 text-white flex items-center justify-center">
            <MessageSquare className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">{channel.name}</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {channel.channel_category === 'patent_rag' ? 'Patent RAG' : channel.channel_category}
            </p>
          </div>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
          {channel.welcome_message || 'Start a conversation with this channel.'}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t(
            'portal.persistentChatHint',
            'Chat history is saved for this channel. Leave and return anytime to continue.',
          )}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={handleStartChat} isLoading={startingChat} className="gap-2">
            <MessageSquare className="w-4 h-4" />
            {t('portal.startChat', 'Open Chat')}
          </Button>
          <Link to={`/portal/channels/${id}/knowledge`}>
            <Button type="button" variant="outline" className="gap-2">
              <BookOpen className="w-4 h-4" />
              {t('portal.manageKnowledge', 'Knowledge & files')}
            </Button>
          </Link>
        </div>
      </div>

      {/* Subscription */}
      {channel.subscription_active === false && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800 p-4 text-sm text-amber-800 dark:text-amber-200">
          <p className="font-medium">{t('portal.subscriptionExpired')}</p>
          <p className="mt-1 text-amber-700 dark:text-amber-300">{t('portal.subscriptionExpiredHint')}</p>
          {channel.template_id && (
            <Link
              to={`/portal/checkout?channel=${id}&template=${channel.template_id}&period=monthly`}
              className="inline-block mt-3 text-primary-600 font-medium hover:underline"
            >
              {t('portal.renewNow')}
            </Link>
          )}
        </div>
      )}

      {(channel.subscription_ends_at || channel.trial_ends_at) && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
            {t('portal.subscriptionTitle')}
          </h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-gray-500">{t('portal.planLabel')}</dt>
              <dd className="font-medium">{channel.plan}</dd>
            </div>
            {channel.trial_ends_at && (
              <div>
                <dt className="text-gray-500">{t('portal.trialEnds')}</dt>
                <dd>{new Date(channel.trial_ends_at).toLocaleString()}</dd>
              </div>
            )}
            {channel.subscription_ends_at && (
              <div>
                <dt className="text-gray-500">{t('portal.subscriptionEnds')}</dt>
                <dd>{new Date(channel.subscription_ends_at).toLocaleString()}</dd>
              </div>
            )}
          </dl>
          <div className="flex flex-wrap gap-4 mt-3">
            <Link to="/portal/orders" className="text-sm text-primary-600 hover:underline">
              {t('portal.viewOrders')}
            </Link>
            {channel.template_id && channel.plan === 'pro' && (
              <Link
                to={`/portal/checkout?channel=${id}&template=${channel.template_id}&period=monthly`}
                className="text-sm text-primary-600 hover:underline"
              >
                {t('portal.renewNow')}
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Usage */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Usage this month</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-xl">
            <p className="text-xs text-gray-500">Messages</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {(channel.usage_messages_month ?? 0).toLocaleString()}
              <span className="text-xs font-normal text-gray-400 ml-1">/ {(channel.usage_messages_limit ?? 0).toLocaleString()}</span>
            </p>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-xl">
            <p className="text-xs text-gray-500">Tokens</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {(channel.usage_tokens_month ?? 0) >= 1000 ? `${((channel.usage_tokens_month ?? 0) / 1000).toFixed(1)}k` : (channel.usage_tokens_month ?? 0)}
              <span className="text-xs font-normal text-gray-400 ml-1">/ {((channel.usage_tokens_limit ?? 0) >= 1000 ? `${((channel.usage_tokens_limit ?? 0) / 1000).toFixed(0)}k` : (channel.usage_tokens_limit ?? 0))}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Memory files */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('portal.chatHistory')}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('portal.persistentChatHint')}
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              MEMORY.md
            </label>
            <textarea
              value={memoryMd}
              onChange={(e) => setMemoryMd(e.target.value)}
              rows={8}
              className="w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 px-3 py-2 text-sm font-mono text-gray-900 dark:text-gray-100"
              placeholder={t('portal.chatEmpty')}
            />
            <div className="mt-2">
              <Button onClick={handleSaveMemory} isLoading={memorySaving} size="sm">
                {t('common.save')}
              </Button>
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('portal.chatHistory')}
            </p>
            {dailyDates.length === 0 ? (
              <p className="text-sm text-gray-500">{t('portal.noChatHistory')}</p>
            ) : (
              <div className="flex flex-wrap gap-2 mb-3">
                {dailyDates.map((date) => (
                  <button
                    key={date}
                    type="button"
                    onClick={() => loadDaily(date)}
                    className={`px-3 py-1 rounded-lg text-xs border transition-colors ${
                      selectedDaily === date
                        ? 'bg-primary-100 dark:bg-primary-900/40 border-primary-300 text-primary-700 dark:text-primary-300'
                        : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-900/50'
                    }`}
                  >
                    {date}
                  </button>
                ))}
              </div>
            )}
            {selectedDaily && (
              <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
                {memoryLoading ? '…' : dailyContent || t('portal.noChatHistory')}
              </pre>
            )}
          </div>
        </div>
      </div>

      {/* Basic settings — visible by default */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('portal.channelSettings')}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          <span className="text-gray-500">{t('portal.aiCurrent')}: </span>
          <span className="font-medium text-gray-800 dark:text-gray-200">
            {channel.ai_provider}/{channel.ai_model}
            {!channel.ai_override && channel.template_default_ai_config_id && (
              <span className="text-gray-400 font-normal"> ({t('portal.aiFromTemplate')})</span>
            )}
          </span>
        </p>
        <div className="space-y-4">
          <Input label={t('common.name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input
            label={t('portal.welcomeMessageLabel', '欢迎语')}
            value={form.welcome_message}
            onChange={(e) => setForm({ ...form, welcome_message: e.target.value })}
          />
          <Button onClick={handleSave} isLoading={saving}>{t('common.save')}</Button>
        </div>
      </div>

      <PortalAdvancedPanel hint={t('portal.advancedSettingsHint')}>
        <PortalAdvancedSubsection title={t('portal.aiConfigTitle')} hint={t('portal.aiConfigHint')}>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={aiOverride}
              onChange={(e) => setAiOverride(e.target.checked)}
              className="rounded border-gray-300"
            />
            {t('portal.aiOverrideLabel')}
          </label>
          {aiOverride && (
            <>
              {aiSelectOptions.length <= 1 ? (
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  {t('portal.noAiConfigs')}{' '}
                  <Link to="/portal/account" className="text-primary-600 dark:text-primary-400 underline">
                    {t('portal.goAddAiConfig')}
                  </Link>
                </p>
              ) : (
                <Select
                  label={t('portal.aiSelect')}
                  value={aiConfigId}
                  onChange={(e) => setAiConfigId(e.target.value)}
                  options={aiSelectOptions}
                />
              )}
            </>
          )}
          <p className="text-xs text-gray-500 dark:text-gray-400">
            <Link to="/portal/account" className="text-primary-600 dark:text-primary-400 hover:underline">
              {t('portal.manageAiKeys')}
            </Link>
          </p>
          <Button
            size="sm"
            disabled={aiOverride && !aiConfigId}
            isLoading={savingAi}
            onClick={async () => {
              if (!id) return
              setSavingAi(true)
              try {
                const updated = await portalApi.updateMyChannel(id, {
                  ai_override: aiOverride,
                  ai_config_id: aiOverride ? aiConfigId : channel.ai_config_id,
                })
                setChannel(updated)
                setAiConfigId(updated.ai_config_id || '')
              } catch (e: any) {
                setError(e.message)
              } finally {
                setSavingAi(false)
              }
            }}
          >
            {t('common.save')}
          </Button>
        </PortalAdvancedSubsection>

        <PortalAdvancedSubsection
          title={t('portal.integrationsTitle')}
          hint={t('portal.integrationsHintOverride')}
        >
          {integrations && integrations.integrations.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('portal.noIntegrationsHint')}</p>
          ) : (
            <>
              <div className="space-y-4">
                {integrations?.integrations.map((block) => {
                  const binding = skillBindings[block.skill] || {}
                  const overrideOn = !!binding.override
                  return (
                    <div
                      key={block.skill}
                      className="rounded-xl border border-gray-100 dark:border-gray-700 p-4 space-y-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                          {block.skill}
                          {block.source && (
                            <span className="ml-2 text-xs text-gray-400">({block.source})</span>
                          )}
                        </p>
                        {block.allow_channel_override !== false && (
                          <label className="flex items-center gap-2 text-xs cursor-pointer">
                            <input
                              type="checkbox"
                              checked={overrideOn}
                              onChange={(e) => {
                                const on = e.target.checked
                                setSkillBindings((prev) => ({
                                  ...prev,
                                  [block.skill]: { ...prev[block.skill], override: on },
                                }))
                              }}
                              className="rounded border-gray-300"
                            />
                            {t('portal.skillOverrideLabel')}
                          </label>
                        )}
                      </div>
                      {overrideOn &&
                        block.fields.map((field) => (
                          <div key={`${block.skill}-${field.key}`}>
                            <Input
                              label={field.label || field.key}
                              type={field.secret !== false ? 'password' : 'text'}
                              placeholder={field.placeholder || undefined}
                              value={binding.secrets?.[field.key] ?? ''}
                              onChange={(e) => {
                                const v = e.target.value
                                setSkillBindings((prev) => ({
                                  ...prev,
                                  [block.skill]: {
                                    ...prev[block.skill],
                                    override: true,
                                    secrets: {
                                      ...(prev[block.skill]?.secrets || {}),
                                      [field.key]: v,
                                    },
                                  },
                                }))
                              }}
                            />
                            {field.help && (
                              <p className="text-xs text-gray-400 mt-1">{field.help}</p>
                            )}
                          </div>
                        ))}
                      {!overrideOn && (
                        <p className="text-xs text-gray-400">{t('portal.skillUsePlatformDefault')}</p>
                      )}
                    </div>
                  )
                })}
              </div>
              {integrations && integrations.integrations.length > 0 && (
                <Button
                  size="sm"
                  onClick={async () => {
                    if (!id) return
                    setSavingBindings(true)
                    try {
                      const updated = await portalApi.updateMyChannel(id, {
                        skill_bindings: skillBindings,
                      })
                      setChannel(updated)
                      setSkillBindings((updated.skill_bindings || {}) as Record<string, SkillBindingState>)
                    } catch (e: any) {
                      setError(e.message)
                    } finally {
                      setSavingBindings(false)
                    }
                  }}
                  isLoading={savingBindings}
                >
                  {t('portal.saveIntegrations')}
                </Button>
              )}
            </>
          )}
        </PortalAdvancedSubsection>

        <PortalAdvancedSubsection title={t('portal.embedAdvanced')} hint={t('portal.embedHint')}>
          {embed ? (
            <>
              <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto">{embed.embed_script}</pre>
              <div className="flex items-center gap-3">
                <Button onClick={handleCopy} size="sm" className="gap-1">
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? t('portal.copied') : t('portal.copyCode')}
                </Button>
                <a
                  href={embed.widget_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary-600 dark:text-primary-400 hover:underline"
                >
                  {t('common.preview')} <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('common.loading')}</p>
          )}
        </PortalAdvancedSubsection>
      </PortalAdvancedPanel>
    </div>
  )
}
