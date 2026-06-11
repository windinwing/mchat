import { create } from 'zustand'
import api, { setToken, removeToken } from '@/lib/api'

export interface User {
  id: string
  username: string
  role: 'admin' | 'agent' | 'user'
  account_status?: string
  display_name?: string | null
  avatar_url?: string | null
  email?: string
  phone?: string | null
  external_provider?: string | null
  can_set_password?: boolean
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (username: string, password: string) => Promise<void>
  signup: (username: string, password: string, email?: string, displayName?: string) => Promise<void>
  sendSmsCode: (phone: string) => Promise<void>
  signupByPhone: (phone: string, code: string) => Promise<void>
  loginByPhone: (phone: string, code: string) => Promise<void>
  start9235Login: () => Promise<void>
  complete9235Sso: (xtk: string) => Promise<void>
  updateProfile: (payload: { display_name?: string | null; avatar_url?: string | null }) => Promise<User>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem('mchat_token'),
  isLoading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<{ access_token: string; token_type: string; user: User }>('/auth/login', {
        username,
        password,
      })
      setToken(res.access_token)
      set({
        user: res.user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err: any) {
      set({
        isLoading: false,
        error: err.message || '登录失败',
      })
      throw err
    }
  },

  signup: async (username, password, email, displayName) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<{ access_token: string; token_type: string; user: User }>('/auth/signup', {
        username,
        password,
        email,
        display_name: displayName,
      })
      setToken(res.access_token)
      set({
        user: res.user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err: any) {
      set({
        isLoading: false,
        error: err.message || 'Signup failed',
      })
      throw err
    }
  },

  sendSmsCode: async (phone: string) => {
    set({ isLoading: true, error: null })
    try {
      await api.post('/auth/sms/send', { phone })
      set({ isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '发送验证码失败' })
      throw err
    }
  },

  signupByPhone: async (phone: string, code: string) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<{ access_token: string; token_type: string; user: User }>(
        '/auth/signup/phone',
        { phone, code },
      )
      setToken(res.access_token)
      set({ user: res.user, isAuthenticated: true, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '注册失败' })
      throw err
    }
  },

  loginByPhone: async (phone: string, code: string) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<{ access_token: string; token_type: string; user: User }>(
        '/auth/login/phone',
        { phone, code },
      )
      setToken(res.access_token)
      set({ user: res.user, isAuthenticated: true, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '登录失败' })
      throw err
    }
  },

  start9235Login: async () => {
    set({ isLoading: true, error: null })
    try {
      const { url } = await api.get<{ url: string }>('/auth/sso/9235/url')
      window.location.href = url
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '无法跳转 9235 登录' })
      throw err
    }
  },

  complete9235Sso: async (xtk: string) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<{ access_token: string; token_type: string; user: User }>(
        '/auth/sso/9235/callback',
        { xtk },
      )
      setToken(res.access_token)
      set({ user: res.user, isAuthenticated: true, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '9235 登录失败' })
      throw err
    }
  },

  updateProfile: async (payload) => {
    set({ isLoading: true, error: null })
    try {
      const user = await api.patch<User>('/auth/me', payload)
      set({ user, isAuthenticated: true, isLoading: false })
      return user
    } catch (err: any) {
      set({ isLoading: false, error: err.message || '更新资料失败' })
      throw err
    }
  },

  logout: () => {
    removeToken()
    set({
      user: null,
      isAuthenticated: false,
    })
  },

  checkAuth: async () => {
    const token = localStorage.getItem('mchat_token')
    if (!token) {
      set({ isAuthenticated: false, user: null })
      return
    }
    set({ isLoading: true })
    try {
      const user = await api.get<User>('/auth/me')
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      removeToken()
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
