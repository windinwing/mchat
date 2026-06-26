import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileSearch, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { portalApi, type ChannelTemplate, type MyChannel } from '@/lib/portalApi'
import { Spinner } from '@/components/ui/Spinner'

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = { FileSearch, MessageSquare }

export function TemplatesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<ChannelTemplate[]>([])
  const [rentedTemplateIds, setRentedTemplateIds] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([portalApi.getTemplates(), portalApi.getMyChannels().catch(() => [] as MyChannel[])])
      .then(([tpl, channels]) => {
        setTemplates(tpl)
        setRentedTemplateIds(
          new Set(channels.map((c) => c.template_id).filter(Boolean) as string[]),
        )
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>
  if (error) return <div className="text-red-500 text-sm p-4">{error}</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('portal.templates')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {t('portal.templatesSubtitle', 'Pick an industry solution and open your own AI assistant.')}
        </p>
      </div>
      {templates.length === 0 && (
        <div className="text-center py-16 text-gray-500">
          <MessageSquare className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p>{t('common.noData')}</p>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {templates.map((tmpl) => {
          const Icon = iconMap[tmpl.icon || ''] || MessageSquare
          const price = tmpl.price_monthly_cents > 0
            ? `¥${(tmpl.price_monthly_cents / 100).toFixed(0)}${t('portal.monthly')}`
            : tmpl.price_yearly_cents > 0
              ? `¥${(tmpl.price_yearly_cents / 100).toFixed(0)}${t('portal.yearly', '/年')}`
              : t('portal.planFree')
          const trial = tmpl.trial_days > 0
            ? t('portal.trialDays', { days: tmpl.trial_days })
            : t('portal.noTrial')
          const alreadyRented = rentedTemplateIds.has(tmpl.id)
          return (
            <button key={tmpl.id} type="button" onClick={() => navigate(`/portal/templates/${tmpl.id}`)}
              className={cn(
                'text-left rounded-2xl border bg-white dark:bg-gray-800 p-5 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all',
                alreadyRented
                  ? 'border-emerald-300 dark:border-emerald-700 ring-1 ring-emerald-200/80 dark:ring-emerald-800/50'
                  : 'border-gray-200 dark:border-gray-700',
              )}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{tmpl.name}</h2>
                    {alreadyRented && (
                      <span className="text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                        {t('portal.templateInUse', 'In use')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{tmpl.description || t('common.noData')}</p>
                </div>
                <div className="w-11 h-11 rounded-2xl bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{price}</span>
                <span className="text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 px-2 py-0.5 rounded-full">{trial}</span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
