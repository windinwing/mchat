import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import { Spinner } from '@/components/ui/Spinner'

interface ChannelSubscription {
  channel_id: string
  channel_name: string
  user_id: string
  user_username: string | null
  user_phone: string | null
  user_display_name: string | null
  template_id: string | null
  template_name: string | null
  plan: string
  trial_ends_at: string | null
  subscription_ends_at: string | null
  subscription_active: boolean
  enabled: boolean
  created_at: string
  updated_at: string
}

interface PortalUserSubscription {
  user_id: string
  user_username: string | null
  user_phone: string | null
  user_display_name: string | null
  channels: ChannelSubscription[]
}

interface ChannelTemplateOption {
  id: string
  name: string
  category: string
  is_published: boolean
}

type QuickAction =
  | { kind: 'trial'; days: number }
  | { kind: 'pro_days'; days: number; grant: boolean }
  | { kind: 'pro_months'; months: number }
  | { kind: 'free' }

function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function toLocalInput(iso: string | null | undefined) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromLocalInput(value: string): string | null {
  if (!value) return null
  return new Date(value).toISOString()
}

function planBadgeClass(plan: string, active: boolean) {
  if (!active) return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
  if (plan === 'pro' || plan === 'enterprise') {
    return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
  }
  if (plan === 'free_trial') {
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  }
  return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
}

function hasPaidSubscription(row: ChannelSubscription) {
  if (row.plan === 'pro' || row.plan === 'enterprise') {
    if (!row.subscription_ends_at) return true
    return row.subscription_active
  }
  if (row.plan === 'free_trial' && row.trial_ends_at) {
    return row.subscription_active
  }
  return false
}

