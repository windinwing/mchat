import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Workflow } from 'lucide-react'
import api from '@/lib/api'
import { Spinner } from '@/components/ui/Spinner'
import type { WorkflowEntitlements } from '@/types/workflowEntitlements'

/** Core-only entitlement summary; upgrade and checkout controls belong to Cloud. */
export function WorkflowEntitlementBanner() {
  const { t } = useTranslation()
  const ent = useWorkflowEntitlements()

  if (!ent) {
    return (
      <div className="flex justify-center py-4">
        <Spinner size="sm" />
      </div>
    )
  }

  const wfCap =
    ent.max_workflows == null
      ? t('portal.automationUnlimited')
      : String(ent.max_workflows)
  const runCap =
    ent.max_runs_month == null
      ? t('portal.automationUnlimited')
      : String(ent.max_runs_month)

  return (
    <div className="mb-6 rounded-2xl border border-primary-200 dark:border-primary-800/50 bg-primary-50/60 dark:bg-primary-950/30 p-4 sm:p-5">
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
        </div>
      </div>
    </div>
  )
}

export function useWorkflowEntitlements() {
  const [ent, setEnt] = useState<WorkflowEntitlements | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .get<WorkflowEntitlements>('/workflows/entitlements')
      .then((data) => {
        if (!cancelled) setEnt(data)
      })
      .catch(() => {
        if (!cancelled) setEnt(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return ent
}
