import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import { portalApi } from '@/lib/portalApi'
import { isCloudEdition } from '@/lib/edition'
import {
  getPreferredStaffMode,
  readStoredChannelId,
  readStoredChatScope,
  setPreferredStaffMode,
  writeStoredChannelId,
  writeStoredChatScope,
} from '@/lib/appPreferences'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { Button } from '@/components/ui/Button'
import { AppModeSwitch } from '@/components/common/AppModeSwitch'
import { SetupGuide } from '@/components/setup/SetupGuide'
import { useAuthStore } from '@/stores/auth'
import { fetchSetupStatus, type SetupStatus } from '@/lib/setupStatus'

interface ChannelOption {
  id: string
  name: string
}

interface CreatedChannel {
  id: string
  name: string
}

interface GroupOption {
  id: string
  name: string
}

async function loadChannels(
  mode: 'portal' | 'agent',
): Promise<ChannelOption[]> {
  if (mode === 'portal') {
    const rows = await portalApi.getMyChannels()
    return rows.filter((c) => c.enabled !== false).map((c) => ({ id: c.id, name: c.name }))
  }
  const rows = await api.get<Array<{ id: string; name: string; enabled?: boolean }>>(
    '/agents/customer-configs',
  )
  return (rows || [])
    .filter((c) => c.enabled !== false)
    .map((c) => ({ id: c.id, name: c.name }))
}

async function ensureStaffDefaultChannel(name: string): Promise<ChannelOption> {
  const channel = await api.post<CreatedChannel>('/agents/customer-configs', {
    name,
  })
  return { id: channel.id, name: channel.name }
}

function pickChannel(
  channels: ChannelOption[],
  role: string | null | undefined,
): ChannelOption | null {
  if (!channels.length) return null
  const lastId = readStoredChannelId(role)
  if (lastId) {
    const hit = channels.find((c) => c.id === lastId)
    if (hit) return hit
  }
  return channels[0]
}

interface ChatHomePageProps {
  mode?: 'portal' | 'agent'
}

function ChatHomeShell({
  children,
  showModeSwitch,
  modeSwitchVariant,
}: {
  children: ReactNode
  showModeSwitch: boolean
  modeSwitchVariant: 'agent' | 'portal'
}) {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-900">
      {showModeSwitch && (
        <header className="shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
          <AppModeSwitch variant={modeSwitchVariant} active="chat" />
        </header>
      )}
      <div className="flex-1 flex flex-col">{children}</div>
    </div>
  )
}

