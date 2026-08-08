import { ApiError } from './api'

export interface AutomationLimitDetail {
  code?: string
  message?: string
  /** i18n key for the message (preferred over `message` when present). */
  message_key?: string
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

/**
 * Resolve the user-facing message for a limit detail.
 * Prefers the i18n `message_key` (localized); falls back to the backend
 * `message` (Chinese) so there's always something to show.
 */
export function limitMessage(detail: AutomationLimitDetail, t: (key: string, opts?: any) => string): string {
  if (detail.message_key) {
    const localized = t(detail.message_key, { defaultValue: '' })
    if (localized) return localized
  }
  return detail.message || ''
}
