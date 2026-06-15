import React, { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, UserPlus, Shield, ChevronDown, ChevronUp, KeyRound } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { ChangePasswordForm } from '@/components/admin/ChangePasswordForm'
import { formatDate } from '@/lib/utils'
import { ALL_PERMISSIONS, PERMISSION_LABELS, FALLBACK_ROLE_PERMISSIONS } from '@/lib/permissions'

interface SkillOption {
  id: string
  name: string
  description: string | null
}

interface UserRow {
  id: string
  username: string
  role: 'admin' | 'agent'
  display_name: string | null
  skill_ids: string[] | null
  workspace_container_allowed?: boolean | null
  created_at: string
}

export function UsersPage() {
  const { t } = useTranslation()
  const currentUser = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<UserRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [expandedPerms, setExpandedPerms] = useState<Set<string>>(new Set())
  const [rolePermsData, setRolePermsData] = useState<Record<string, string[]>>(FALLBACK_ROLE_PERMISSIONS)
  const [permsLoaded, setPermsLoaded] = useState(false)
  const [showPasswordDialog, setShowPasswordDialog] = useState(false)
  const [resetPasswordUser, setResetPasswordUser] = useState<UserRow | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState('')
  const [resettingPassword, setResettingPassword] = useState(false)
  const [skills, setSkills] = useState<SkillOption[]>([])
  const [skillEditUser, setSkillEditUser] = useState<UserRow | null>(null)
  const [form, setForm] = useState({
    username: '',
    password: '',
    role: 'agent',
    display_name: '',
  })

  const loadUsers = async () => {
    try {
      const data = await api.get<UserRow[]>('/auth/users')
      setUsers(data)
    } catch (err) {
      console.error(err)
      toast(t('users.loadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const loadRolePerms = useCallback(async () => {
    try {
      const data = await api.get<{ role_permissions: Record<string, string[]> }>('/settings/role-permissions')
      if (data.role_permissions && Object.keys(data.role_permissions).length > 0) {
        setRolePermsData(data.role_permissions)
      }
    } catch (err) {
      console.error('Failed to load role permissions:', err)
    } finally {
      setPermsLoaded(true)
    }
  }, [])

  useEffect(() => {
    void loadUsers()
    void loadRolePerms()
    void api.get<SkillOption[]>('/skills').then(setSkills).catch(() => {})
  }, [])

  const getRolePerms = (role: string): string[] => {
    return rolePermsData[role] || FALLBACK_ROLE_PERMISSIONS[role] || []
  }

  const knownRoles = Object.keys(rolePermsData).length > 0
    ? Object.keys(rolePermsData)
    : Object.keys(FALLBACK_ROLE_PERMISSIONS)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.post('/auth/users', {
        username: form.username,
        password: form.password,
        role: form.role,
        display_name: form.display_name || form.username,
      })
      toast(t('users.created'), { type: 'success' })
      setForm({ username: '', password: '', role: 'agent', display_name: '' })
      setShowCreate(false)
      await loadUsers()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : t('users.createFailed'), {
        type: 'error',
      })
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (user: UserRow) => {
    if (!window.confirm(t('users.deleteConfirm', { name: user.username }))) return
    try {
      await api.delete(`/auth/users/${user.id}`)
      toast(t('users.deleted'), { type: 'success' })
      await loadUsers()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : t('users.deleteFailed'), {
        type: 'error',
      })
    }
  }

  const handleSkillChange = async (user: UserRow, skillIds: string[] | null) => {
    try {
      await api.patch(`/auth/users/${user.id}`, { skill_ids: skillIds })
      toast(t('users.updated'), { type: 'success' })
      await loadUsers()
      // Update the open dialog user so checkboxes reflect the change immediately
      setSkillEditUser((prev) => (prev && prev.id === user.id ? { ...prev, skill_ids: skillIds } : prev))
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : t('users.updateFailed'), { type: 'error' })
    }
  }

  const handleRoleChange = async (user: UserRow, role: string) => {
    try {
      await api.patch(`/auth/users/${user.id}`, { role })
      toast(t('users.updated'), { type: 'success' })
      await loadUsers()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : t('users.updateFailed'), {
        type: 'error',
      })
    }
  }

  const handleContainerPolicyChange = async (
    user: UserRow,
    value: string,
  ) => {
    const workspace_container_allowed =
      value === 'auto' ? null : value === 'allow' ? true : false
    try {
      await api.patch(`/auth/users/${user.id}`, { workspace_container_allowed })
      toast(t('users.updated'), { type: 'success' })
      await loadUsers()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : t('users.updateFailed'), {
        type: 'error',
      })
    }
  }

  const containerPolicyValue = (allowed: boolean | null | undefined) => {
    if (allowed === true) return 'allow'
    if (allowed === false) return 'deny'
    return 'auto'
  }

  const openResetPasswordDialog = (user: UserRow) => {
    setResetPasswordUser(user)
    setResetPassword('')
    setResetPasswordConfirm('')
  }

  const closeResetPasswordDialog = () => {
    if (resettingPassword) return
    setResetPasswordUser(null)
    setResetPassword('')
    setResetPasswordConfirm('')
  }

  const handleResetUserPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetPasswordUser) return
    if (resetPassword !== resetPasswordConfirm) {
      toast(t('users.passwordMismatch'), { type: 'error' })
      return
    }
    setResettingPassword(true)
    try {
      await api.patch(`/auth/users/${resetPasswordUser.id}`, {
        password: resetPassword,
      })
      toast(t('users.userPasswordChanged', { name: resetPasswordUser.username }), {
        type: 'success',
      })
      closeResetPasswordDialog()
    } catch (err: unknown) {
      toast(
        err instanceof Error ? err.message : t('users.userPasswordChangeFailed'),
        { type: 'error' },
      )
    } finally {
      setResettingPassword(false)
    }
  }

  if (currentUser?.role !== 'admin') {
    return (
      <div className="text-center py-20 text-gray-500 dark:text-gray-400">{t('users.adminOnly')}</div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('users.title')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('users.subtitle')}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant="secondary"
            leftIcon={<KeyRound className="w-4 h-4" />}
            onClick={() => setShowPasswordDialog(true)}
          >
            {t('users.changePassword')}
          </Button>
          <Button
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={() => setShowCreate((v) => !v)}
          >
            {t('users.createUser')}
          </Button>
        </div>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-gray-900 dark:text-gray-100 font-medium">
              <UserPlus className="w-5 h-5" />
              {t('users.createUser')}
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid gap-4 sm:grid-cols-2 max-w-2xl">
              <Input
                label={t('auth.username')}
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                pattern="[a-zA-Z0-9_]+"
                required
              />
              <Input
                label={t('users.displayName')}
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              />
              <Input
                label={t('auth.password')}
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                minLength={6}
                required
              />
              <Input
                label={t('users.role')}
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                list="role-options-create"
                placeholder="admin / agent / custom"
              />
              <datalist id="role-options-create">
                {knownRoles.map((r) => (
                  <option key={r} value={r} />
                ))}
              </datalist>
              <div className="sm:col-span-2 flex gap-2">
                <Button type="submit" isLoading={creating}>
                  {t('users.createUser')}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setShowCreate(false)}>
                  {t('users.cancel')}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>{t('users.listTitle')}</CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner size="md" />
            </div>
          ) : users.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">{t('users.empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
                    <th className="py-2 pr-4">{t('auth.username')}</th>
                    <th className="py-2 pr-4">{t('users.displayName')}</th>
                    <th className="py-2 pr-4">{t('users.role')}</th>
                    <th className="py-2 pr-4">{t('users.workspaceContainer')}</th>
                    <th className="py-2 pr-4">{t('users.permissions')}</th>
                    <th className="py-2 pr-4">{t('users.skills')}</th>
                    <th className="py-2 pr-4">{t('users.createdAt')}</th>
                    <th className="py-2">{t('users.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      className="border-b border-gray-100 dark:border-gray-800"
                    >
                      <td className="py-3 pr-4 font-medium text-gray-900 dark:text-gray-100">
                        {user.username}
                        {user.id === currentUser?.id && (
                          <Badge variant="info" size="sm" className="ml-2">
                            {t('users.you')}
                          </Badge>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                        {user.display_name || '—'}
                      </td>
                      <td className="py-3 pr-4">
                        <Select
                          value={user.role}
                          onChange={(e) => handleRoleChange(user, e.target.value)}
                          disabled={user.id === currentUser?.id}
                          options={knownRoles.map((r) => ({ value: r, label: r }))}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <Select
                          value={containerPolicyValue(user.workspace_container_allowed)}
                          onChange={(e) =>
                            handleContainerPolicyChange(user, e.target.value)
                          }
                          options={[
                            { value: 'auto', label: t('users.workspaceContainerAuto') },
                            { value: 'allow', label: t('users.workspaceContainerAllow') },
                            { value: 'deny', label: t('users.workspaceContainerDeny') },
                          ]}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <button
                          type="button"
                          onClick={() => {
                            const next = new Set(expandedPerms)
                            if (next.has(user.id)) next.delete(user.id)
                            else next.add(user.id)
                            setExpandedPerms(next)
                          }}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400"
                        >
                          <Shield className="w-3.5 h-3.5" />
                          {(getRolePerms(user.role)).length}
                          {expandedPerms.has(user.id) ? (
                            <ChevronUp className="w-3 h-3" />
                          ) : (
                            <ChevronDown className="w-3 h-3" />
                          )}
                        </button>
                        {expandedPerms.has(user.id) && (
                          <div className="mt-2 flex flex-wrap gap-1 max-w-48">
                            {getRolePerms(user.role).map((perm) => (
                              <span key={perm} title={PERMISSION_LABELS[perm] || perm}>
                                <Badge variant="info" size="sm">
                                  {perm}
                                </Badge>
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {user.role === 'admin' ? (
                          <Badge variant="default" size="sm">{t('users.allSkills')}</Badge>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setSkillEditUser(user)}
                            className="text-xs text-primary-600 hover:underline"
                          >
                            {user.skill_ids === null
                              ? t('users.unlimited')
                              : user.skill_ids?.length
                                ? `${user.skill_ids.length} skills`
                                : t('users.none')}
                          </button>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-gray-500 dark:text-gray-400">
                        {formatDate(user.created_at)}
                      </td>
                      <td className="py-3">
                        <button
                          type="button"
                          disabled={user.id === currentUser?.id}
                          onClick={() => openResetPasswordDialog(user)}
                          className="p-2 rounded-lg text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 disabled:opacity-40"
                          title={t('users.resetUserPassword')}
                        >
                          <KeyRound className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          disabled={user.id === currentUser?.id}
                          onClick={() => handleDelete(user)}
                          className="p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40"
                          title={t('users.delete')}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={showPasswordDialog}
        onClose={() => setShowPasswordDialog(false)}
        title={t('users.changePassword')}
        size="sm"
      >
        <ChangePasswordForm />
      </Dialog>

      <Dialog
        open={Boolean(resetPasswordUser)}
        onClose={closeResetPasswordDialog}
        title={t('users.resetUserPassword')}
        size="sm"
      >
        <form onSubmit={handleResetUserPassword} className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('users.resetUserPasswordHint', {
              name: resetPasswordUser?.display_name || resetPasswordUser?.username || '',
            })}
          </p>
          <Input
            label={t('users.newPassword')}
            type="password"
            value={resetPassword}
            onChange={(e) => setResetPassword(e.target.value)}
            minLength={6}
            autoComplete="new-password"
            required
          />
          <Input
            label={t('users.confirmPassword')}
            type="password"
            value={resetPasswordConfirm}
            onChange={(e) => setResetPasswordConfirm(e.target.value)}
            minLength={6}
            autoComplete="new-password"
            required
          />
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="secondary" onClick={closeResetPasswordDialog}>
              {t('users.cancel')}
            </Button>
            <Button type="submit" isLoading={resettingPassword}>
              {t('users.resetUserPassword')}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={Boolean(skillEditUser)}
        onClose={() => setSkillEditUser(null)}
        title={t('users.editSkills', { name: skillEditUser?.display_name || skillEditUser?.username || '' })}
        size="sm"
      >
        <div className="space-y-3 max-h-[60vh] overflow-y-auto">
          <div className="flex flex-wrap gap-2">
            {skills.map((sk) => {
              const ids: string[] | null = skillEditUser?.skill_ids ?? null
              const checked = ids === null || ids.includes(sk.id)
              return (
                <label
                  key={sk.id}
                  className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 px-3 py-2 rounded border border-gray-200 dark:border-gray-600 min-w-[220px] flex-1"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      if (!skillEditUser) return
                      const cur = skillEditUser.skill_ids
                      if (cur === null || cur === undefined) {
                        // Coming from unlimited: start with all skills then toggle this one off/on
                        const allIds = skills.map((s) => s.id)
                        handleSkillChange(skillEditUser, checked ? allIds.filter((id: string) => id !== sk.id) : allIds)
                      } else {
                        handleSkillChange(
                          skillEditUser,
                          checked ? cur.filter((id: string) => id !== sk.id) : [...cur, sk.id]
                        )
                      }
                    }}
                    className="rounded"
                  />
                  <div className="min-w-0">
                    <div className="font-medium truncate">{sk.name}</div>
                    {sk.description && <div className="text-xs text-gray-400 truncate">{sk.description}</div>}
                  </div>
                </label>
              )
            })}
          </div>
          <div className="flex gap-3 pt-3 border-t">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => { if (skillEditUser) handleSkillChange(skillEditUser, null) }}
            >
              {t('users.unlimited')}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => { if (skillEditUser) handleSkillChange(skillEditUser, []) }}
            >
              {t('users.none')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
