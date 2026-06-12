import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { toast } from '@/components/ui/Toast'

interface PortalSetPasswordFormProps {
  hasPassword?: boolean
}

export function PortalSetPasswordForm({ hasPassword = false }: PortalSetPasswordFormProps) {
  const { t } = useTranslation()
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword.length < 6) {
      toast(t('portal.passwordTooShort'), { type: 'error' })
      return
    }
    if (newPassword !== confirmPassword) {
      toast(t('users.passwordMismatch'), { type: 'error' })
      return
    }
    if (hasPassword && !currentPassword.trim()) {
      toast(t('portal.currentPasswordRequired'), { type: 'error' })
      return
    }
    setSaving(true)
    try {
      await api.post('/auth/change-password', {
        current_password: hasPassword ? currentPassword : undefined,
        new_password: newPassword,
      })
      toast(
        hasPassword ? t('users.passwordChanged') : t('portal.passwordSetSuccess'),
        { type: 'success' },
      )
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      await checkAuth()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('users.passwordChangeFailed')
      toast(message, { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const canSubmit =
    newPassword.length >= 6 &&
    newPassword === confirmPassword &&
    (!hasPassword || currentPassword.trim().length > 0)

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {hasPassword ? t('portal.changePasswordHint') : t('portal.setPasswordHint')}
      </p>
      {hasPassword && (
        <Input
          label={t('users.currentPassword')}
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          autoComplete="current-password"
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label={t('users.newPassword')}
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          minLength={6}
          autoComplete="new-password"
        />
        <Input
          label={t('users.confirmPassword')}
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          minLength={6}
          autoComplete="new-password"
        />
      </div>
      <div className="flex justify-end">
        <Button type="submit" isLoading={saving} disabled={!canSubmit}>
          {hasPassword ? t('users.changePassword') : t('portal.savePassword')}
        </Button>
      </div>
    </form>
  )
}
