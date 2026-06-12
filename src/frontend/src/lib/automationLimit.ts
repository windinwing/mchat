import { ApiError } from './api'

export interface AutomationLimitDetail {
  code?: string
  message?: string
  plan?: string
  upgrade_template_id?: string | null
  upgrade_channel_id?: string | null
}

export function extractAutomationLimit(err: unknown): AutomationLimitDetail | null {
  if (!(err instanceof ApiError) || err.status !== 402) return null
  const raw = err.data?.detail
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  return raw as AutomationLimitDetail
}

export function automationCheckoutPath(detail: AutomationLimitDetail): string {
  if (!detail.upgrade_template_id) return '/portal/templates'
  const qs = new URLSearchParams({
    template: detail.upgrade_template_id,
    period: 'monthly',
  })
  if (detail.upgrade_channel_id) qs.set('channel', detail.upgrade_channel_id)
  return `/portal/checkout?${qs.toString()}`
}
