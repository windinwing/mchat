import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { portalApi, type ChannelTemplate } from '@/lib/portalApi'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'

export function CheckoutPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const templateId = params.get('template') || ''
  const channelId = params.get('channel') || ''
  const period = (params.get('period') as 'monthly' | 'yearly') || 'monthly'
  const purpose = params.get('purpose') || ''
  const isAutomation = purpose === 'automation'
  const isRenewal = Boolean(channelId)

  const [template, setTemplate] = useState<ChannelTemplate | null>(null)
  const [channelName, setChannelName] = useState('')
  const [method, setMethod] = useState<'alipay' | 'wechat'>('alipay')
  const [orderId, setOrderId] = useState<string | null>(null)
  const [qrContent, setQrContent] = useState<string | null>(null)
  const [amountCents, setAmountCents] = useState(0)
  const [loading, setLoading] = useState(true)
  const [paying, setPaying] = useState(false)
  const [instantDone, setInstantDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const backTo = isAutomation ? '/portal/workflows' : `/portal/templates/${templateId}`

  useEffect(() => {
    if (!templateId) return
    portalApi
      .getTemplate(templateId)
      .then((tmpl) => {
        setTemplate(tmpl)
        setChannelName(tmpl.name)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [templateId])

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPoll = useCallback(
    (oid: string) => {
      stopPoll()
      pollRef.current = setInterval(async () => {
        try {
          const st = await portalApi.checkOrderStatus(oid)
          if (st.paid) {
            stopPoll()
            if (isAutomation) {
              navigate('/portal/workflows', { replace: true })
            } else if (st.channel_id) {
              navigate(`/portal/channels/${st.channel_id}`, { replace: true })
            }
          }
        } catch {
          /* ignore poll errors */
        }
      }, 2500)
    },
    [isAutomation, navigate, stopPoll],
  )

  useEffect(() => () => stopPoll(), [stopPoll])

  const handleCheckoutResult = (checkout: Awaited<ReturnType<typeof portalApi.createCheckout>>) => {
    setAmountCents(checkout.amount_cents)
    if (checkout.instant) {
      setInstantDone(true)
      return
    }
    setOrderId(checkout.order_id)
    setQrContent(checkout.qr_content)
    if (checkout.order_id) {
      startPoll(checkout.order_id)
    }
  }

  const handlePay = async () => {
    if (!templateId) return
    setPaying(true)
    setError(null)
    try {
      const checkout = await portalApi.createCheckout({
        template_id: templateId,
        billing_period: period,
        channel_name: isRenewal ? undefined : channelName || undefined,
        channel_id: channelId || undefined,
        payment_method: method,
      })
      handleCheckoutResult(checkout)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('portal.payFailed'))
    } finally {
      setPaying(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  const listPriceCents =
    template &&
    (period === 'yearly' && template.price_yearly_cents > 0
      ? template.price_yearly_cents
      : template.price_monthly_cents)

  const amount =
    amountCents > 0
      ? `¥${(amountCents / 100).toFixed(2)}`
      : listPriceCents != null && listPriceCents > 0
        ? `¥${(listPriceCents / 100).toFixed(2)}`
        : t('portal.automationActivateFree')

  const periodLabel = period === 'yearly' ? t('portal.yearly') : t('portal.monthly')
  const isFreeRenewal = isRenewal && (listPriceCents ?? 0) <= 0

  const qrUrl = qrContent
    ? `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(qrContent)}`
    : null

  const pageTitle = isAutomation
    ? t('portal.automationCheckoutTitle')
    : isRenewal
      ? t('portal.renewCheckoutTitle')
      : t('portal.checkoutTitle')

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <Link
        to={backTo}
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-primary-600"
      >
        <ArrowLeft className="w-4 h-4" />{' '}
        {isAutomation ? t('portal.workflowsNav') : t('portal.templates')}
      </Link>

      <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{pageTitle}</h1>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 text-sm text-red-600">
          {error}
        </div>
      )}

      {instantDone && (
        <div className="p-4 rounded-2xl bg-green-50 dark:bg-green-900/30 border border-green-200 text-sm text-green-800 dark:text-green-200 space-y-3">
          <p>{t('portal.automationActivateSuccess')}</p>
          <Button type="button" onClick={() => navigate('/portal/workflows', { replace: true })}>
            {t('portal.workflowsNav')}
          </Button>
        </div>
      )}

      {!instantDone && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          {isAutomation && (
            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
              {t('portal.automationCheckoutDesc', {
                workspace: channelName || template?.name || '—',
                period: periodLabel,
              })}
            </p>
          )}
          {!isAutomation && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {template?.name} · {periodLabel}
            </p>
          )}
          <p className="text-2xl font-bold">{amount}</p>

          {!qrContent && (
            <>
              {!isRenewal && (
                <Input
                  label={t('portal.channelName')}
                  value={channelName}
                  onChange={(e) => setChannelName(e.target.value)}
                />
              )}
              {isFreeRenewal ? (
                <Button className="w-full" size="lg" isLoading={paying} onClick={handlePay}>
                  {t('portal.automationActivateFree')}
                </Button>
              ) : (
                <>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant={method === 'alipay' ? 'primary' : 'outline'}
                      className="flex-1"
                      onClick={() => setMethod('alipay')}
                    >
                      {t('portal.payAlipay')}
                    </Button>
                    <Button
                      type="button"
                      variant={method === 'wechat' ? 'primary' : 'outline'}
                      className="flex-1"
                      onClick={() => setMethod('wechat')}
                    >
                      {t('portal.payWechat')}
                    </Button>
                  </div>
                  <Button className="w-full" size="lg" isLoading={paying} onClick={handlePay}>
                    {t('portal.createPayment')}
                  </Button>
                </>
              )}
            </>
          )}

          {qrUrl && (
            <div className="flex flex-col items-center gap-3 pt-2">
              <img
                src={qrUrl}
                alt="QR"
                className="rounded-lg border border-gray-200"
                width={220}
                height={220}
              />
              <p className="text-sm text-gray-500 text-center">
                {method === 'alipay' ? t('portal.scanAlipay') : t('portal.scanWechat')}
              </p>
              <p className="text-xs text-gray-400 flex items-center gap-1">
                <RefreshCw className="w-3 h-3" /> {t('portal.pollingPayment')}
              </p>
              {orderId && (
                <Button variant="outline" size="sm" onClick={() => portalApi.checkOrderStatus(orderId)}>
                  {t('portal.refreshPayment')}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
