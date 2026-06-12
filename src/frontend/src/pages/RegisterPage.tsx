import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MessageCircle } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { isCloudEdition } from '@/lib/edition'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'

export function RegisterPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const {
    signupByPhone,
    sendSmsCode,
    start9235Login,
    isLoading,
    error,
    clearError,
  } = useAuthStore()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [smsCooldown, setSmsCooldown] = useState(0)

  useEffect(() => {
    if (smsCooldown <= 0) return
    const id = window.setInterval(() => {
      setSmsCooldown((s) => (s <= 1 ? 0 : s - 1))
    }, 1000)
    return () => window.clearInterval(id)
  }, [smsCooldown])

  const handleSendCode = useCallback(async () => {
    clearError()
    setLocalError(null)
    if (!phone.trim()) {
      setLocalError(t('auth.phoneRequired'))
      return
    }
    try {
      await sendSmsCode(phone.trim())
      setSmsCooldown(60)
    } catch {
      /* store */
    }
  }, [phone, sendSmsCode, clearError, t])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    setLocalError(null)
    if (!phone.trim() || !code.trim()) {
      setLocalError(t('auth.phoneCodeRequired'))
      return
    }
    try {
      await signupByPhone(phone.trim(), code.trim())
      const user = useAuthStore.getState().user
      const dest =
        isCloudEdition && user?.role === 'user' ? '/portal/dashboard' : '/chat'
      navigate(dest, { replace: true })
    } catch {
      /* store */
    }
  }

  const handle9235Login = async () => {
    clearError()
    setLocalError(null)
    try {
      await start9235Login()
    } catch {
      /* redirect or error */
    }
  }

  const displayError = localError || error

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-primary-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-800 p-4">
      <div className="absolute top-4 right-4">
        <LanguageSwitcher />
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">MChat</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('auth.registerTagline')}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            {t('auth.registerTitle')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            {t('auth.registerPhoneHint')}
          </p>

          <Button
            type="button"
            variant="outline"
            className="w-full mb-6"
            onClick={handle9235Login}
            disabled={isLoading}
          >
            {t('auth.loginWith9235')}
          </Button>

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-gray-200 dark:border-gray-600" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white dark:bg-gray-800 px-2 text-gray-400">
                {t('auth.orRegisterPhone')}
              </span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {displayError && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
                {displayError}
              </div>
            )}
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
              {t('auth.signup')}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('auth.haveAccount')}{' '}
            <Link
              to="/admin/login"
              className="text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium"
            >
              {t('auth.submit')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
