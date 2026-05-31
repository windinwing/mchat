import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Puzzle,
  Upload,
  Trash2,
  Search,
  Loader2,
  RefreshCw,
  Link2,
  Download,
  ExternalLink,
  FolderOpen,
  Plus,
} from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate } from '@/lib/utils'
import { isServerOpsSkill } from '@/lib/skillUtils'
import { SkillFileBrowser } from '@/components/admin/SkillFileBrowser'

interface Skill {
  id: string
  name: string
  description?: string
  version?: string
  enabled: boolean
  skill_type: string
  config?: {
    secrets?: Record<string, string>
    prompt_body?: string
    [key: string]: unknown
  } | null
  created_at: string
  updated_at: string
}

interface CatalogItem {
  name: string
  title: string
  description?: string | null
  homepage?: string | null
  download_url?: string | null
  source?: string
}

export function SkillManager() {
  const { t } = useTranslation()
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [secretsJson, setSecretsJson] = useState('{}')
  const [savingSecrets, setSavingSecrets] = useState(false)
  const [reloading, setReloading] = useState(false)
  const [descriptionEdit, setDescriptionEdit] = useState('')
  const [installOpen, setInstallOpen] = useState(false)
  const [installSource, setInstallSource] = useState('')
  const [installName, setInstallName] = useState('')
  const [installing, setInstalling] = useState(false)
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogItems, setCatalogItems] = useState<CatalogItem[]>([])
  const [fileBrowserOpen, setFileBrowserOpen] = useState(false)
  const [fileBrowserSkillId, setFileBrowserSkillId] = useState('')
  const [fileBrowserSkillName, setFileBrowserSkillName] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [createType, setCreateType] = useState('tool')
  const [creating, setCreating] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadSkills()
  }, [])

  const loadSkills = async () => {
    try {
      const data = await api.get<Skill[]>('/skills')
      setSkills(data)
    } catch (err) {
      console.error('Failed to load skills:', err)
      toast(t('skills.toastLoadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const toggleSkill = async (id: string, enabled: boolean) => {
    try {
      const updated = await api.patch<Skill>(`/skills/${id}`, { enabled })
      setSkills((prev) => prev.map((s) => (s.id === id ? updated : s)))
      toast(enabled ? t('common.enabled') : t('common.disabled'), { type: 'success' })
    } catch (err: any) {
      console.error('Failed to toggle skill:', err)
      toast(t('skills.toastOperationFailed'), { type: 'error', message: err.message })
    }
  }

  const reloadFromDisk = async () => {
    setReloading(true)
    try {
      const res = await api.post<{
        reloaded: number
        message: string
        server_ops?: string[]
      }>('/skills/reload')
      const extra =
        res.server_ops?.length ?
          ` · 服务端运维: ${res.server_ops.join(', ')}（默认禁用）`
        : ''
      toast(
        (res.message || t('skills.toastReloadDone', { count: res.reloaded })) + extra,
        { type: 'success' }
      )
      await loadSkills()
    } catch (err: any) {
      toast(t('skills.toastSyncFailed'), { type: 'error', message: err.message })
    } finally {
      setReloading(false)
    }
  }

  const loadCatalog = async (query = '') => {
    setCatalogLoading(true)
    try {
      const data = await api.get<{ source: string; items: CatalogItem[] }>('/skills/catalog', {
        query,
        limit: '24',
      })
      setCatalogItems(data.items || [])
    } catch (err: any) {
      toast(t('skills.toastCatalogLoadFailed'), { type: 'error', message: err.message })
    } finally {
      setCatalogLoading(false)
    }
  }

  const openInstallDialog = async () => {
    setInstallOpen(true)
    if (catalogItems.length === 0) {
      await loadCatalog('')
    }
  }

  const installFromSource = async (source: string, nameHint?: string) => {
    const src = source.trim()
    if (!src) {
      toast(t('skills.toastInstallNeedSource'), { type: 'error' })
      return
    }
    setInstalling(true)
    try {
      await api.post<Skill>('/skills/install-url', {
        url: src,
        name: (nameHint || installName || '').trim() || undefined,
      })
      toast(t('skills.toastInstalled'), { type: 'success' })
      setInstallSource('')
      setInstallName('')
      setInstallOpen(false)
      await loadSkills()
    } catch (err: any) {
      toast(t('skills.toastInstallFailed'), { type: 'error', message: err.message })
    } finally {
      setInstalling(false)
    }
  }

  const deleteSkill = async (id: string, name: string) => {
    if (!window.confirm(t('skills.deleteConfirm', { name }))) return
    try {
      await api.delete(`/skills/${id}`)
      setSkills((prev) => prev.filter((s) => s.id !== id))
      toast(t('skills.toastDeleted'), { type: 'success' })
    } catch (err: any) {
      console.error('Failed to delete skill:', err)
      toast(t('skills.toastDeleteFailed'), { type: 'error', message: err.message })
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.name.endsWith('.zip')) {
      toast(t('skills.toastZipOnly'), { type: 'error' })
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await api.upload<Skill>('/skills/upload', formData)
      setUploadOpen(false)
      toast(t('skills.toastUploaded'), { type: 'success' })
      await loadSkills()
    } catch (err: any) {
      console.error('Failed to upload skill:', err)
      toast(t('skills.toastUploadFailed'), { type: 'error', message: err.message })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createName.trim()) return
    setCreating(true)
    try {
      await api.post<Skill>('/skills', {
        name: createName.trim(),
        description: createDescription.trim() || null,
        skill_type: createType,
      })
      setCreateOpen(false)
      setCreateName('')
      setCreateDescription('')
      setCreateType('tool')
      toast(t('skills.toastCreated'), { type: 'success' })
      await loadSkills()
    } catch (err: any) {
      toast(err.message || t('skills.toastOperationFailed'), { type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const filtered = skills.filter(
    (s) =>
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.description?.toLowerCase().includes(search.toLowerCase()),
  )

  const typeLabel = (skillType: string) =>
    skillType === 'builtin' ? t('skills.builtin') : t('skills.custom')

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="md" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="w-72">
          <Input
            placeholder={t('skills.searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex gap-2">
          <Button
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={() => setCreateOpen(true)}
            className="w-[150px]"
          >
            {t('skills.createSkill')}
          </Button>
          <Button
            variant="secondary"
            leftIcon={<Link2 className="w-4 h-4" />}
            onClick={openInstallDialog}
          >
            {t('skills.installFromUrl')}
          </Button>
          <Button
            variant="secondary"
            leftIcon={<RefreshCw className="w-4 h-4" />}
            onClick={reloadFromDisk}
            isLoading={reloading}
          >
            {t('skills.syncFromDisk')}
          </Button>
          <Button
            leftIcon={<Upload className="w-4 h-4" />}
            onClick={() => setUploadOpen(true)}
          >
            {t('skills.uploadOverwrite')}
          </Button>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip"
        aria-label={t('skills.uploadOverwrite')}
        className="hidden"
        onChange={handleUpload}
      />

      {/* Skill List */}
      {filtered.length === 0 ? (
        <Card>
          <CardContent>
            <div className="flex flex-col items-center py-12 text-gray-400">
              <Puzzle className="w-12 h-12 mb-3 opacity-50" />
              <p className="text-sm">{t('skills.emptySkills')}</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((skill) => (
            <Card key={skill.id}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center shrink-0">
                      <Puzzle className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                    </div>
                    <div className="min-w-0">
                      <h3
                        className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate cursor-pointer hover:text-primary-600"
                        onClick={() => {
                          setSelectedSkill(skill)
                          setSecretsJson(
                            JSON.stringify(skill.config?.secrets || {}, null, 2),
                          )
                          setDescriptionEdit(skill.description || '')
                          setDetailOpen(true)
                        }}
                      >
                        {skill.name}
                      </h3>
                      <p className="text-xs text-gray-400">
                        {typeLabel(skill.skill_type)}
                        {skill.version ? ` · v${skill.version}` : ''}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {isServerOpsSkill(skill) && (
                      <Badge variant="warning" size="sm">
                        {t('skills.scopeServerOps')}
                      </Badge>
                    )}
                    <Badge
                      variant={skill.skill_type === 'builtin' ? 'info' : 'default'}
                      size="sm"
                    >
                      {typeLabel(skill.skill_type)}
                    </Badge>
                  </div>
                </div>

                {skill.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mb-3">
                    {skill.description}
                  </p>
                )}

                <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={skill.enabled}
                      onChange={(checked) => toggleSkill(skill.id, checked)}
                    />
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {skill.enabled ? t('common.enabled') : t('common.disabled')}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => {
                        setFileBrowserSkillId(skill.id)
                        setFileBrowserSkillName(skill.name)
                        setFileBrowserOpen(true)
                      }}
                      aria-label={t('skills.browseFiles')}
                      title={t('skills.browseFiles')}
                      className="p-1.5 rounded text-gray-400 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                    >
                      <FolderOpen className="w-4 h-4" />
                    </button>
                    {skill.skill_type !== 'builtin' && (
                      <button
                        onClick={() => deleteSkill(skill.id, skill.name)}
                        aria-label={t('common.delete')}
                        title={t('common.delete')}
                        className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Skill Detail Dialog */}
      <Dialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={selectedSkill?.name || t('skills.skillDetailFallback')}
        size="md"
      >
        {selectedSkill && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant={selectedSkill.skill_type === 'builtin' ? 'info' : 'default'}>
                {typeLabel(selectedSkill.skill_type)}
              </Badge>
              <Badge variant={selectedSkill.enabled ? 'success' : 'default'}>
                {selectedSkill.enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
            </div>
            {selectedSkill.skill_type !== 'builtin' && (
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-800 dark:text-gray-200">
                  {t('common.description')}
                </label>
                <textarea
                  aria-label={t('common.description')}
                  className="w-full h-20 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-2"
                  value={descriptionEdit}
                  onChange={(e) => setDescriptionEdit(e.target.value)}
                />
              </div>
            )}
            {selectedSkill.skill_type === 'builtin' && selectedSkill.description && (
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {selectedSkill.description}
              </p>
            )}
            <div className="text-xs text-gray-400 space-y-1">
              <p>{t('skills.metaType', { type: typeLabel(selectedSkill.skill_type) })}</p>
              <p>{t('skills.metaCreatedAt', { date: formatDate(selectedSkill.created_at) })}</p>
              <p>{t('skills.metaUpdatedAt', { date: formatDate(selectedSkill.updated_at) })}</p>
            </div>

            {selectedSkill.skill_type !== 'builtin' && (
              <div className="space-y-2 pt-2 border-t border-gray-100 dark:border-gray-700">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                  {t('skills.secretsTitle')}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('skills.secretsHint')}
                  <code className="mx-1 px-1 bg-gray-100 dark:bg-gray-700 rounded">
                    {`{"API_KEY": "sk-xxx"}`}
                  </code>
                </p>
                <textarea
                  aria-label={t('skills.secretsTitle')}
                  className="w-full h-28 text-xs font-mono rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-3"
                  value={secretsJson}
                  onChange={(e) => setSecretsJson(e.target.value)}
                  placeholder='{"API_KEY": "your-key"}'
                />
                <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  isLoading={savingSecrets}
                  onClick={async () => {
                    if (!selectedSkill) return
                    setSavingSecrets(true)
                    try {
                      const secrets = JSON.parse(secretsJson || '{}')
                      const updated = await api.patch<Skill>(
                        `/skills/${selectedSkill.id}`,
                        {
                          description: descriptionEdit.trim() || null,
                          config: {
                            ...(selectedSkill.config || {}),
                            secrets,
                          },
                        },
                      )
                      setSkills((prev) =>
                        prev.map((s) => (s.id === updated.id ? updated : s)),
                      )
                      setSelectedSkill(updated)
                      toast(t('skills.toastSecretsSaved'), { type: 'success' })
                    } catch (err: any) {
                      toast(t('skills.toastSaveSecretsFailed'), {
                        type: 'error',
                        message: err.message || t('skills.toastInvalidJson'),
                      })
                    } finally {
                      setSavingSecrets(false)
                    }
                  }}
                >
                  {t('skills.saveConfig')}
                </Button>
                </div>
              </div>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('skills.footerZipHint')}
            </p>
          </div>
        )}
      </Dialog>

      {/* Upload Dialog */}
      <Dialog
        open={installOpen}
        onClose={() => setInstallOpen(false)}
        title={t('skills.dialogInstallTitle')}
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('skills.installHint')}
          </p>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_200px] gap-3 items-end">
            <Input
              label={t('skills.installSourceLabel')}
              value={installSource}
              onChange={(e) => setInstallSource(e.target.value)}
              placeholder={t('skills.installSourcePlaceholder')}
            />
            <Input
              label={t('skills.installNameHintLabel')}
              value={installName}
              onChange={(e) => setInstallName(e.target.value)}
              placeholder={t('skills.installNameHintPlaceholder')}
            />
          </div>

          <div className="flex justify-end">
            <Button
              leftIcon={<Download className="w-4 h-4" />}
              onClick={() => installFromSource(installSource)}
              isLoading={installing}
              disabled={!installSource.trim()}
            >
              {t('skills.installNow')}
            </Button>
          </div>

          <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-3 space-y-3">
            <div className="flex gap-2 items-end">
              <Input
                label={t('skills.catalogSearchLabel')}
                value={catalogQuery}
                onChange={(e) => setCatalogQuery(e.target.value)}
                placeholder={t('skills.catalogSearchPlaceholder')}
              />
              <Button
                variant="secondary"
                size="action"
                leftIcon={<Search className="w-4 h-4" />}
                onClick={() => loadCatalog(catalogQuery)}
                isLoading={catalogLoading}
              >
                {t('skills.catalogSearchAction')}
              </Button>
            </div>

            {catalogLoading ? (
              <div className="flex items-center justify-center py-8 text-gray-500">
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                {t('skills.catalogLoading')}
              </div>
            ) : catalogItems.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-3 text-center">
                {t('skills.catalogEmpty')}
              </p>
            ) : (
              <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                {catalogItems.map((item) => (
                  <div
                    key={`${item.source || 'clawhub'}-${item.name}`}
                    className="rounded-lg border border-gray-100 dark:border-gray-700 px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {item.title || item.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {item.description || item.name}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {item.homepage && (
                          <a
                            href={item.homepage}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 rounded text-gray-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20"
                            title={t('skills.openCatalogLink')}
                          >
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        )}
                        <Button
                          size="sm"
                          leftIcon={<Download className="w-4 h-4" />}
                          onClick={() => installFromSource(item.download_url || item.name, item.name)}
                          isLoading={installing}
                        >
                          {t('skills.installAction')}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setInstallOpen(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Create Skill Dialog */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('skills.dialogCreateTitle')}
        size="sm"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label={t('skills.createNameLabel')}
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            placeholder="my-skill"
            required
          />
          <Input
            label={t('skills.createDescriptionLabel')}
            value={createDescription}
            onChange={(e) => setCreateDescription(e.target.value)}
            placeholder={t('skills.createDescriptionLabel')}
          />
          <Input
            label={t('skills.createTypeLabel')}
            value={createType}
            onChange={(e) => setCreateType(e.target.value)}
            list="skill-types"
            placeholder="tool"
          />
          <datalist id="skill-types">
            <option value="tool" />
            <option value="function" />
            <option value="webhook" />
          </datalist>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" type="button" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" isLoading={creating}>
              {t('common.create')}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* File Browser */}
      <SkillFileBrowser
        skillId={fileBrowserSkillId}
        skillName={fileBrowserSkillName}
        open={fileBrowserOpen}
        onClose={() => setFileBrowserOpen(false)}
      />

      {/* Upload Dialog */}
      <Dialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title={t('skills.dialogUploadTitle')}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('skills.uploadZipHint')}
          </p>
          <pre className="text-xs bg-gray-50 dark:bg-gray-900 rounded-lg p-3 text-gray-600 dark:text-gray-400 overflow-x-auto">
{t('skills.uploadZipStructure')}
          </pre>
          <div
            className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-8 text-center hover:border-primary-500 transition-colors cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            {uploading ? (
              <Loader2 className="w-8 h-8 mx-auto mb-2 text-primary-600 animate-spin" />
            ) : (
              <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
            )}
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {uploading ? t('knowledge.uploading') : t('skills.uploadClickZip')}
            </p>
            <p className="text-xs text-gray-400 mt-1">{t('skills.uploadZipPackHint')}</p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setUploadOpen(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
