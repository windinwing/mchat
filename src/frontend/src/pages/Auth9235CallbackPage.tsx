import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/stores/auth'
import { Spinner } from '@/components/ui/Spinner'
import { isCloudEdition } from '@/lib/edition'

export function Auth9235CallbackPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { complete9235Sso, error, clearError } = useAuthStore()
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    clearError()
    const xtk = params.get('xtk')
    if (!xtk) {
      if (params.get('token')) {
        setLocalError(t('auth.ssoWrongTokenParam'))
        return
      }
      setLocalError(t('auth.ssoMissingToken'))
      return
    }
    complete9235Sso(xtk)
      .then(() => {
        const user = useAuthStore.getState().user
        const destination =
          isCloudEdition && user?.role === 'user' ? '/portal/dashboard' : '/chat'
        navigate(destination, { replace: true })
      })
      .catch(() => {})
  }, [params, complete9235Sso, navigate, clearError, t])

  const displayError = localError || error

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-4">
      {displayError ? (
        <p className="text-red-600 dark:text-red-400 text-sm">{displayError}</p>
      ) : (
        <>
          <Spinner size="lg" />
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('auth.ssoSigningIn')}</p>
        </>
      )}
    </div>
  )
}
