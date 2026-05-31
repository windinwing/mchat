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

interface UserRow {
  id: string
  username: string
  role: 'admin' | 'agent'
  display_name: string | null
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

  if (currentUser?.role !== 'admin') {
    return (
      <div className="text-center py-20 text-gray-500 dark:text-gray-400">{t('users.adminOnly')}</div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('users.title')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('users.subtitle')}
          </p>
        </div>
        <div className="flex gap-2">
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
            className="w-[150px]"
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
                    <th className="py-2 pr-4">{t('users.permissions')}</th>
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
                      <td className="py-3 pr-4 text-gray-500 dark:text-gray-400">
                        {formatDate(user.created_at)}
                      </td>
                      <td className="py-3">
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
    </div>
  )
}