export function ChatHomePage({ mode: modeProp }: ChatHomePageProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, checkAuth, isAuthenticated, isLoading: authLoading } = useAuthStore()
  const mode: 'portal' | 'agent' =
    modeProp ?? (user?.role === 'user' ? 'portal' : 'agent')
  const isPortalUser = user?.role === 'user'
  const showModeSwitch =
    user?.role === 'agent' ||
    user?.role === 'admin' ||
    (isPortalUser && isCloudEdition) ||
    (isAuthenticated && !user && getPreferredStaffMode() === 'chat')
  const modeSwitchVariant = isPortalUser ? 'portal' : 'agent'
  const setupVariant = isPortalUser && isCloudEdition ? 'portal' : 'staff'

  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null)
  const [setupLoading, setSetupLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const [groupOptions, setGroupOptions] = useState<GroupOption[]>([])
  const [chatScopeType, setChatScopeType] = useState<'personal' | 'group'>(() => readStoredChatScope(user?.role).type)
  const [chatScopeId, setChatScopeId] = useState<string>(() => readStoredChatScope(user?.role).groupId || '')

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (user?.role === 'agent' || user?.role === 'admin') {
      setPreferredStaffMode('chat')
    }
  }, [user?.role])

  useEffect(() => {
    if (!isAuthenticated) return
    api
      .get<Array<{ id: string; name: string }>>('/groups/mine')
      .then((rows) => setGroupOptions(rows || []))
      .catch(() => setGroupOptions([]))
  }, [isAuthenticated])

  useEffect(() => {
    const stored = readStoredChatScope(user?.role)
    setChatScopeType(stored.type)
    setChatScopeId(stored.groupId || '')
  }, [user?.role])

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      navigate('/admin/login', { state: { from: '/chat' }, replace: true })
      return
    }
    let cancelled = false
    setSetupLoading(true)
    fetchSetupStatus()
      .then((status) => {
        if (!cancelled) setSetupStatus(status)
      })
      .catch(() => {
        if (!cancelled) setSetupStatus(null)
      })
      .finally(() => {
        if (!cancelled) setSetupLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [authLoading, isAuthenticated, navigate])

  useEffect(() => {
    if (!setupStatus) return
    const inGroupScope = chatScopeType === 'group' && Boolean(chatScopeId)
    if (!inGroupScope && (!setupStatus.ai_ready || !setupStatus.has_assistant)) return
    let cancelled = false
    setOpening(true)
    setError(null)
    ;(async () => {
      try {
        if (inGroupScope && chatScopeId) {
          const groupName =
            groupOptions.find((g) => g.id === chatScopeId)?.name ||
            t('chat.scopeGroup', '群组')
          const conv = await api.post<{ id: string }>(
            `/groups/${chatScopeId}/chat/resume`,
            { title: groupName },
          )
          if (cancelled) return
          writeStoredChatScope(user?.role, { type: 'group', groupId: chatScopeId })
          navigate(`/chat/${conv.id}?scope=group&group=${chatScopeId}`, { replace: true })
          return
        }

        const channels = await loadChannels(mode)
        if (cancelled) return
        let channel = pickChannel(channels, user?.role)
        if (!channel) {
          if (mode === 'agent') {
            channel = await ensureStaffDefaultChannel(
              t('chatHome.defaultAssistantName'),
            )
          } else if (groupOptions.length > 0) {
            const firstGroup = groupOptions[0]
            const conv = await api.post<{ id: string }>(
              `/groups/${firstGroup.id}/chat/resume`,
              { title: firstGroup.name },
            )
            if (cancelled) return
            writeStoredChatScope(user?.role, { type: 'group', groupId: firstGroup.id })
            navigate(`/chat/${conv.id}?scope=group&group=${firstGroup.id}`, { replace: true })
            return
          } else {
            setError(t('chatHome.loadFailed'))
            return
          }
        }
        const conv = await api.post<{ id: string }>('/chat/conversations/resume', {
          customer_id: channel.id,
          title: channel.name,
          scope_type: chatScopeType,
          scope_id: chatScopeType === 'group' ? chatScopeId || null : null,
        })
        if (cancelled) return
        writeStoredChannelId(user?.role, channel.id)
        writeStoredChatScope(user?.role, {
          type: chatScopeType,
          ...(chatScopeType === 'group' && chatScopeId ? { groupId: chatScopeId } : {}),
        })
        navigate(
          `/chat/${conv.id}?channel=${channel.id}${chatScopeType === 'group' && chatScopeId ? `&scope=group&group=${chatScopeId}` : ''}`,
          { replace: true },
        )
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : t('chatHome.loadFailed'))
        }
      } finally {
        if (!cancelled) setOpening(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [setupStatus, mode, navigate, t, user?.role, chatScopeType, chatScopeId, groupOptions])

  if (authLoading || setupLoading) {
    return (
      <ChatHomeShell showModeSwitch={showModeSwitch} modeSwitchVariant={modeSwitchVariant}>
        <div className="flex flex-col items-center justify-center flex-1 gap-3">
          <div className="w-full max-w-sm px-6">
            <Select
              label={t('chat.scopeLabel', '聊天作用域')}
              value={chatScopeType === 'group' ? `group:${chatScopeId}` : 'personal'}
              options={[
                { value: 'personal', label: t('chat.scopePersonal', '个人空间') },
                ...groupOptions.map((group) => ({ value: `group:${group.id}`, label: `${t('chat.scopeGroup', '群组')}: ${group.name}` })),
              ]}
              onChange={(event) => {
                const value = event.target.value
                if (value === 'personal') {
                  setChatScopeType('personal')
                  setChatScopeId('')
                  return
                }
                const [, groupId] = value.split(':')
                setChatScopeType('group')
                setChatScopeId(groupId || '')
              }}
            />
          </div>
          <Spinner size="lg" />
          <p className="text-sm text-gray-500">{t('common.loading')}</p>
        </div>
      </ChatHomeShell>
    )
  }

  const inGroupScope = chatScopeType === 'group' && Boolean(chatScopeId)
  if (
    setupStatus &&
    !inGroupScope &&
    (!setupStatus.ai_ready || !setupStatus.has_assistant)
  ) {
    if (isPortalUser && isCloudEdition) {
      return (
        <ChatHomeShell showModeSwitch={showModeSwitch} modeSwitchVariant={modeSwitchVariant}>
          <div className="flex flex-col items-center justify-center flex-1 px-6 py-10 text-center max-w-md mx-auto">
            {groupOptions.length > 0 ? (
              <>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {t('portal.groupsTitle')}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
                  {t('portal.hasGroupsNoAssistantHint')}
                </p>
                <Button className="mt-6" onClick={() => navigate('/portal/groups')}>
                  {t('portal.openGroupChat')}
                </Button>
              </>
            ) : (
              <>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {t('portal.noChannelTitle')}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
                  {t('portal.noChannelHint')}
                </p>
                <Button className="mt-6" onClick={() => navigate('/portal/templates')}>
                  {t('portal.browseTemplates')}
                </Button>
              </>
            )}
          </div>
        </ChatHomeShell>
      )
    }
    return (
      <ChatHomeShell showModeSwitch={showModeSwitch} modeSwitchVariant={modeSwitchVariant}>
        <div className="flex flex-col items-center justify-center flex-1 px-6 py-10">
          <SetupGuide status={setupStatus} variant={setupVariant} />
        </div>
      </ChatHomeShell>
    )
  }

  if (error) {
    return (
      <ChatHomeShell showModeSwitch={showModeSwitch} modeSwitchVariant={modeSwitchVariant}>
        <div className="flex flex-col items-center justify-center flex-1 text-center px-6">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
            {t('common.refresh')}
          </Button>
        </div>
      </ChatHomeShell>
    )
  }

  if (opening) {
    return (
      <ChatHomeShell showModeSwitch={showModeSwitch} modeSwitchVariant={modeSwitchVariant}>
        <div className="flex flex-col items-center justify-center flex-1 gap-3">
          <div className="w-full max-w-sm px-6">
            <Select
              label={t('chat.scopeLabel', '聊天作用域')}
              value={chatScopeType === 'group' ? `group:${chatScopeId}` : 'personal'}
              options={[
                { value: 'personal', label: t('chat.scopePersonal', '个人空间') },
                ...groupOptions.map((group) => ({ value: `group:${group.id}`, label: `${t('chat.scopeGroup', '群组')}: ${group.name}` })),
              ]}
              onChange={(event) => {
                const value = event.target.value
                if (value === 'personal') {
                  setChatScopeType('personal')
                  setChatScopeId('')
                } else {
                  const [, groupId] = value.split(':')
                  setChatScopeType('group')
                  setChatScopeId(groupId || '')
                }
              }}
            />
          </div>
          <Spinner size="lg" />
          <p className="text-sm text-gray-500">{t('chatHome.opening')}</p>
        </div>
      </ChatHomeShell>
    )
  }

  return null
}
