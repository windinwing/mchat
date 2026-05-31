import React, { useState, useEffect } from 'react'
import api from '@/lib/api'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MessageCircle, Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { isCloudEdition } from '@/lib/edition'

export function LoginForm() {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const { login, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const from = (location.state as { from?: string })?.from || '/admin'
  const [bootstrapHint, setBootstrapHint] = useState<{
    username: string
    password: string | null
  } | null>(null)

  useEffect(() => {
    api
      .get<{ username: string; password: string | null; show_credentials: boolean }>(
        '/auth/bootstrap',
      )
      .then((data) => {
        if (data.show_credentials && data.password) {
          setBootstrapHint({ username: data.username, password: data.password })
        }
      })
      .catch(() => {})
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await login(username, password)
      // After login, check user role from store to redirect correctly
      const user = useAuthStore.getState().user
      if (isCloudEdition && user?.role === 'user') {
        navigate('/portal/dashboard', { replace: true })
      } else {
        navigate(from, { replace: true })
      }
    } catch {
      // error is handled by store
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
            {t('auth.tagline')}
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">
            {t('auth.loginTitle')}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <Input
              label={t('auth.username')}
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('auth.usernamePlaceholder')}
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

          {bootstrapHint && (
            <p className="mt-4 text-xs text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50 rounded-lg px-3 py-2 border border-gray-100 dark:border-gray-700">
              {t('auth.defaultCredentials', {
                username: bootstrapHint.username,
                password: bootstrapHint.password,
              })}
            </p>
          )}

          {isCloudEdition && (
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
        </div>
      </div>
    </div>
  )
}
