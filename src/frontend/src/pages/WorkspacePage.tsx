import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Container, RefreshCw, Server } from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'

interface SidecarStatus {
  exists: boolean
  running: boolean
  status?: string | null
  image?: string | null
}

interface ChannelWorkspaceRow {
  customer_id: string
  customer_name: string
  user_id: string
  plan: string
  workspace_mode: string | null
  user_container_allowed?: boolean | null
  requested_mode: string
  effective_mode: string
  fallback_reason?: string | null
  container_name: string | null
  sidecar: SidecarStatus
  disk_usage_bytes: { total?: number; skills?: number; uploads?: number; data?: number }
  usage_storage_bytes: number
  last_active_at: string | null
  idle_minutes: number | null
}

interface SidecarRow {
  container_name: string
  user_id: string
  running: boolean
  status: string
  image: string
  configured_image: string
  image_matches: boolean
  idle_minutes: number | null
  last_active_at: string | null
  memory_limit_bytes?: number | null
  cpus?: number | null
  configured_memory?: string | null
  configured_cpus?: string | null
}

interface RuntimeSettings {
  workspace_container_enabled: boolean
  workspace_container_image: string
  workspace_container_memory?: string
  workspace_container_cpus?: string
  workspace_sidecar_idle_minutes: number
  workspace_sidecar_recycle_enabled: boolean
}

interface UserWorkspaceRow {
  user_id: string
  username: string
  display_name: string | null
  workspace_container_allowed: boolean | null
  container_entitled: boolean
  tenant_skill_authoring: boolean
  workspace_sidecar_memory: string | null
  workspace_sidecar_cpus: string | null
  effective_memory: string | null
  effective_cpus: string | null
  container_name: string | null
  sidecar: SidecarStatus
  memory_limit_bytes: number | null
  running_cpus: number | null
  disk_usage_bytes: { total?: number }
  idle_minutes: number | null
  image_matches: boolean
}

