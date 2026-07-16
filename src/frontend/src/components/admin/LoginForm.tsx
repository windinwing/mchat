import React, { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MessageCircle, Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { getEditionEffective, applyRuntimeEditionFlags } from '@/lib/edition'
import { preferredStaffPath } from '@/lib/appPreferences'

type LoginMode = 'phone' | 'password'

function postLoginPath(user: { role: string } | null, from?: string): string {
  const { cloud } = getEditionEffective()
  if (cloud && user?.role === 'user') {
    return from && from.startsWith('/portal') ? from : '/portal/dashboard'
  }
  if (user?.role === 'agent' || user?.role === 'admin') {
    return from || preferredStaffPath()
  }
  return from || '/admin'
}

export function LoginForm() {
  const { t } = useTranslation()
  // portalLogin starts from build-time flags, then widens once /auth/bootstrap
  // reports the server's actual edition (so a Core build on a Cloud server
  // still shows register / phone login / 9235 SSO).
  const [effectiveFlags, setEffectiveFlags] = useState(() => getEditionEffective())
  const portalLogin = effectiveFlags.signup || effectiveFlags.cloud
  const [mode, setMode] = useState<LoginMode>('password')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [smsCooldown, setSmsCooldown] = useState(0)
  const [showPassword, setShowPassword] = useState(false)
  const { login, loginByPhone, sendSmsCode, start9235Login, isLoading, error, clearError } =
    useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const from =
    (location.state as { from?: string })?.from ||
    new URLSearchParams(location.search).get('redirect') ||
    undefined
  const [bootstrapHint, setBootstrapHint] = useState<{
    username: string
    password: string | null
  } | null>(null)

  useEffect(() => {
    if (smsCooldown <= 0) return
    const id = window.setInterval(() => {
      setSmsCooldown((s) => (s <= 1 ? 0 : s - 1))
    }, 1000)
    return () => window.clearInterval(id)
  }, [smsCooldown])

  useEffect(() => {
    api
      .get<{
        username: string
        password: string | null
        show_credentials: boolean
        signup_enabled?: boolean
        cloud_edition?: boolean
      }>('/auth/bootstrap')
      .then((data) => {
        if (data.show_credentials && data.password) {
          setBootstrapHint({ username: data.username, password: data.password })
        }
        // Widen edition flags from the live server. This makes register /
        // phone login / 9235 SSO appear even if the frontend was built as
        // Core while the backend is Cloud or has signup enabled.
        applyRuntimeEditionFlags({
          cloud: !!data.cloud_edition,
          signup: !!data.signup_enabled,
        })
        setEffectiveFlags(getEditionEffective())
      })
      .catch(() => {})
  }, [])

  const handleSendCode = useCallback(async () => {
    clearError()
    if (!phone.trim()) return
    try {
      await sendSmsCode(phone.trim())
      setSmsCooldown(60)
    } catch {
      /* store */
    }
  }, [phone, sendSmsCode, clearError])

  const handlePhoneSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await loginByPhone(phone.trim(), code.trim())
      const user = useAuthStore.getState().user
      navigate(postLoginPath(user, from), { replace: true })
    } catch {
      /* store */
    }
  }

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await login(username, password)
      const user = useAuthStore.getState().user
      navigate(postLoginPath(user, from), { replace: true })
    } catch {
      /* store */
    }
  }

  const handle9235Login = async () => {
    clearError()
    try {
      await start9235Login()
    } catch {
      /* redirect or error */
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-primary-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-800 p-4">
      <div className="absolute top-4 right-4">
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>
      <div className="absolute top-4 left-4">
        <Link
          to="/"
          className="text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400"
        >
          ← {t('common.home')}
        </Link>
      </div>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary-600 mb-4">
            <MessageCircle className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            MChat
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {portalLogin ? t('auth.portalTagline') : t('auth.tagline')}
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">
            {portalLogin ? t('auth.portalLoginTitle') : t('auth.loginTitle')}
          </h2>

          {portalLogin && (
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-600 p-1 mb-6">
              <button
                type="button"
                className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                  mode === 'password'
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
                onClick={() => {
                  setMode('password')
                  clearError()
                }}
              >
                {t('auth.loginModePassword')}
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                  mode === 'phone'
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
                onClick={() => {
                  setMode('phone')
                  clearError()
                }}
              >
                {t('auth.loginModePhone')}
              </button>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400 mb-4">
              {error}
            </div>
          )}

          {portalLogin && mode === 'phone' ? (
            <form onSubmit={handlePhoneSubmit} className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('auth.loginPhoneHint')}
              </p>
              <Input
                label={t('auth.phone')}
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t('auth.phonePlaceholder')}
                autoComplete="tel"
                required
              />
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Input
                    label={t('auth.smsCode')}
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder={t('auth.smsCodePlaceholder')}
                    autoComplete="one-time-code"
                    required
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="shrink-0 mb-0.5"
                  disabled={isLoading || smsCooldown > 0}
                  onClick={handleSendCode}
                >
                  {smsCooldown > 0
                    ? t('auth.resendIn', { seconds: smsCooldown })
                    : t('auth.sendCode')}
                </Button>
              </div>
              <Button type="submit" className="w-full" size="lg" isLoading={isLoading}>
                {t('auth.submit')}
              </Button>
            </form>
          ) : (
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <Input
                label={portalLogin ? t('auth.usernameOrPhone') : t('auth.username')}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={
                  portalLogin
                    ? t('auth.usernameOrPhonePlaceholder')
                    : t('auth.usernamePlaceholder')
                }
                autoComplete="username"
                required
              />

              <div>
                <Input
                  label={t('auth.password')}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.passwordPlaceholder')}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="mt-1 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 flex items-center gap-1"
                >
                  {showPassword ? (
                    <>
                      <EyeOff className="w-3 h-3" /> {t('auth.hidePassword')}
                    </>
                  ) : (
                    <>
                      <Eye className="w-3 h-3" /> {t('auth.showPassword')}
                    </>
                  )}
                </button>
              </div>

              <Button
                type="submit"
                className="w-full"
                size="lg"
                isLoading={isLoading}
              >
                {t('auth.submit')}
              </Button>
            </form>
          )}

          {bootstrapHint && mode === 'password' && (
            <p className="mt-4 text-xs text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50 rounded-lg px-3 py-2 border border-gray-100 dark:border-gray-700">
              {t('auth.defaultCredentials', {
                username: bootstrapHint.username,
                password: bootstrapHint.password,
              })}
            </p>
          )}

          {effectiveFlags.signup && (
            <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
              {t('auth.noAccount')}{' '}
              <Link
                to="/register"
                className="text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium"
              >
                {t('auth.register')}
              </Link>
            </p>
          )}

          {portalLogin && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-gray-200 dark:border-gray-600" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-white dark:bg-gray-800 px-2 text-gray-400">
                    {t('auth.orLoginWith')}
                  </span>
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={handle9235Login}
                disabled={isLoading}
              >
                {t('auth.loginWith9235')}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