export function AdminSubscriptionsPage() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ChannelSubscription[]>([])
  const [userRows, setUserRows] = useState<PortalUserSubscription[]>([])
  const [viewMode, setViewMode] = useState<'channels' | 'users'>('channels')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [planFilter, setPlanFilter] = useState('')
  const [activeFilter, setActiveFilter] = useState('')
  const [editing, setEditing] = useState<ChannelSubscription | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveOk, setSaveOk] = useState<string | null>(null)
  const [customPlan, setCustomPlan] = useState('')
  const [trialEndsAt, setTrialEndsAt] = useState('')
  const [subscriptionEndsAt, setSubscriptionEndsAt] = useState('')
  const [note, setNote] = useState('')
  const [templates, setTemplates] = useState<ChannelTemplateOption[]>([])
  const [provisioningUser, setProvisioningUser] = useState<PortalUserSubscription | null>(null)
  const [provisionTemplateId, setProvisionTemplateId] = useState('')
  const [provisionNote, setProvisionNote] = useState('')
  const [provisionSaving, setProvisionSaving] = useState(false)
  const [provisionError, setProvisionError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<ChannelTemplateOption[]>('/admin/templates')
      .then((list) => {
        setTemplates(list || [])
        if (list?.length) {
          setProvisionTemplateId((cur) => cur || list[0].id)
        }
      })
      .catch(() => setTemplates([]))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (q.trim()) params.set('q', q.trim())
    if (planFilter) params.set('plan', planFilter)
    if (activeFilter === 'active') params.set('active_only', 'true')
    if (activeFilter === 'inactive') params.set('active_only', 'false')
    const qs = params.toString()

    const channelReq = api.get<ChannelSubscription[]>(
      `/admin/subscriptions/channels${qs ? `?${qs}` : ''}`,
    )
    const userReq = q.trim()
      ? api.get<PortalUserSubscription[]>(
          `/admin/subscriptions/users?${new URLSearchParams({ q: q.trim() }).toString()}`,
        )
      : Promise.resolve([] as PortalUserSubscription[])

    Promise.all([channelReq, userReq])
      .then(([channels, users]) => {
        setRows(channels)
        setUserRows(users)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [q, planFilter, activeFilter])

  useEffect(() => {
    load()
  }, [load])

  const openEdit = (row: ChannelSubscription) => {
    setEditing(row)
    setCustomPlan(row.plan)
    setTrialEndsAt(toLocalInput(row.trial_ends_at))
    setSubscriptionEndsAt(toLocalInput(row.subscription_ends_at))
    setNote('')
    setSaveError(null)
    setSaveOk(null)
  }

  const closeEdit = () => {
    setEditing(null)
    setSaveError(null)
    setSaveOk(null)
  }

  const patchChannel = async (body: Record<string, unknown>) => {
    if (!editing) return
    setSaving(true)
    setSaveError(null)
    setSaveOk(null)
    try {
      const res = await api.patch<{ channel: ChannelSubscription; message: string }>(
        `/admin/subscriptions/channels/${editing.channel_id}`,
        body,
      )
      setRows((prev) =>
        prev.map((r) => (r.channel_id === res.channel.channel_id ? res.channel : r)),
      )
      setUserRows((prev) =>
        prev.map((u) => ({
          ...u,
          channels: u.channels.map((c) =>
            c.channel_id === res.channel.channel_id ? res.channel : c,
          ),
        })),
      )
      setEditing(res.channel)
      setCustomPlan(res.channel.plan)
      setTrialEndsAt(toLocalInput(res.channel.trial_ends_at))
      setSubscriptionEndsAt(toLocalInput(res.channel.subscription_ends_at))
      setSaveOk(res.message)
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const runQuick = (action: QuickAction) => {
    if (action.kind === 'trial') {
      void patchChannel({ grant_trial_days: action.days, note: note || undefined })
      return
    }
    if (action.kind === 'pro_days') {
      void patchChannel({
        ...(action.grant ? { grant_pro_days: action.days } : { extend_pro_days: action.days }),
        note: note || undefined,
      })
      return
    }
    if (action.kind === 'pro_months') {
      void patchChannel({ extend_pro_months: action.months, note: note || undefined })
      return
    }
    void patchChannel({
      plan: 'free',
      clear_trial: true,
      clear_subscription: true,
      note: note || undefined,
    })
  }

  const saveCustom = () => {
    const body: Record<string, unknown> = { note: note || undefined }
    const trial = fromLocalInput(trialEndsAt)
    const sub = fromLocalInput(subscriptionEndsAt)
    if (customPlan) body.plan = customPlan
    if (trial) body.trial_ends_at = trial
    if (sub) body.subscription_ends_at = sub
    if (customPlan === 'pro' && !sub && !trial) {
      body.grant_pro_days = 30
    }
    if (!body.plan && !trial && !sub && !body.grant_pro_days) {
      setSaveError(t('adminSubscriptions.nothingToSave'))
      return
    }
    void patchChannel(body)
  }

  const editingHasPro = editing
    ? editing.plan === 'pro' || editing.plan === 'enterprise'
    : false
  const editingHasPaid = editing ? hasPaidSubscription(editing) : false

  const applySearch = () => {
    setQ(searchInput)
    if (searchInput.trim()) setViewMode('users')
  }

  const openProvision = (user: PortalUserSubscription) => {
    setProvisioningUser(user)
    setProvisionError(null)
    setProvisionNote('')
    if (templates.length > 0) {
      setProvisionTemplateId(templates[0].id)
    }
  }

  const closeProvision = () => {
    setProvisioningUser(null)
    setProvisionError(null)
  }

  const runProvision = async (body: Record<string, unknown>) => {
    if (!provisioningUser || !provisionTemplateId) return
    setProvisionSaving(true)
    setProvisionError(null)
    try {
      const res = await api.post<{ channel: ChannelSubscription; message: string }>(
        `/admin/subscriptions/users/${provisioningUser.user_id}/provision`,
        {
          template_id: provisionTemplateId,
          note: provisionNote || undefined,
          ...body,
        },
      )
      setRows((prev) => {
        const exists = prev.some((r) => r.channel_id === res.channel.channel_id)
        return exists
          ? prev.map((r) => (r.channel_id === res.channel.channel_id ? res.channel : r))
          : [res.channel, ...prev]
      })
      setUserRows((prev) =>
        prev.map((u) =>
          u.user_id === provisioningUser.user_id
            ? {
                ...u,
                channels: u.channels.some((c) => c.channel_id === res.channel.channel_id)
                  ? u.channels.map((c) =>
                      c.channel_id === res.channel.channel_id ? res.channel : c,
                    )
                  : [res.channel, ...u.channels],
              }
            : u,
        ),
      )
      closeProvision()
      openEdit(res.channel)
      setSaveOk(res.message)
    } catch (e: unknown) {
      setProvisionError(e instanceof Error ? e.message : String(e))
    } finally {
      setProvisionSaving(false)
    }
  }

  if (loading && rows.length === 0) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6 text-gray-900 dark:text-gray-200">
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          {t('adminSubscriptions.title')}
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('adminSubscriptions.subtitle')}
        </p>
      </div>

      <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 p-4 text-sm text-blue-900 dark:text-blue-100 space-y-2">
        <p className="font-medium">{t('adminSubscriptions.howToTitle')}</p>
        <ol className="list-decimal list-inside space-y-1 text-blue-800 dark:text-blue-200">
          <li>{t('adminSubscriptions.howToStep1')}</li>
          <li>{t('adminSubscriptions.howToStep2')}</li>
          <li>{t('adminSubscriptions.howToStep3')}</li>
        </ol>
        <p className="text-xs text-blue-700 dark:text-blue-300">{t('adminSubscriptions.howToNote')}</p>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-sm text-red-600 dark:text-red-300 border border-red-200 dark:border-red-800">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex flex-col gap-1 text-sm flex-1 min-w-[220px]">
          <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.search')}</span>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && applySearch()}
              placeholder={t('adminSubscriptions.searchPlaceholder')}
            />
            <button
              type="button"
              onClick={applySearch}
              className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm hover:bg-primary-700 shrink-0"
            >
              {t('common.search', '搜索')}
            </button>
          </div>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.planFilter')}</span>
          <select
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2"
            value={planFilter}
            onChange={(e) => setPlanFilter(e.target.value)}
          >
            <option value="">{t('adminSubscriptions.allPlans')}</option>
            <option value="free">free</option>
            <option value="free_trial">free_trial</option>
            <option value="pro">pro</option>
            <option value="enterprise">enterprise</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.statusFilter')}</span>
          <select
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2"
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value)}
          >
            <option value="">{t('adminSubscriptions.allStatus')}</option>
            <option value="active">{t('adminSubscriptions.activeOnly')}</option>
            <option value="inactive">{t('adminSubscriptions.inactiveOnly')}</option>
          </select>
        </label>
        <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setViewMode('channels')}
            className={`px-3 py-2 ${viewMode === 'channels' ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800'}`}
          >
            {t('adminSubscriptions.viewChannels')}
          </button>
          <button
            type="button"
            onClick={() => setViewMode('users')}
            className={`px-3 py-2 ${viewMode === 'users' ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800'}`}
          >
            {t('adminSubscriptions.viewUsers')}
          </button>
        </div>
        <button
          type="button"
          onClick={load}
          className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          {t('common.refresh')}
        </button>
      </div>

      {viewMode === 'users' && q.trim() && (
        <div className="space-y-3">
          {userRows.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('adminSubscriptions.userNotFound')}</p>
          ) : (
            userRows.map((user) => (
              <div
                key={user.user_id}
                className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4"
              >
                <p className="font-medium">
                  {user.user_phone || user.user_display_name || user.user_username || user.user_id}
                </p>
                {user.channels.length === 0 ? (
                  <div className="mt-3 space-y-2">
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {t('adminSubscriptions.userNoChannelsHint')}
                    </p>
                    <button
                      type="button"
                      onClick={() => openProvision(user)}
                      className="text-sm px-3 py-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700"
                    >
                      {t('adminSubscriptions.provisionWorkspace')}
                    </button>
                  </div>
                ) : (
                  <ul className="mt-3 space-y-2">
                    {user.channels.map((ch) => (
                      <li
                        key={ch.channel_id}
                        className="flex flex-wrap items-center justify-between gap-2 text-sm border-t border-gray-100 dark:border-gray-700 pt-2"
                      >
                        <span>
                          {ch.channel_name}
                          <span className={`ml-2 inline-flex px-2 py-0.5 rounded text-xs ${planBadgeClass(ch.plan, ch.subscription_active)}`}>
                            {ch.plan}
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={() => openEdit(ch)}
                          className="text-primary-600 hover:underline"
                        >
                          {t('adminSubscriptions.manage')}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {viewMode === 'channels' && (
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50 text-left text-gray-500 dark:text-gray-400">
              <tr>
                <th className="px-4 py-3">{t('adminSubscriptions.channel')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.user')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.template')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.plan')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.trialEnds')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.subEnds')}</th>
                <th className="px-4 py-3">{t('adminSubscriptions.status')}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {rows.map((row) => (
                <tr key={row.channel_id}>
                  <td className="px-4 py-3 font-medium">{row.channel_name}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {row.user_phone || row.user_display_name || row.user_username || '—'}
                  </td>
                  <td className="px-4 py-3">{row.template_name || '—'}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${planBadgeClass(row.plan, row.subscription_active)}`}
                    >
                      {row.plan}
                    </span>
                  </td>
                  <td className="px-4 py-3">{fmtDate(row.trial_ends_at)}</td>
                  <td className="px-4 py-3">{fmtDate(row.subscription_ends_at)}</td>
                  <td className="px-4 py-3">
                    {!hasPaidSubscription(row) && row.plan === 'free'
                      ? t('adminSubscriptions.noPaidPlan')
                      : row.subscription_active
                        ? t('adminSubscriptions.active')
                        : t('adminSubscriptions.expired')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => openEdit(row)}
                      className="text-primary-600 hover:underline text-sm"
                    >
                      {t('adminSubscriptions.manage')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="p-6 text-center text-gray-500 dark:text-gray-400 text-sm">
              {t('adminSubscriptions.empty')}
            </p>
          )}
        </div>
      )}

      {provisioningUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-6 space-y-4">
            <div className="flex justify-between items-start gap-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {t('adminSubscriptions.provisionTitle')}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {provisioningUser.user_phone ||
                    provisioningUser.user_display_name ||
                    provisioningUser.user_username}
                </p>
              </div>
              <button type="button" onClick={closeProvision} className="text-gray-500">
                ✕
              </button>
            </div>
            {provisionError && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-sm text-red-600 dark:text-red-300">
                {provisionError}
              </div>
            )}
            <label className="block text-sm">
              <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.template')}</span>
              <select
                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                value={provisionTemplateId}
                onChange={(e) => setProvisionTemplateId(e.target.value)}
              >
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name}
                    {!tpl.is_published ? ` (${t('adminSubscriptions.unpublished')})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.note')}</span>
              <input
                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                value={provisionNote}
                onChange={(e) => setProvisionNote(e.target.value)}
                placeholder={t('adminSubscriptions.notePlaceholder')}
              />
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('adminSubscriptions.provisionHint')}
            </p>
            <div className="flex flex-wrap gap-2">
              <QuickBtn
                disabled={provisionSaving || !provisionTemplateId}
                onClick={() => void runProvision({ grant_trial_days: 14 })}
              >
                {t('adminSubscriptions.grantTrial14')}
              </QuickBtn>
              <QuickBtn
                disabled={provisionSaving || !provisionTemplateId}
                onClick={() => void runProvision({ grant_pro_days: 30 })}
              >
                {t('adminSubscriptions.grantPro30')}
              </QuickBtn>
              <QuickBtn
                disabled={provisionSaving || !provisionTemplateId}
                onClick={() => void runProvision({ extend_pro_months: 12 })}
              >
                {t('adminSubscriptions.grantPro1y')}
              </QuickBtn>
            </div>
          </div>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-start gap-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {editing.channel_name}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {editing.user_phone || editing.user_username}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  {editingHasPaid
                    ? t('adminSubscriptions.currentPaid', {
                        plan: editing.plan,
                        end: fmtDate(editing.subscription_ends_at || editing.trial_ends_at),
                      })
                    : t('adminSubscriptions.currentNoPaid')}
                </p>
              </div>
              <button
                type="button"
                onClick={closeEdit}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                ✕
              </button>
            </div>

            {saveError && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-sm text-red-600 dark:text-red-300">
                {saveError}
              </div>
            )}
            {saveOk && (
              <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-sm text-emerald-700 dark:text-emerald-300">
                {saveOk}
              </div>
            )}

            <div>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                {t('adminSubscriptions.quickActions')}
              </p>
              <div className="flex flex-wrap gap-2">
                <QuickBtn disabled={saving} onClick={() => runQuick({ kind: 'trial', days: 7 })}>
                  {t('adminSubscriptions.grantTrial7')}
                </QuickBtn>
                <QuickBtn disabled={saving} onClick={() => runQuick({ kind: 'trial', days: 14 })}>
                  {t('adminSubscriptions.grantTrial14')}
                </QuickBtn>
                <QuickBtn
                  disabled={saving}
                  onClick={() => runQuick({ kind: 'pro_days', days: 30, grant: !editingHasPro })}
                >
                  {editingHasPro
                    ? t('adminSubscriptions.extendPro30')
                    : t('adminSubscriptions.grantPro30')}
                </QuickBtn>
                <QuickBtn
                  disabled={saving}
                  onClick={() => runQuick({ kind: 'pro_months', months: 1 })}
                >
                  {editingHasPro
                    ? t('adminSubscriptions.extendPro1m')
                    : t('adminSubscriptions.grantPro1m')}
                </QuickBtn>
                <QuickBtn
                  disabled={saving}
                  onClick={() => runQuick({ kind: 'pro_months', months: 12 })}
                >
                  {editingHasPro
                    ? t('adminSubscriptions.extendPro1y')
                    : t('adminSubscriptions.grantPro1y')}
                </QuickBtn>
                <QuickBtn
                  disabled={saving}
                  variant="danger"
                  onClick={() => runQuick({ kind: 'free' })}
                >
                  {t('adminSubscriptions.resetFree')}
                </QuickBtn>
              </div>
            </div>

            <label className="block text-sm">
              <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.note')}</span>
              <input
                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t('adminSubscriptions.notePlaceholder')}
              />
            </label>

            <div className="border-t border-gray-200 dark:border-gray-700 pt-4 space-y-3">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {t('adminSubscriptions.customFields')}
              </p>
              <label className="block text-sm">
                <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.plan')}</span>
                <select
                  className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                  value={customPlan}
                  onChange={(e) => setCustomPlan(e.target.value)}
                >
                  <option value="free">free</option>
                  <option value="free_trial">free_trial</option>
                  <option value="pro">pro</option>
                  <option value="enterprise">enterprise</option>
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.trialEnds')}</span>
                <input
                  type="datetime-local"
                  className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                  value={trialEndsAt}
                  onChange={(e) => setTrialEndsAt(e.target.value)}
                />
              </label>
              <label className="block text-sm">
                <span className="text-gray-500 dark:text-gray-400">{t('adminSubscriptions.subEnds')}</span>
                <input
                  type="datetime-local"
                  className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2"
                  value={subscriptionEndsAt}
                  onChange={(e) => setSubscriptionEndsAt(e.target.value)}
                />
              </label>
              <p className="text-xs text-gray-400">{t('adminSubscriptions.customProHint')}</p>
              <button
                type="button"
                disabled={saving}
                onClick={saveCustom}
                className="w-full py-2 rounded-lg bg-primary-600 text-white text-sm hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? t('adminSubscriptions.saving') : t('adminSubscriptions.saveCustom')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function QuickBtn({
  children,
  onClick,
  disabled,
  variant = 'default',
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  variant?: 'default' | 'danger'
}) {
  const base =
    variant === 'danger'
      ? 'border-red-300 text-red-700 dark:border-red-700 dark:text-red-300'
      : 'border-gray-300 text-gray-800 dark:border-gray-600 dark:text-gray-200'
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg border text-xs hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 ${base}`}
    >
      {children}
    </button>
  )
}
