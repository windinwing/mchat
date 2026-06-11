import { useEffect, useState } from 'react'
import type { TFunction } from 'i18next'
import { Clock3, Plus, Settings2, Trash2, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'

interface GroupRow {
  id: string
  name: string
  description?: string | null
  owner_user_id: string
  member_count: number
  current_user_role?: string | null
  default_skill_ids?: string[] | null
  devbridge_project_allowlists?: Record<string, string[]> | null
}

interface DevBridgeProviderOption {
  key: string
  title: string
  enabled: boolean
}

function resolveGroupAllowlists(group: GroupRow): Record<string, string[]> {
  return group.devbridge_project_allowlists || {}
}

function countAllowlistedProjects(allowlists: Record<string, string[]> | null | undefined): number {
  if (!allowlists) return 0
  return Object.values(allowlists).reduce((sum, slugs) => sum + (slugs?.length || 0), 0)
}

interface GroupMemberRow {
  id: string
  user_id: string
  username?: string | null
  display_name?: string | null
  user_role?: string | null
  role: string
}

interface UserOption {
  id: string
  username: string
  display_name?: string | null
  role?: string
}

function accountRoleLabel(role: string | null | undefined, t: TFunction): string {
  if (role === 'admin') return t('groups.accountRoleAdmin')
  if (role === 'agent') return t('groups.accountRoleAgent')
  if (role === 'user') return t('groups.accountRoleUser')
  return role || '—'
}

function groupRoleLabel(role: string, t: TFunction): string {
  if (role === 'owner') return t('groups.roleOwner')
  if (role === 'editor') return t('groups.roleEditor')
  if (role === 'member') return t('groups.roleMember')
  return role
}

function userOptionLabel(user: UserOption, t: TFunction): string {
  const name = user.display_name || user.username
  const role = accountRoleLabel(user.role, t)
  return `${name} · ${role}`
}

interface SkillOption {
  id: string
  name: string
  description?: string | null
}

interface ProjectOption {
  slug: string
  name: string
  has_build: boolean
}

export function GroupsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const currentUser = useAuthStore((s) => s.user)
  const [groups, setGroups] = useState<GroupRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [users, setUsers] = useState<UserOption[]>([])
  const [memberDialogGroup, setMemberDialogGroup] = useState<GroupRow | null>(null)
  const [settingsDialogGroup, setSettingsDialogGroup] = useState<GroupRow | null>(null)
  const [members, setMembers] = useState<GroupMemberRow[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [selectedRole, setSelectedRole] = useState('member')
  const [savingMember, setSavingMember] = useState(false)
  const [updatingMemberRoleId, setUpdatingMemberRoleId] = useState<string | null>(null)
  const [deletingGroupId, setDeletingGroupId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '' })
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const [providerOptions, setProviderOptions] = useState<DevBridgeProviderOption[]>([])
  const [selectedProviderKey, setSelectedProviderKey] = useState('')
  const [projectOptions, setProjectOptions] = useState<ProjectOption[]>([])
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([])
  const [allowlistsByProvider, setAllowlistsByProvider] = useState<Record<string, string[]>>({})

  const loadGroups = async () => {
    setLoading(true)
    try {
      const data = await api.get<GroupRow[]>('/groups')
      setGroups(data || [])
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.loadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const loadUsers = async () => {
    try {
      const data = await api.get<UserOption[]>('/auth/users')
      setUsers(data || [])
    } catch {
      setUsers([])
    }
  }

  const pickDefaultMemberUserId = (
    memberRows: GroupMemberRow[],
    userOptions: UserOption[],
  ): string => {
    const existing = new Set(memberRows.map((m) => m.user_id))
    return userOptions.find((u) => !existing.has(u.id))?.id ?? ''
  }

  const loadMembers = async (group: GroupRow) => {
    setMemberDialogGroup(group)
    setMembersLoading(true)
    setSelectedRole('member')
    try {
      const data = await api.get<GroupMemberRow[]>(`/groups/${group.id}/members`)
      const rows = data || []
      setMembers(rows)
      setSelectedUserId(pickDefaultMemberUserId(rows, users))
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.membersLoadFailed'), { type: 'error' })
      setMembers([])
    } finally {
      setMembersLoading(false)
    }
  }

  const loadProviderProjects = async (providerKey: string) => {
    if (!providerKey) {
      setProjectOptions([])
      return
    }
    setProjectsLoading(true)
    try {
      const projects = await api.get<ProjectOption[]>(`/devbridge/providers/${providerKey}/projects`)
      setProjectOptions(projects || [])
    } catch {
      setProjectOptions([])
    } finally {
      setProjectsLoading(false)
    }
  }

  const openSettings = async (group: GroupRow) => {
    setSettingsDialogGroup(group)
    setSelectedSkillIds(group.default_skill_ids || [])
    setAllowlistsByProvider(resolveGroupAllowlists(group))
    setSettingsLoading(true)
    try {
      const [skills, providers] = await Promise.all([
        api.get<SkillOption[]>('/skills'),
        api.get<DevBridgeProviderOption[]>('/devbridge/providers'),
      ])
      setSkillOptions(skills || [])
      const enabledProviders = (providers || []).filter((item) => item.enabled)
      setProviderOptions(enabledProviders)
      const firstProvider = enabledProviders[0]?.key || ''
      setSelectedProviderKey(firstProvider)
      if (firstProvider) {
        await loadProviderProjects(firstProvider)
      } else {
        setProjectOptions([])
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.settingsLoadFailed'), { type: 'error' })
    } finally {
      setSettingsLoading(false)
    }
  }

  const handleProviderChange = async (providerKey: string) => {
    setSelectedProviderKey(providerKey)
    await loadProviderProjects(providerKey)
  }

  const toggleSkill = (skillId: string) => {
    setSelectedSkillIds((prev) =>
      prev.includes(skillId) ? prev.filter((id) => id !== skillId) : [...prev, skillId],
    )
  }

  const selectedProjectSlugs = selectedProviderKey
    ? (allowlistsByProvider[selectedProviderKey] || [])
    : []

  const toggleProject = (slug: string) => {
    if (!selectedProviderKey) return
    setAllowlistsByProvider((prev) => {
      const current = prev[selectedProviderKey] || []
      const next = current.includes(slug)
        ? current.filter((s) => s !== slug)
        : [...current, slug]
      return { ...prev, [selectedProviderKey]: next }
    })
  }

  const selectAllProjects = () => {
    if (!selectedProviderKey) return
    setAllowlistsByProvider((prev) => ({
      ...prev,
      [selectedProviderKey]: projectOptions.map((project) => project.slug),
    }))
  }

  const clearAllProjects = () => {
    if (!selectedProviderKey) return
    setAllowlistsByProvider((prev) => ({
      ...prev,
      [selectedProviderKey]: [],
    }))
  }

  const handleSaveSettings = async () => {
    if (!settingsDialogGroup) return
    setSettingsSaving(true)
    try {
      const hasAllowlistConfig = Object.keys(allowlistsByProvider).length > 0
      await api.patch(`/groups/${settingsDialogGroup.id}`, {
        default_skill_ids: selectedSkillIds,
        devbridge_project_allowlists: hasAllowlistConfig ? allowlistsByProvider : null,
      })
      toast(t('groups.settingsSaved'), { type: 'success' })
      setSettingsDialogGroup(null)
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.settingsSaveFailed'), { type: 'error' })
    } finally {
      setSettingsSaving(false)
    }
  }

  useEffect(() => {
    void loadGroups()
    void loadUsers()
  }, [])

  useEffect(() => {
    if (!memberDialogGroup || users.length === 0) return
    setSelectedUserId((current) => {
      const addable = users.filter((u) => !members.some((m) => m.user_id === u.id))
      if (current && addable.some((u) => u.id === current)) return current
      return addable[0]?.id ?? ''
    })
  }, [memberDialogGroup, users, members])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.post('/groups', {
        name: form.name.trim(),
        description: form.description.trim() || null,
      })
      toast(t('groups.created'), { type: 'success' })
      setForm({ name: '', description: '' })
      setShowCreate(false)
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.createFailed'), { type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (group: GroupRow) => {
    if (!window.confirm(t('groups.deleteConfirm', { name: group.name }))) return
    setDeletingGroupId(group.id)
    try {
      await api.delete(`/groups/${group.id}`)
      toast(t('groups.deleted'), { type: 'success' })
      if (memberDialogGroup?.id === group.id) {
        setMemberDialogGroup(null)
        setMembers([])
      }
      if (settingsDialogGroup?.id === group.id) {
        setSettingsDialogGroup(null)
      }
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.deleteFailed'), { type: 'error' })
    } finally {
      setDeletingGroupId(null)
    }
  }

  const handleAddMember = async () => {
    if (!memberDialogGroup || !selectedUserId) return
    setSavingMember(true)
    try {
      await api.post(`/groups/${memberDialogGroup.id}/members`, {
        user_id: selectedUserId,
        role: selectedRole,
      })
      toast(t('groups.memberSaved'), { type: 'success' })
      await loadMembers(memberDialogGroup)
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.memberSaveFailed'), { type: 'error' })
    } finally {
      setSavingMember(false)
    }
  }

  const handleUpdateMemberRole = async (member: GroupMemberRow, role: string) => {
    if (!memberDialogGroup || member.role === role) return
    setUpdatingMemberRoleId(member.id)
    try {
      await api.post(`/groups/${memberDialogGroup.id}/members`, {
        user_id: member.user_id,
        role,
      })
      toast(t('groups.memberRoleUpdated'), { type: 'success' })
      await loadMembers(memberDialogGroup)
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.memberSaveFailed'), { type: 'error' })
    } finally {
      setUpdatingMemberRoleId(null)
    }
  }

  const handleRemoveMember = async (member: GroupMemberRow) => {
    if (!memberDialogGroup) return
    if (!window.confirm(t('groups.removeMemberConfirm', { name: member.display_name || member.username || member.user_id }))) {
      return
    }
    try {
      await api.delete(`/groups/${memberDialogGroup.id}/members/${member.user_id}`)
      toast(t('groups.memberRemoved'), { type: 'success' })
      await loadMembers(memberDialogGroup)
      await loadGroups()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('groups.memberRemoveFailed'), { type: 'error' })
    }
  }

  if (currentUser?.role !== 'admin') {
    return (
      <div className="p-6 text-sm text-gray-500 dark:text-gray-400">
        {t('groups.adminOnly')}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('groups.title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('groups.subtitle')}</p>
        </div>
        <Button onClick={() => setShowCreate(true)} leftIcon={<Plus className="w-4 h-4" />}>
          {t('groups.create')}
        </Button>
      </div>

      <Card>
        <CardHeader>{t('groups.listTitle')}</CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : groups.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('groups.empty')}</p>
          ) : (
            <div className="space-y-3">
              {groups.map((group) => (
                <div key={group.id} className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">{group.name}</h3>
                      <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                        <Users className="w-3 h-3" />
                        {t('groups.memberCount', { count: group.member_count })}
                      </span>
                      {(group.default_skill_ids?.length || 0) > 0 && (
                        <span className="text-xs text-primary-600 dark:text-primary-400">
                          {t('groups.defaultSkillsCount', { count: group.default_skill_ids?.length || 0 })}
                        </span>
                      )}
                      {countAllowlistedProjects(group.devbridge_project_allowlists) > 0 && (
                        <span className="text-xs text-amber-700 dark:text-amber-300">
                          {t('groups.projectAllowlistCount', { count: countAllowlistedProjects(group.devbridge_project_allowlists) })}
                        </span>
                      )}
                    </div>
                    {group.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{group.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      leftIcon={<Clock3 className="w-3.5 h-3.5" />}
                      onClick={() => navigate(`/admin/group-memory?group=${group.id}`)}
                    >
                      {t('groups.manageMemory')}
                    </Button>
                    <Button variant="outline" size="sm" leftIcon={<Settings2 className="w-3.5 h-3.5" />} onClick={() => void openSettings(group)}>
                      {t('groups.manageSettings')}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => void loadMembers(group)}>
                      {t('groups.manageMembers')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      isLoading={deletingGroupId === group.id}
                      leftIcon={<Trash2 className="w-4 h-4" />}
                      onClick={() => void handleDelete(group)}
                    >
                      {t('common.delete')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showCreate} onClose={() => setShowCreate(false)} title={t('groups.createDialogTitle')}>
        <form className="space-y-4" onSubmit={handleCreate}>
          <Input
            label={t('groups.nameLabel')}
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
          />
          <Input
            label={t('groups.descriptionLabel')}
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
            <Button type="submit" isLoading={creating}>{t('common.create')}</Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={!!settingsDialogGroup}
        onClose={() => setSettingsDialogGroup(null)}
        title={t('groups.settingsDialogTitle', { name: settingsDialogGroup?.name || '' })}
        size="lg"
      >
        {settingsLoading ? (
          <div className="flex justify-center py-10"><Spinner size="lg" /></div>
        ) : (
          <div className="space-y-6">
            <div>
              <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">{t('groups.defaultSkillsTitle')}</h4>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('groups.defaultSkillsHint')}</p>
              <div className="max-h-48 overflow-y-auto space-y-2 border border-gray-200 dark:border-gray-700 rounded-lg p-2">
                {skillOptions.length === 0 ? (
                  <p className="text-xs text-gray-400 p-2">{t('groups.noSkills')}</p>
                ) : (
                  skillOptions.map((skill) => (
                    <label key={skill.id} className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer">
                      <input type="checkbox" className="mt-1" checked={selectedSkillIds.includes(skill.id)} onChange={() => toggleSkill(skill.id)} />
                      <span className="text-sm">
                        <span className="font-medium text-gray-900 dark:text-gray-100">{skill.name}</span>
                        {skill.description && <span className="block text-xs text-gray-500 mt-0.5 line-clamp-2">{skill.description}</span>}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">{t('groups.devbridgeAllowlistTitle')}</h4>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('groups.devbridgeAllowlistHint')}</p>
              {providerOptions.length === 0 ? (
                <p className="text-xs text-gray-400 p-2 border border-gray-200 dark:border-gray-700 rounded-lg">{t('groups.noProviders')}</p>
              ) : (
                <>
                  <Select
                    label={t('groups.devbridgeProviderLabel')}
                    value={selectedProviderKey}
                    options={providerOptions.map((provider) => ({
                      value: provider.key,
                      label: provider.title,
                    }))}
                    onChange={(e) => void handleProviderChange(e.target.value)}
                  />
                  <div className="flex items-center justify-between gap-2 mt-3 mb-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {t('groups.devbridgeSelectedCount', { count: selectedProjectSlugs.length })}
                    </span>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={selectAllProjects} disabled={projectsLoading || projectOptions.length === 0}>
                        {t('groups.selectAllProjects')}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={clearAllProjects} disabled={projectsLoading}>
                        {t('groups.clearAllProjects')}
                      </Button>
                    </div>
                  </div>
                  <div className="max-h-56 overflow-y-auto space-y-2 border border-gray-200 dark:border-gray-700 rounded-lg p-2">
                    {projectsLoading ? (
                      <div className="flex justify-center py-6"><Spinner /></div>
                    ) : projectOptions.length === 0 ? (
                      <p className="text-xs text-gray-400 p-2">{t('groups.noProjects')}</p>
                    ) : (
                      projectOptions.map((project) => (
                        <label key={project.slug} className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer">
                          <input type="checkbox" className="mt-1" checked={selectedProjectSlugs.includes(project.slug)} onChange={() => toggleProject(project.slug)} />
                          <span className="text-sm">
                            <span className="font-medium text-gray-900 dark:text-gray-100">{project.name}</span>
                            <span className="block text-xs text-gray-500 mt-0.5">
                              {project.slug}{project.has_build ? ` · ${t('groups.projectHasBuild')}` : ''}
                            </span>
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setSettingsDialogGroup(null)}>{t('common.cancel')}</Button>
              <Button isLoading={settingsSaving} onClick={() => void handleSaveSettings()}>{t('common.save')}</Button>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog
        open={!!memberDialogGroup}
        onClose={() => setMemberDialogGroup(null)}
        title={t('groups.membersDialogTitle', { name: memberDialogGroup?.name || '' })}
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_160px_auto] gap-3 items-end">
            <Select
              label={t('groups.memberUserLabel')}
              value={selectedUserId}
              placeholder={t('groups.memberUserPlaceholder')}
              options={users
                .filter((user) => !members.some((m) => m.user_id === user.id))
                .map((user) => ({
                  value: user.id,
                  label: userOptionLabel(user, t),
                }))}
              onChange={(e) => setSelectedUserId(e.target.value)}
            />
            <Select
              label={t('groups.memberRoleLabel')}
              value={selectedRole}
              options={[
                { value: 'member', label: t('groups.roleMember') },
                { value: 'editor', label: t('groups.roleEditor') },
                { value: 'owner', label: t('groups.roleOwner') },
              ]}
              onChange={(e) => setSelectedRole(e.target.value)}
            />
            <Button
              isLoading={savingMember}
              disabled={!selectedUserId}
              onClick={() => void handleAddMember()}
            >
              {t('groups.addMember')}
            </Button>
          </div>

          {membersLoading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : members.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('groups.membersEmpty')}</p>
          ) : (
            <div className="space-y-2">
              {members.map((member) => (
                <div key={member.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {member.display_name || member.username || member.user_id}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {t('groups.memberListAccount', {
                        account: accountRoleLabel(
                          member.user_role
                            ?? users.find((u) => u.id === member.user_id)?.role,
                          t,
                        ),
                      })}
                    </p>
                  </div>
                  <div className="w-36 shrink-0">
                    <Select
                      aria-label={t('groups.memberRoleLabel')}
                      value={member.role}
                      disabled={updatingMemberRoleId === member.id}
                      options={[
                        { value: 'member', label: t('groups.roleMember') },
                        { value: 'editor', label: t('groups.roleEditor') },
                        { value: 'owner', label: t('groups.roleOwner') },
                      ]}
                      onChange={(e) => void handleUpdateMemberRole(member, e.target.value)}
                    />
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => void handleRemoveMember(member)}>
                    {t('common.delete')}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
