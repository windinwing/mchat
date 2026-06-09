import React, { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Lock, PlusCircle, XCircle, Puzzle } from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { ALL_PERMISSIONS, PERMISSION_LABELS, FALLBACK_ROLE_PERMISSIONS } from '@/lib/permissions'

export function RolesPage() {
  const { t } = useTranslation()
  const [rolePermsData, setRolePermsData] = useState<Record<string, string[]>>(FALLBACK_ROLE_PERMISSIONS)
  const [rolePermsEditing, setRolePermsEditing] = useState(false)
  const [rolePermsDraft, setRolePermsDraft] = useState<Record<string, string[]>>({})
  const [savingPerms, setSavingPerms] = useState(false)
  const [permsLoaded, setPermsLoaded] = useState(false)
  const [newRoleName, setNewRoleName] = useState('')
  const [skills, setSkills] = useState<Array<{ id: string; name: string; description: string | null }>>([])
  const [roleDefaultSkills, setRoleDefaultSkills] = useState<Record<string, string[]>>({})
  const [savingDefaults, setSavingDefaults] = useState(false)

  const loadRoleDefaultSkills = useCallback(async () => {
    try {
      const data = await api.get<{ key: string; value: Record<string, string[]> }>('/settings/key-value/role_default_skills')
      if (data.value && typeof data.value === 'object') {
        setRoleDefaultSkills(data.value)
      }
    } catch {
      // 404 = no defaults configured yet, start empty
    }
  }, [])

  const loadSkills = useCallback(async () => {
    try {
      const data = await api.get<Array<{ id: string; name: string; description: string | null }>>('/skills')
      setSkills(data)
    } catch { /* ignore */ }
  }, [])

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
    void loadRolePerms()
    void loadSkills()
    void loadRoleDefaultSkills()
  }, [loadRolePerms, loadSkills, loadRoleDefaultSkills])

  const startEditPerms = () => {
    setRolePermsDraft(JSON.parse(JSON.stringify(rolePermsData)))
    setRolePermsEditing(true)
  }

  const addNewRole = () => {
    const name = newRoleName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_')
    if (!name || name.length < 2) {
      toast(t('users.invalidRoleName'), { type: 'error' })
      return
    }
    if (rolePermsDraft[name]) {
      toast(t('users.roleAlreadyExists'), { type: 'error' })
      return
    }
    setRolePermsDraft(prev => ({ ...prev, [name]: [] }))
    setNewRoleName('')
  }

  const deleteRole = (role: string) => {
    if (role === 'admin') {
      toast(t('users.cannotDeleteAdmin'), { type: 'error' })
      return
    }
    setRolePermsDraft(prev => {
      const next = { ...prev }
      delete next[role]
      return next
    })
  }

  const togglePerm = (role: string, perm: string) => {
    setRolePermsDraft(prev => {
      const current = prev[role] || []
      const next = current.includes(perm)
        ? current.filter(p => p !== perm)
        : [...current, perm]
      return { ...prev, [role]: next }
    })
  }

  const saveRolePerms = async () => {
    setSavingPerms(true)
    try {
      const data = await api.put<{ role_permissions: Record<string, string[]> }>(
        '/settings/role-permissions',
        { role_permissions: rolePermsDraft }
      )
      setRolePermsData(data.role_permissions)
      setRolePermsEditing(false)
      toast(t('users.rolePermsSaved'), { type: 'success' })
    } catch (err: any) {
      toast(err.message || t('users.rolePermsSaveFailed'), { type: 'error' })
    } finally {
      setSavingPerms(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {t('roles.pageTitle')}
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('users.subtitle')}
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2 text-gray-900 dark:text-gray-100 font-medium">
              <Lock className="w-5 h-5" />
              {t('users.rolePermsTitle')}
            </div>
            {!rolePermsEditing ? (
              <Button variant="secondary" size="sm" onClick={startEditPerms}>
                {t('common.edit')}
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => setRolePermsEditing(false)}>
                  {t('common.cancel')}
                </Button>
                <Button size="sm" onClick={saveRolePerms} isLoading={savingPerms}>
                  {t('common.save')}
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {!permsLoaded ? (
            <div className="flex justify-center py-4">
              <Spinner size="sm" />
            </div>
          ) : (
            <div className="space-y-6">
              {rolePermsEditing && (
                <div className="flex items-end gap-2">
                  <Input
                    label={t('users.newRole')}
                    value={newRoleName}
                    onChange={(e) => setNewRoleName(e.target.value)}
                    placeholder={t('users.newRolePlaceholder')}
                    className="max-w-40"
                    onKeyDown={(e) => e.key === 'Enter' && addNewRole()}
                  />
                  <Button size="sm" onClick={addNewRole} leftIcon={<PlusCircle className="w-4 h-4" />} className="w-[120px]">
                    {t('common.create')}
                  </Button>
                </div>
              )}

              {Object.keys(rolePermsEditing ? rolePermsDraft : rolePermsData).map((role) => {
                const perms = rolePermsEditing ? (rolePermsDraft[role] || []) : (rolePermsData[role] || [])
                return (
                  <div key={role}>
                    <div className="flex items-center gap-2 mb-3">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {role}
                      </h4>
                      <Badge variant={role === 'admin' ? 'danger' : 'info'} size="sm">
                        {perms.length} {t('users.permissions')}
                      </Badge>
                      {rolePermsEditing && role !== 'admin' && (
                        <button
                          type="button"
                          onClick={() => deleteRole(role)}
                          className="p-0.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                          title={t('users.deleteRole')}
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {ALL_PERMISSIONS.map((perm) => {
                        const checked = perms.includes(perm)
                        return (
                          <label
                            key={perm}
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                              rolePermsEditing
                                ? 'hover:border-primary-300 dark:hover:border-primary-600'
                                : 'cursor-default'
                            } ${
                              checked
                                ? 'border-primary-300 dark:border-primary-600 bg-primary-50 dark:bg-primary-900/20 text-gray-900 dark:text-gray-100'
                                : 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500'
                            }`}
                          >
                            {rolePermsEditing && (
                              <Switch
                                checked={checked}
                                onChange={() => togglePerm(role, perm)}
                              />
                            )}
                            <span className="truncate" title={PERMISSION_LABELS[perm] || perm}>
                              {perm}
                            </span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-gray-900 dark:text-gray-100 font-medium">
              <Puzzle className="w-5 h-5" />
              {t('users.roleDefaultSkills')}
            </div>
            <Button
              size="sm"
              isLoading={savingDefaults}
              onClick={async () => {
                setSavingDefaults(true)
                try {
                  await api.put('/settings/key-value', {
                    key: 'role_default_skills',
                    value: roleDefaultSkills,
                  })
                  toast(t('users.roleDefaultSkillsSaved'), { type: 'success' })
                } catch {
                  toast(t('users.roleDefaultSkillsSaveFailed'), { type: 'error' })
                } finally {
                  setSavingDefaults(false)
                }
              }}
            >
              {t('common.save')}
            </Button>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('users.roleDefaultSkillsHint')}</p>
        </CardHeader>
        <CardContent>
          {Object.keys(rolePermsData).map((role) => {
            const currentIds = roleDefaultSkills[role] || []
            return (
              <div key={role} className="mb-4 last:mb-0">
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant={role === 'admin' ? 'danger' : 'info'} size="sm">{role}</Badge>
                  <button
                    type="button"
                    onClick={() => setRoleDefaultSkills({ ...roleDefaultSkills, [role]: undefined as unknown as string[] })}
                    className="text-xs text-gray-400 hover:text-red-500"
                  >
                    {t('users.unlimited')}
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {skills.map((sk) => {
                    const checked = currentIds === undefined || currentIds.includes(sk.id)
                    return (
                      <label
                        key={sk.id}
                        className={`flex items-center gap-1.5 text-xs cursor-pointer px-2.5 py-1.5 rounded-full border transition-colors ${
                          checked
                            ? 'border-primary-300 bg-primary-50 dark:bg-primary-900/20 text-primary-700'
                            : 'border-gray-200 dark:border-gray-700 text-gray-500'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const ids = roleDefaultSkills[role]
                            if (ids === undefined) {
                              setRoleDefaultSkills({ ...roleDefaultSkills, [role]: [sk.id] })
                            } else {
                              setRoleDefaultSkills({
                                ...roleDefaultSkills,
                                [role]: checked ? ids.filter((id) => id !== sk.id) : [...ids, sk.id],
                              })
                            }
                          }}
                          className="sr-only"
                        />
                        {sk.name}
                      </label>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </CardContent>
      </Card>
    </div>
  )
}
