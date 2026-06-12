import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Sparkles, Workflow } from 'lucide-react'
import { portalApi, type WorkflowEntitlements } from '@/lib/portalApi'
import { useAuthStore } from '@/stores/auth'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'

export function WorkflowEntitlementBanner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [ent, setEnt] = useState<WorkflowEntitlements | null>(null)
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)
  const [activateError, setActivateError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        if (user?.role === 'user') {
          const data = await portalApi.getAutomationEntitlements()
          if (!cancelled) setEnt(data)
        } else {
          const data = await api.get<WorkflowEntitlements>('/workflows/entitlements')
          if (!cancelled) setEnt(data)
        }
      } catch {
        if (!cancelled) setEnt(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [user?.role])

  if (loading) {
    return (
      <div className="flex justify-center py-4">
        <Spinner size="sm" />
      </div>
    )
  }
  if (!ent) return null

  const wfCap =
    ent.max_workflows == null
      ? t('portal.automationUnlimited')
      : String(ent.max_workflows)
  const runCap =
    ent.max_runs_month == null
      ? t('portal.automationUnlimited')
      : String(ent.max_runs_month)

  const checkoutPath = ent.upgrade_template_id
    ? `/portal/checkout?template=${ent.upgrade_template_id}&period=monthly&purpose=automation${
        ent.upgrade_channel_id ? `&channel=${ent.upgrade_channel_id}` : ''
      }`
    : '/portal/templates'

  const handleInstantActivate = async () => {
    if (!ent.upgrade_template_id) return
    setActivating(true)
    setActivateError(null)
    try {
      const checkout = await portalApi.createCheckout({
        template_id: ent.upgrade_template_id,
        billing_period: 'monthly',
        channel_id: ent.upgrade_channel_id || undefined,
        payment_method: 'alipay',
      })
      if (checkout.instant) {
        navigate('/portal/workflows', { replace: true })
        window.location.reload()
        return
      }
      navigate(checkoutPath)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portal.payFailed')
      setActivateError(msg)
    } finally {
      setActivating(false)
    }
  }

  return (
    <div className="mb-6 rounded-2xl border border-primary-200 dark:border-primary-800/50 bg-primary-50/60 dark:bg-primary-950/30 p-4 sm:p-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="shrink-0 w-10 h-10 rounded-xl bg-primary-600 text-white flex items-center justify-center">
            <Workflow className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('portal.automationPlanTitle', { plan: ent.plan_label })}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 leading-relaxed">
              {t('portal.automationPlanUsage', {
                workflows: ent.workflow_count,
                wfCap,
                runs: ent.runs_month,
                runCap,
                schedules: ent.schedule_count,
                schedCap:
                  ent.max_schedules == null
                    ? t('portal.automationUnlimited')
                    : String(ent.max_schedules),
              })}
            </p>
            {ent.plan === 'free' && (
              <p className="text-xs text-amber-700 dark:text-amber-300 mt-2">
                {t('portal.automationFreeHint')}
              </p>
            )}
            {ent.upgrade_required && user?.role === 'user' && (
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                {t('portal.automationUpgradeHint')}
              </p>
            )}
            {activateError && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-2">{activateError}</p>
            )}
          </div>
        </div>
        {ent.upgrade_required && user?.role === 'user' && (
          <div className="shrink-0">
            {ent.upgrade_instant ? (
              <Button
                type="button"
                size="sm"
                isLoading={activating}
                leftIcon={<Sparkles className="w-4 h-4" />}
                onClick={handleInstantActivate}
              >
                {t('portal.automationActivateFree')}
              </Button>
            ) : (
              <Link to={checkoutPath}>
                <Button type="button" size="sm" leftIcon={<Sparkles className="w-4 h-4" />}>
                  {t('portal.automationUpgradePro')}
                </Button>
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function useWorkflowEntitlements() {
  const user = useAuthStore((s) => s.user)
  const [ent, setEnt] = useState<WorkflowEntitlements | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data =
          user?.role === 'user'
            ? await portalApi.getAutomationEntitlements()
            : await api.get<WorkflowEntitlements>('/workflows/entitlements')
        if (!cancelled) setEnt(data)
      } catch {
        if (!cancelled) setEnt(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user?.role])

  return ent
}
