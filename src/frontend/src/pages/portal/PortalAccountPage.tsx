import { useEffect, useRef, useState, type ChangeEvent, type ClipboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowLeft, ClipboardPaste, ImagePlus, Trash2 } from 'lucide-react'
import api from '@/lib/api'
import { resolveUploadUrl } from '@/lib/mediaUrl'
import { useAuthStore } from '@/stores/auth'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/components/ui/Toast'
import { PortalSetPasswordForm } from '@/components/portal/PortalSetPasswordForm'
import { PortalAdvancedPanel } from '@/components/portal/PortalAdvancedPanel'
import { PortalAiConfigManager } from '@/components/portal/PortalAiConfigManager'

interface TenantFileUploadResponse {
  path: string
  name: string
  size: number
  url: string
}

function buildAvatarFilename(file: File): string {
  const ext = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.')) : '.png'
  return `avatar-${Date.now()}${ext}`
}

export function PortalAccountPage() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const updateProfile = useAuthStore((s) => s.updateProfile)
  const [displayName, setDisplayName] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setDisplayName(user?.display_name || '')
    setAvatarUrl(user?.avatar_url || '')
  }, [user?.avatar_url, user?.display_name])

  const resolvedAvatarUrl = resolveUploadUrl(avatarUrl)
  const effectiveName = displayName.trim() || user?.display_name || user?.username || ''
  const hasProfileChanges =
    displayName.trim() !== (user?.display_name || '') || avatarUrl !== (user?.avatar_url || '')
  const showPasswordSection = user?.can_set_password !== false && !user?.external_provider

  const uploadAvatar = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast(t('portal.avatarInvalidType'), { type: 'error' })
      return
    }

    setUploadingAvatar(true)
    try {
      const renamed = new File([file], buildAvatarFilename(file), {
        type: file.type || 'image/png',
        lastModified: file.lastModified,
      })
      const form = new FormData()
      form.append('file', renamed)
      form.append('subdir', 'user')
      form.append('relative_dir', 'profile/avatars')
      const uploaded = await api.upload<TenantFileUploadResponse>('/workspace/files/upload', form)
      setAvatarUrl(uploaded.url)
      toast(t('portal.avatarUploadSuccess'), { type: 'success' })
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.avatarUploadFailed'), { type: 'error' })
    } finally {
      setUploadingAvatar(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleAvatarFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    await uploadAvatar(file)
  }

  const handleAvatarPaste = async (event: ClipboardEvent<HTMLDivElement>) => {
    const imageItem = Array.from(event.clipboardData.items).find((item) => item.type.startsWith('image/'))
    const file = imageItem?.getAsFile()
    if (!file) return
    event.preventDefault()
    await uploadAvatar(file)
  }

  const handleRemoveAvatar = () => {
    setAvatarUrl('')
    toast(t('portal.avatarRemoved'), { type: 'info' })
  }

  const handleProfileSave = async () => {
    setSaving(true)
    try {
      await updateProfile({
        display_name: displayName.trim() || user?.username || '',
        avatar_url: avatarUrl.trim() || null,
      })
      toast(t('portal.profileSaved'), { type: 'success' })
    } catch (err) {
      toast(err instanceof Error ? err.message : t('portal.profileSaveFailed'), { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 text-gray-900 dark:text-gray-200">
      <Link
        to="/portal/dashboard"
        className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-primary-600"
      >
        <ArrowLeft className="w-4 h-4" />
        {t('portal.backDashboard')}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('portal.accountTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {user?.phone || user?.username}
            {user?.email && ` · ${user.email}`}
          </p>
        </div>
        {hasProfileChanges && (
          <Badge variant="warning">{t('portal.unsavedChanges')}</Badge>
        )}
      </div>

      <section className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
            {t('portal.profileTitle')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('portal.profileHint')}
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[auto,1fr]">
          <div className="flex flex-col items-center gap-3">
            <Avatar
              src={resolvedAvatarUrl}
              name={effectiveName}
              size="xl"
              className="ring-4 ring-primary-100 dark:ring-primary-900/40"
            />
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                leftIcon={<ImagePlus className="w-4 h-4" />}
                isLoading={uploadingAvatar}
                onClick={() => fileInputRef.current?.click()}
              >
                {t('portal.uploadAvatar')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                leftIcon={<Trash2 className="w-4 h-4" />}
                disabled={!avatarUrl}
                onClick={handleRemoveAvatar}
              >
                {t('portal.removeAvatar')}
              </Button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              aria-label={t('portal.uploadAvatar')}
              title={t('portal.uploadAvatar')}
              onChange={handleAvatarFileChange}
            />
          </div>

          <div className="space-y-4 min-w-0">
            <Input
              label={t('portal.displayNameLabel')}
              value={displayName}
              maxLength={100}
              placeholder={user?.username || t('portal.displayNamePlaceholder')}
              onChange={(event) => setDisplayName(event.target.value)}
            />

            <div
              className="rounded-xl border border-dashed border-gray-300 dark:border-gray-600 bg-gray-50/70 dark:bg-gray-900/30 p-4 text-sm text-gray-600 dark:text-gray-300 outline-none focus:ring-2 focus:ring-primary-500"
              tabIndex={0}
              onPaste={handleAvatarPaste}
            >
              <div className="flex items-start gap-3">
                <ClipboardPaste className="w-4 h-4 mt-0.5 text-gray-400 shrink-0" />
                <div>
                  <p className="font-medium text-gray-800 dark:text-gray-100">
                    {t('portal.avatarPasteTitle')}
                  </p>
                  <p className="mt-1 text-gray-500 dark:text-gray-400">
                    {t('portal.avatarPasteHint')}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                type="button"
                isLoading={saving}
                disabled={!hasProfileChanges || uploadingAvatar}
                onClick={handleProfileSave}
              >
                {t('portal.saveProfile')}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {showPasswordSection && (
        <section className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
            {t('portal.setPasswordTitle')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            {user?.has_password ? t('portal.passwordSectionChange') : t('portal.passwordSectionSet')}
          </p>
          <PortalSetPasswordForm hasPassword={Boolean(user?.has_password)} />
        </section>
      )}

      {user?.external_provider && (
        <section className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t('portal.password9235Hint')}
          </p>
        </section>
      )}

      <PortalAdvancedPanel hint={t('portal.accountAdvancedAiHint')}>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 -mt-2 mb-2">
          {t('portal.aiConfigManageTitle')}
        </h2>
        <PortalAiConfigManager />
      </PortalAdvancedPanel>
    </div>
  )
}
