import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, MessageCircle, MessageSquare, ShoppingBag, Trash2 } from 'lucide-react'
import { portalApi, type MyChannel } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'

function UsageBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = Math.min(100, Math.round((used / limit) * 100))
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{label}</span>
        <span>{used.toLocaleString()} / {limit.toLocaleString()}</span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-primary-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function MyChannelsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [channels, setChannels] = useState<MyChannel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    portalApi.getMyChannels().then(setChannels).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const handleDelete = async (id: string) => {
    if (!confirm(t('portal.deleteConfirm'))) return
    try {
      await portalApi.deleteMyChannel(id)
      setChannels((prev) => prev.filter((c) => c.id !== id))
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleStartChat = async (channel: MyChannel) => {
    try {
      const conv = await portalApi.resumeChannelChat(channel.id, { title: channel.name })
      sessionStorage.setItem('mchat_portal_channel_id', channel.id)
      navigate(`/chat/${conv.id}?channel=${channel.id}`)
    } catch (e: any) {
      setError(e.message || 'Failed to start chat')
    }
  }

  const planBadge = (plan: string) => {
    const map: Record<string, string> = {
      free: t('portal.planFree'), free_trial: t('portal.planFreeTrial'),
      pro: t('portal.planPro'), enterprise: t('portal.planEnterprise'),
    }
    const colors: Record<string, string> = {
      free: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
      free_trial: 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400',
      pro: 'bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400',
      enterprise: 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
    }
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full ${colors[plan] || colors.free}`}>
        {map[plan] || plan}
      </span>
    )
  }

  const formatTokens = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

  if (loading) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('portal.myWorkspaces')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">{channels.length} workspaces</p>
        </div>
        <Button onClick={() => navigate('/portal/templates')} size="sm">
          <ShoppingBag className="w-4 h-4 mr-1" />{t('portal.browseTemplates')}
        </Button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">{error}</div>
      )}

      {channels.length === 0 && (
        <div className="text-center py-16 text-gray-500">
          <MessageSquare className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="font-medium">{t('portal.noChannels')}</p>
          <p className="text-sm mt-1">{t('portal.noChannelsHint')}</p>
          <Link to="/portal/templates" className="inline-flex items-center gap-2 mt-4 text-sm font-medium text-primary-600 dark:text-primary-400">
            <ShoppingBag className="w-4 h-4" />{t('portal.browseTemplates')}
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {channels.map((channel) => (
          <div key={channel.id}
            className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-shadow">
            {/* Header */}
            <div className="p-5 pb-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">{channel.name}</h3>
                    {planBadge(channel.plan)}
                    {!channel.enabled && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-900/30 text-red-600">{t('common.disabled')}</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {channel.channel_category === 'patent_rag' ? 'Patent RAG' : channel.channel_category}
                    {channel.trial_ends_at && (
                      <> · {t('portal.trialRemaining', { days: Math.max(0, Math.ceil((new Date(channel.trial_ends_at).getTime() - Date.now()) / 86400000)) })}</>
                    )}
                    {channel.subscription_ends_at && (
                      <> · {t('portal.subscriptionUntil', { date: new Date(channel.subscription_ends_at).toLocaleDateString() })}</>
                    )}
                  </p>
                </div>
              </div>
            </div>

            {/* Usage */}
            <div className="px-5 pb-3 space-y-2">
              <UsageBar used={channel.usage_messages_month} limit={channel.usage_messages_limit} label={`Messages`} />
              <UsageBar used={channel.usage_tokens_month} limit={channel.usage_tokens_limit} label={`Tokens (${formatTokens(channel.usage_tokens_month)})`} />
            </div>

            {/* Actions */}
            <div className="px-5 pb-4 flex items-center gap-2 border-t border-gray-100 dark:border-gray-700 pt-3">
              <Button onClick={() => handleStartChat(channel)} size="sm" className="w-[120px] gap-1">
                <MessageCircle className="w-3.5 h-3.5" />Chat
              </Button>
              <Button onClick={() => navigate(`/portal/channels/${channel.id}`)} size="sm" variant="outline" className="w-[100px] gap-1">
                <ExternalLink className="w-3.5 h-3.5" />Settings
              </Button>
              <button onClick={() => handleDelete(channel.id)}
                className="p-2 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors shrink-0"
                title={t('common.delete')}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
