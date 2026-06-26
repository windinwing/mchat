import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, FileSearch, MessageSquare } from 'lucide-react'
import { portalApi, type ChannelTemplate, type MyChannel } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  FileSearch,
  MessageSquare,
}

export function TemplateDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [template, setTemplate] = useState<ChannelTemplate | null>(null)
  const [ownedChannel, setOwnedChannel] = useState<MyChannel | null>(null)
  const [loading, setLoading] = useState(true)
  const [renting, setRenting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    Promise.all([
      portalApi.getTemplate(id),
      portalApi.getMyChannels().catch(() => [] as MyChannel[]),
    ])
      .then(([tmpl, channels]) => {
        setTemplate(tmpl)
        setOwnedChannel(channels.find((c) => c.template_id === id) ?? null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  const handleRent = async () => {
    if (!id || !template) return
    const hasMonthly = template.price_monthly_cents > 0
    const hasYearly = template.price_yearly_cents > 0
    const needsPay = hasMonthly || hasYearly
    if (needsPay) {
      // Pick the period that has a price. If only yearly is priced (monthly=0),
      // use yearly — otherwise default to monthly.
      const period = hasMonthly ? 'monthly' : 'yearly'
      navigate(`/portal/checkout?template=${id}&period=${period}`)
      return
    }
    setRenting(true)
    try {
      await portalApi.rentChannel(id)
      navigate('/portal/channels', { replace: true })
    } catch (e: any) {
      const msg = e.message || ''
      if (msg.includes('402') || msg.toLowerCase().includes('payment')) {
        const period = hasMonthly ? 'monthly' : 'yearly'
        navigate(`/portal/checkout?template=${id}&period=${period}`)
        return
      }
      setError(msg || t('portal.rentFailed'))
    } finally {
      setRenting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }
  if (!template) {
    return <div className="text-red-500 text-sm p-4">{error || t('common.noData')}</div>
  }

  const Icon = iconMap[template.icon || ''] || MessageSquare
  const price =
    template.price_monthly_cents > 0
      ? `¥${(template.price_monthly_cents / 100).toFixed(0)}${t('portal.monthly')}`
      : template.price_yearly_cents > 0
        ? `¥${(template.price_yearly_cents / 100).toFixed(0)}${t('portal.yearly', '/年')}`
        : t('portal.planFree')

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate('/portal/templates')}
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400"
      >
        <ArrowLeft className="w-4 h-4" /> {t('portal.templates')}
      </button>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-14 h-14 rounded-2xl bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center shrink-0">
            <Icon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{template.name}</h1>
              {ownedChannel && (
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                  {t('portal.templateInUse', 'In use')}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{template.description}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-6 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl">
          <div>
            <p className="text-xs text-gray-500">{t('portal.monthly')}</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{price}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('portal.trialDays', { days: template.trial_days })}</p>
            <p className="text-sm text-green-600 dark:text-green-400 font-medium">
              {template.trial_days > 0
                ? t('portal.trialRemaining', { days: template.trial_days })
                : t('portal.noTrial')}
            </p>
          </div>
        </div>

        <div className="mb-6 p-4 rounded-xl border border-primary-100 dark:border-primary-900/40 bg-primary-50/40 dark:bg-primary-950/20">
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            {t('portal.templateAutomationTitle')}
          </p>
          <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1.5 list-disc list-inside">
            <li>{t('portal.templateAutomationTrial')}</li>
            <li>{t('portal.templateAutomationPro')}</li>
          </ul>
        </div>

        {ownedChannel ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t(
                'portal.templateAlreadyOwned',
                'You already opened this solution. Continue chatting or manage knowledge.',
              )}
            </p>
            <div className="flex flex-wrap gap-2">
              <Link to={`/portal/channels/${ownedChannel.id}`}>
                <Button type="button">{t('portal.openAssistant', 'Open assistant')}</Button>
              </Link>
              <Link to={`/portal/channels/${ownedChannel.id}/knowledge`}>
                <Button type="button" variant="outline">
                  {t('portal.manageKnowledge', 'Knowledge & files')}
                </Button>
              </Link>
            </div>
          </div>
        ) : (
          <Button onClick={handleRent} className="w-full" size="lg" isLoading={renting}>
            {t('portal.rentChannel')}
          </Button>
        )}
      </div>
    </div>
  )
}