function formatBytes(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

function userPolicyLabel(allowed: boolean | null | undefined, t: (k: string) => string) {
  if (allowed === true) return t('workspace.userPolicyAllow')
  if (allowed === false) return t('workspace.userPolicyDeny')
  return t('workspace.userPolicyAuto')
}

function modeBadge(mode: string, running?: boolean) {
  if (mode === 'container' && running) {
    return <Badge variant="success">container</Badge>
  }
  if (mode === 'container') {
    return <Badge variant="warning">container (stopped)</Badge>
  }
  return <Badge variant="default">local</Badge>
}

export function WorkspacePage() {
  const { t } = useTranslation()
  const [channels, setChannels] = useState<ChannelWorkspaceRow[]>([])
  const [users, setUsers] = useState<UserWorkspaceRow[]>([])
  const [sidecars, setSidecars] = useState<SidecarRow[]>([])
  const [runtime, setRuntime] = useState<RuntimeSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [savingUserId, setSavingUserId] = useState<string | null>(null)
  const [userDrafts, setUserDrafts] = useState<Record<string, { memory: string; cpus: string; policy: string }>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ch, sc, rt, us] = await Promise.all([
        api.get<ChannelWorkspaceRow[]>('/workspace/channels'),
        api.get<SidecarRow[]>('/workspace/sidecars'),
        api.get<RuntimeSettings>('/workspace/settings/runtime'),
        api.get<UserWorkspaceRow[]>('/workspace/users').catch(() => []),
      ])
      setChannels(ch)
      setSidecars(sc)
      setRuntime(rt)
      setUsers(us)
      setUserDrafts(
        Object.fromEntries(
          us.map((u) => [
            u.user_id,
            {
              memory: u.workspace_sidecar_memory || '',
              cpus: u.workspace_sidecar_cpus || '',
              policy:
                u.workspace_container_allowed === true
                  ? 'allow'
                  : u.workspace_container_allowed === false
                    ? 'deny'
                    : 'auto',
            },
          ]),
        ),
      )
    } catch (e) {
      toast.error(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const updateMode = async (customerId: string, workspace_mode: string | null) => {
    setSavingId(customerId)
    try {
      const updated = await api.patch<ChannelWorkspaceRow>(
        `/workspace/channels/${customerId}`,
        { workspace_mode: workspace_mode === 'auto' ? null : workspace_mode },
      )
      setChannels((rows) =>
        rows.map((r) => (r.customer_id === customerId ? updated : r)),
      )
      toast.success(t('workspace.modeUpdated'))
    } catch (e) {
      toast.error(String(e))
    } finally {
      setSavingId(null)
    }
  }

  const recycleUser = async (userId: string) => {
    try {
      const res = await api.post<{ message: string }>(`/workspace/sidecars/${userId}/recycle`, {})
      toast.success(res.message || t('workspace.recycled'))
      await load()
    } catch (e) {
      toast.error(String(e))
    }
  }

  const recycleIdle = async () => {
    try {
      const res = await api.post<{ message: string; removed: number }>(
        '/workspace/sidecars/recycle-idle',
        {},
      )
      toast.success(res.message)
      await load()
    } catch (e) {
      toast.error(String(e))
    }
  }

  const saveUserWorkspace = async (userId: string) => {
    const draft = userDrafts[userId]
    if (!draft) return
    setSavingUserId(userId)
    try {
      await api.patch(`/workspace/users/${userId}`, {
        workspace_container_allowed:
          draft.policy === 'auto' ? null : draft.policy === 'allow',
        workspace_sidecar_memory: draft.memory.trim() || '',
        workspace_sidecar_cpus: draft.cpus.trim() || '',
      })
      toast.success(t('workspace.userUpdated'))
      await load()
    } catch (e) {
      toast.error(String(e))
    } finally {
      setSavingUserId(null)
    }
  }

  const formatMemoryLimit = (bytes: number | null | undefined) => {
    if (!bytes) return '—'
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
    return `${Math.round(bytes / (1024 * 1024))} MB`
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Container className="w-7 h-7" />
            {t('workspace.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('workspace.pageSubtitle')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" />
            {t('common.refresh')}
          </Button>
          <Button variant="outline" onClick={recycleIdle}>
            {t('workspace.recycleIdle')}
          </Button>
        </div>
      </div>

      {runtime && (
        <Card>
          <CardHeader>{t('workspace.runtimeTitle')}</CardHeader>
          <CardContent className="text-sm text-gray-600 dark:text-gray-300 space-y-1">
            <p>
              {t('workspace.containerEnabled')}:{' '}
              <strong>{runtime.workspace_container_enabled ? t('common.enabled') : t('common.disabled')}</strong>
            </p>
            <p>
              {t('workspace.containerImage')}: <code>{runtime.workspace_container_image}</code>
            </p>
            <p>
              {t('workspace.idleRecycle')}:{' '}
              {runtime.workspace_sidecar_recycle_enabled
                ? t('workspace.idleMinutes', { n: runtime.workspace_sidecar_idle_minutes })
                : t('workspace.idleDisabled')}
            </p>
            <p>
              {t('workspace.defaultMemory')}:{' '}
              <code>{runtime.workspace_container_memory || t('workspace.unlimited')}</code>
              {' · '}
              {t('workspace.defaultCpus')}:{' '}
              <code>{runtime.workspace_container_cpus || t('workspace.unlimited')}</code>
            </p>
          </CardContent>
        </Card>
      )}

      {users.length > 0 && (
        <Card>
          <CardHeader>{t('workspace.usersTitle')}</CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 pr-4">{t('workspace.colUser')}</th>
                  <th className="py-2 pr-4">{t('workspace.colUserPolicy')}</th>
                  <th className="py-2 pr-4">{t('workspace.colSkillAuthor')}</th>
                  <th className="py-2 pr-4">{t('workspace.colSidecar')}</th>
                  <th className="py-2 pr-4">{t('workspace.colMemory')}</th>
                  <th className="py-2 pr-4">{t('workspace.colCpus')}</th>
                  <th className="py-2 pr-4">{t('workspace.colDisk')}</th>
                  <th className="py-2">{t('workspace.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const draft = userDrafts[u.user_id] || { memory: '', cpus: '', policy: 'auto' }
                  return (
                    <tr key={u.user_id} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-3 pr-4">
                        <div className="font-medium">{u.username}</div>
                        <div className="text-xs text-gray-400 font-mono">{u.user_id.slice(0, 8)}…</div>
                      </td>
                      <td className="py-3 pr-4">
                        <Select
                          value={draft.policy}
                          onChange={(e) =>
                            setUserDrafts((prev) => ({
                              ...prev,
                              [u.user_id]: { ...draft, policy: e.target.value },
                            }))
                          }
                          options={[
                            { value: 'auto', label: t('workspace.userPolicyAuto') },
                            { value: 'allow', label: t('workspace.userPolicyAllow') },
                            { value: 'deny', label: t('workspace.userPolicyDeny') },
                          ]}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        {u.tenant_skill_authoring ? (
                          <Badge variant="success">{t('common.enabled')}</Badge>
                        ) : (
                          <Badge variant="default">{t('common.disabled')}</Badge>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {u.sidecar?.running ? (
                          <Badge variant="success">{t('workspace.running')}</Badge>
                        ) : u.container_name ? (
                          <span className="text-xs text-gray-500">{t('workspace.stopped')}</span>
                        ) : (
                          '—'
                        )}
                        {u.memory_limit_bytes != null && (
                          <div className="text-xs text-gray-400 mt-1">
                            {formatMemoryLimit(u.memory_limit_bytes)}
                            {u.running_cpus != null ? ` · ${u.running_cpus} CPU` : ''}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        <Input
                          value={draft.memory}
                          placeholder={u.effective_memory || '512m'}
                          onChange={(e) =>
                            setUserDrafts((prev) => ({
                              ...prev,
                              [u.user_id]: { ...draft, memory: e.target.value },
                            }))
                          }
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <Input
                          value={draft.cpus}
                          placeholder={u.effective_cpus || '1.0'}
                          onChange={(e) =>
                            setUserDrafts((prev) => ({
                              ...prev,
                              [u.user_id]: { ...draft, cpus: e.target.value },
                            }))
                          }
                        />
                      </td>
                      <td className="py-3 pr-4">{formatBytes(u.disk_usage_bytes?.total)}</td>
                      <td className="py-3">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            isLoading={savingUserId === u.user_id}
                            onClick={() => saveUserWorkspace(u.user_id)}
                          >
                            {t('common.save')}
                          </Button>
                          {u.container_name && (
                            <Button size="sm" variant="outline" onClick={() => recycleUser(u.user_id)}>
                              {t('workspace.recycle')}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>{t('workspace.channelsTitle')}</CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                <th className="py-2 pr-4">{t('workspace.colAgent')}</th>
                <th className="py-2 pr-4">{t('workspace.colPlan')}</th>
                <th className="py-2 pr-4">{t('workspace.colAssign')}</th>
                <th className="py-2 pr-4">{t('workspace.colUserPolicy')}</th>
                <th className="py-2 pr-4">{t('workspace.colEffective')}</th>
                <th className="py-2 pr-4">{t('workspace.colSidecar')}</th>
                <th className="py-2 pr-4">{t('workspace.colDisk')}</th>
                <th className="py-2 pr-4">{t('workspace.colIdle')}</th>
                <th className="py-2">{t('workspace.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((row) => (
                <tr key={row.customer_id} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-3 pr-4 font-medium">{row.customer_name}</td>
                  <td className="py-3 pr-4">{row.plan}</td>
                  <td className="py-3 pr-4">
                    <Select
                      value={row.workspace_mode || 'auto'}
                      disabled={savingId === row.customer_id}
                      onChange={(e) => updateMode(row.customer_id, e.target.value)}
                      options={[
                        { value: 'auto', label: t('workspace.modeAuto') },
                        { value: 'local', label: t('workspace.modeLocal') },
                        { value: 'container', label: t('workspace.modeContainer') },
                      ]}
                    />
                  </td>
                  <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                    {userPolicyLabel(row.user_container_allowed, t)}
                  </td>
                  <td className="py-3 pr-4">
                    {modeBadge(row.effective_mode, row.sidecar?.running)}
                    {row.fallback_reason && (
                      <span
                        className="ml-2 text-xs text-amber-600 dark:text-amber-400"
                        title={t(`workspace.fallback.${row.fallback_reason}`)}
                      >
                        ({t(`workspace.fallback.${row.fallback_reason}`)})
                      </span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    {row.container_name ? (
                      <span className="font-mono text-xs">{row.container_name}</span>
                    ) : (
                      '—'
                    )}
                    {row.sidecar?.running && (
                      <Badge variant="success" className="ml-2">
                        {t('workspace.running')}
                      </Badge>
                    )}
                  </td>
                  <td className="py-3 pr-4">{formatBytes(row.disk_usage_bytes?.total)}</td>
                  <td className="py-3 pr-4">
                    {row.idle_minutes != null ? `${row.idle_minutes}m` : '—'}
                  </td>
                  <td className="py-3">
                    {row.requested_mode === 'container' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => recycleUser(row.user_id)}
                      >
                        {t('workspace.recycle')}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {channels.length === 0 && (
            <p className="text-gray-500 py-6 text-center">{t('workspace.noChannels')}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex items-center gap-2">
          <Server className="w-5 h-5" />
          {t('workspace.sidecarsTitle')}
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                <th className="py-2 pr-4">{t('workspace.colContainer')}</th>
                <th className="py-2 pr-4">{t('workspace.colUser')}</th>
                <th className="py-2 pr-4">{t('workspace.colStatus')}</th>
                <th className="py-2 pr-4">{t('workspace.colImage')}</th>
                <th className="py-2 pr-4">{t('workspace.colMemory')}</th>
                <th className="py-2 pr-4">{t('workspace.colIdle')}</th>
                <th className="py-2">{t('workspace.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {sidecars.map((s) => (
                <tr key={s.container_name} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-3 pr-4 font-mono text-xs">{s.container_name}</td>
                  <td className="py-3 pr-4 font-mono text-xs">{s.user_id || '—'}</td>
                  <td className="py-3 pr-4">{s.status}</td>
                  <td className="py-3 pr-4">
                    <span className={s.image_matches ? '' : 'text-amber-600'}>{s.image}</span>
                    {!s.image_matches && (
                      <Badge variant="warning" className="ml-2">
                        {t('workspace.imageMismatch')}
                      </Badge>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-xs">
                    {s.configured_memory || '—'}
                    {s.memory_limit_bytes ? ` (${formatMemoryLimit(s.memory_limit_bytes)})` : ''}
                    {s.configured_cpus ? ` · ${s.configured_cpus} CPU` : ''}
                  </td>
                  <td className="py-3 pr-4">
                    {s.idle_minutes != null ? `${s.idle_minutes}m` : '—'}
                  </td>
                  <td className="py-3">
                    <Button size="sm" variant="outline" onClick={() => recycleUser(s.user_id)}>
                      {t('workspace.recycle')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sidecars.length === 0 && (
            <p className="text-gray-500 py-6 text-center">{t('workspace.noSidecars')}</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
