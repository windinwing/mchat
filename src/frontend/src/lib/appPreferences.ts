export type StaffAppMode = 'chat' | 'admin'
export type ChatScopeType = 'personal' | 'group'

export interface StoredChatScope {
  type: ChatScopeType
  groupId?: string
}

const STAFF_MODE_KEY = 'mchat_staff_default_mode'
const STAFF_CHANNEL_KEY = 'mchat_staff_channel_id'
const PORTAL_CHANNEL_KEY = 'mchat_portal_channel_id'
const STAFF_CHAT_SCOPE_KEY = 'mchat_staff_chat_scope'
const PORTAL_CHAT_SCOPE_KEY = 'mchat_portal_chat_scope'

function hasWindow(): boolean {
  return typeof window !== 'undefined'
}

export function getPreferredStaffMode(): StaffAppMode {
  if (!hasWindow()) return 'chat'
  return localStorage.getItem(STAFF_MODE_KEY) === 'admin' ? 'admin' : 'chat'
}

export function setPreferredStaffMode(mode: StaffAppMode): void {
  if (!hasWindow()) return
  localStorage.setItem(STAFF_MODE_KEY, mode)
}

export function preferredStaffPath(): '/chat' | '/admin' {
  return getPreferredStaffMode() === 'admin' ? '/admin' : '/chat'
}

export function channelStorageKeyForRole(role: string | null | undefined): string {
  return role === 'user' ? PORTAL_CHANNEL_KEY : STAFF_CHANNEL_KEY
}

function chatScopeStorageKeyForRole(role: string | null | undefined): string {
  return role === 'user' ? PORTAL_CHAT_SCOPE_KEY : STAFF_CHAT_SCOPE_KEY
}

export function readStoredChannelId(role: string | null | undefined): string | undefined {
  if (!hasWindow()) return undefined
  return sessionStorage.getItem(channelStorageKeyForRole(role)) || undefined
}

export function writeStoredChannelId(
  role: string | null | undefined,
  channelId: string | null | undefined,
): void {
  if (!hasWindow()) return
  const key = channelStorageKeyForRole(role)
  if (channelId) {
    sessionStorage.setItem(key, channelId)
    return
  }
  sessionStorage.removeItem(key)
}

export function readStoredChatScope(role: string | null | undefined): StoredChatScope {
  if (!hasWindow()) return { type: 'personal' }
  const raw = sessionStorage.getItem(chatScopeStorageKeyForRole(role))
  if (!raw) return { type: 'personal' }
  try {
    const parsed = JSON.parse(raw) as StoredChatScope
    if (parsed?.type === 'group' && parsed.groupId) {
      return { type: 'group', groupId: parsed.groupId }
    }
  } catch {
    /* ignore */
  }
  return { type: 'personal' }
}

export function writeStoredChatScope(
  role: string | null | undefined,
  scope: StoredChatScope,
): void {
  if (!hasWindow()) return
  sessionStorage.setItem(chatScopeStorageKeyForRole(role), JSON.stringify(scope))
}