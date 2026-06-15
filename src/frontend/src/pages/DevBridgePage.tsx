import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  Code2,
  FileText,
  FolderOpen,
  Hammer,
  History,
  Loader2,
  RefreshCw,
  Rocket,
  RotateCcw,
  Save,
  Search,
  Server,
  Settings,
} from 'lucide-react'
import api from '@/lib/api'
import { DevBridgeSettingsPanel } from '@/components/admin/DevBridgeSettingsPanel'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { formatDate } from '@/lib/utils'

interface DevBridgeProvider {
  key: string
  title: string
  enabled: boolean
  capabilities: string[]
}

interface DevBridgeProject {
  slug: string
  name: string
  path: string
  has_build: boolean
  source_updated_at?: string | null
  build_updated_at?: string | null
  preview_path?: string | null
  readable_roots?: string[]
  top_level_files?: string[]
}

interface DevBridgeFileEntry {
  path: string
  name: string
  is_dir: boolean
  size: number
  updated_at?: string | null
}

interface DevBridgeChange {
  id: string
  provider: string
  project: string
  path: string
  summary?: string | null
  status: string
  actor_user_id: string
  created_at: string
  reverted_at?: string | null
}

interface DevBridgeBuild {
  id: string
  status: string
  created_at: string
  snapshot_dir?: string | null
  summary?: string | null
}

interface DevBridgeRelease {
  id: string
  status?: string
  is_current?: boolean
  created_at?: string
  play_url?: string | null
}

type DevBridgeTab = 'projects' | 'settings'

export function DevBridgePage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab: DevBridgeTab =
    searchParams.get('tab') === 'settings' ? 'settings' : 'projects'
  const [providers, setProviders] = useState<DevBridgeProvider[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  const [projects, setProjects] = useState<DevBridgeProject[]>([])
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [selectedProject, setSelectedProject] = useState<DevBridgeProject | null>(null)
  const [currentPath, setCurrentPath] = useState('')
  const [files, setFiles] = useState<DevBridgeFileEntry[]>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)
  const [changes, setChanges] = useState<DevBridgeChange[]>([])
  const [loadingChanges, setLoadingChanges] = useState(false)
  const [showChanges, setShowChanges] = useState(false)
  const [editingContent, setEditingContent] = useState('')
  const [builds, setBuilds] = useState<DevBridgeBuild[]>([])
  const [releases, setReleases] = useState<DevBridgeRelease[]>([])
  const [loadingBuilds, setLoadingBuilds] = useState(false)
  const [loadingReleases, setLoadingReleases] = useState(false)
  const [savingPatch, setSavingPatch] = useState(false)
  const [building, setBuilding] = useState(false)
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const [rollingBackId, setRollingBackId] = useState<string | null>(null)
  const [projectQuery, setProjectQuery] = useState('')
  const [permSet, setPermSet] = useState<Set<string>>(new Set())
  const canDevbridgeWrite = permSet.has('devbridge:write')
  const canDevbridgeSettings = permSet.has('devbridge:settings:read')

  useEffect(() => {
    api
      .get<{ permissions: string[] }>('/auth/permissions')
      .then((data) => setPermSet(new Set(data.permissions || [])))
      .catch(() => setPermSet(new Set()))
  }, [])

  useEffect(() => {
    if (activeTab === 'settings' && permSet.size > 0 && !canDevbridgeSettings) {
      setSearchParams({})
    }
  }, [activeTab, canDevbridgeSettings, permSet.size, setSearchParams])

  const filteredProjects = useMemo(() => {
    const q = projectQuery.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((project) => {
      const haystack = [project.slug, project.name, project.path || ''].join(' ').toLowerCase()
      return haystack.includes(q)
    })
  }, [projects, projectQuery])

  const loadProviders = useCallback(async () => {
    setLoadingProviders(true)
    try {
      const data = await api.get<DevBridgeProvider[]>('/devbridge/providers')
      setProviders(data || [])
      if (data?.length && !selectedProvider) {
        const first = data.find((p) => p.enabled) || data[0]
        setSelectedProvider(first.key)
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.loadProvidersFailed'), { type: 'error' })
    } finally {
      setLoadingProviders(false)
    }
  }, [selectedProvider, t])

  const loadProjects = useCallback(async (providerKey: string) => {
    setLoadingProjects(true)
    try {
      const data = await api.get<DevBridgeProject[]>(`/devbridge/providers/${providerKey}/projects`)
      setProjects(data || [])
    } catch (err) {
      setProjects([])
      toast(err instanceof Error ? err.message : t('devbridge.loadProjectsFailed'), { type: 'error' })
    } finally {
      setLoadingProjects(false)
    }
  }, [t])

  const loadProjectDetail = useCallback(async (providerKey: string, slug: string) => {
    try {
      const detail = await api.get<DevBridgeProject>(`/devbridge/providers/${providerKey}/projects/${slug}`)
      setSelectedProject(detail)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.loadProjectFailed'), { type: 'error' })
    }
  }, [t])

  const loadFiles = useCallback(async (providerKey: string, slug: string, path: string) => {
    setLoadingFiles(true)
    try {
      const data = await api.get<{ items: DevBridgeFileEntry[] }>(
        `/devbridge/providers/${providerKey}/projects/${slug}/files`,
        { path },
      )
      setFiles(data.items || [])
    } catch (err) {
      setFiles([])
      toast(err instanceof Error ? err.message : t('devbridge.loadFilesFailed'), { type: 'error' })
    } finally {
      setLoadingFiles(false)
    }
  }, [t])

  const loadFileContent = useCallback(async (providerKey: string, slug: string, path: string) => {
    setLoadingFile(true)
    setSelectedFile(path)
    try {
      const data = await api.get<{ content: string }>(
        `/devbridge/providers/${providerKey}/projects/${slug}/file`,
        { path },
      )
      setFileContent(data.content)
      setEditingContent(data.content)
    } catch (err) {
      setFileContent(null)
      setEditingContent('')
      toast(err instanceof Error ? err.message : t('devbridge.loadFileFailed'), { type: 'error' })
    } finally {
      setLoadingFile(false)
    }
  }, [t])

  const loadBuilds = useCallback(async (providerKey: string, slug: string) => {
    setLoadingBuilds(true)
    try {
      const data = await api.get<DevBridgeBuild[]>(`/devbridge/providers/${providerKey}/projects/${slug}/builds`)
      setBuilds(data || [])
    } catch {
      setBuilds([])
    } finally {
      setLoadingBuilds(false)
    }
  }, [])

  const loadReleases = useCallback(async (providerKey: string, slug: string) => {
    setLoadingReleases(true)
    try {
      const data = await api.get<DevBridgeRelease[]>(`/devbridge/providers/${providerKey}/projects/${slug}/releases`)
      setReleases(data || [])
    } catch {
      setReleases([])
    } finally {
      setLoadingReleases(false)
    }
  }, [])

  const loadChanges = useCallback(async (providerKey: string, slug: string) => {
    setLoadingChanges(true)
    try {
      const data = await api.get<DevBridgeChange[]>(`/devbridge/providers/${providerKey}/projects/${slug}/changes`)
      setChanges(data || [])
    } catch (err) {
      setChanges([])
      if (err instanceof Error && !err.message.includes('403') && !err.message.includes('disabled')) {
        toast(err.message, { type: 'error' })
      }
    } finally {
      setLoadingChanges(false)
    }
  }, [])

  useEffect(() => {
    void loadProviders()
  }, [loadProviders])

  useEffect(() => {
    if (!selectedProvider) return
    setSelectedProject(null)
    setCurrentPath('')
    setFiles([])
    setSelectedFile(null)
    setFileContent(null)
    setChanges([])
    setProjectQuery('')
    void loadProjects(selectedProvider)
  }, [selectedProvider, loadProjects])

  const handleSelectProject = (project: DevBridgeProject) => {
    if (!selectedProvider) return
    const provider = providers.find((p) => p.key === selectedProvider)
    setSelectedProject(project)
    setCurrentPath('')
    setSelectedFile(null)
    setFileContent(null)
    setEditingContent('')
    void loadProjectDetail(selectedProvider, project.slug)
    void loadFiles(selectedProvider, project.slug, '')
    if (provider?.capabilities.includes('build:list')) void loadBuilds(selectedProvider, project.slug)
    if (provider?.capabilities.includes('release:list')) void loadReleases(selectedProvider, project.slug)
  }

  const handleEnterDir = (entry: DevBridgeFileEntry) => {
    if (!selectedProvider || !selectedProject || !entry.is_dir) return
    setCurrentPath(entry.path)
    setSelectedFile(null)
    setFileContent(null)
    void loadFiles(selectedProvider, selectedProject.slug, entry.path)
  }

  const handleGoUp = () => {
    if (!selectedProvider || !selectedProject || !currentPath) return
    const parts = currentPath.split('/').filter(Boolean)
    parts.pop()
    const parent = parts.join('/')
    setCurrentPath(parent)
    setSelectedFile(null)
    setFileContent(null)
    void loadFiles(selectedProvider, selectedProject.slug, parent)
  }

  const activeProvider = providers.find((p) => p.key === selectedProvider)
  const canListChanges = activeProvider?.capabilities.includes('change:list')
  const canPatch = activeProvider?.capabilities.includes('file:patch') && canDevbridgeWrite
  const canBuild = activeProvider?.capabilities.includes('build') && canDevbridgeWrite
  const canPublish = activeProvider?.capabilities.includes('release:publish') && canDevbridgeWrite

  const handleSavePatch = async () => {
    if (!selectedProvider || !selectedProject || !selectedFile) return
    setSavingPatch(true)
    try {
      await api.post(`/devbridge/providers/${selectedProvider}/projects/${selectedProject.slug}/patch`, {
        path: selectedFile,
        content: editingContent,
      })
      setFileContent(editingContent)
      toast(t('devbridge.patchSaved'), { type: 'success' })
      void loadChanges(selectedProvider, selectedProject.slug)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.patchFailed'), { type: 'error' })
    } finally {
      setSavingPatch(false)
    }
  }

  const handleBuild = async () => {
    if (!selectedProvider || !selectedProject) return
    setBuilding(true)
    try {
      await api.post(`/devbridge/providers/${selectedProvider}/projects/${selectedProject.slug}/build`, {})
      toast(t('devbridge.buildStarted'), { type: 'success' })
      void loadBuilds(selectedProvider, selectedProject.slug)
      void loadProjects(selectedProvider)
      if (selectedProject) void loadProjectDetail(selectedProvider, selectedProject.slug)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.buildFailed'), { type: 'error' })
    } finally {
      setBuilding(false)
    }
  }

  const handleRevert = async (changeId: string) => {
    if (!selectedProvider || !selectedProject) return
    try {
      await api.post(`/devbridge/providers/${selectedProvider}/projects/${selectedProject.slug}/changes/${changeId}/revert`, {})
      toast(t('devbridge.revertDone'), { type: 'success' })
      void loadChanges(selectedProvider, selectedProject.slug)
      if (selectedFile) void loadFileContent(selectedProvider, selectedProject.slug, selectedFile)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.revertFailed'), { type: 'error' })
    }
  }

  const handlePublish = async (buildId: string) => {
    if (!selectedProvider || !selectedProject) return
    setPublishingId(buildId)
    try {
      const result = await api.post<{ play_url?: string }>(
        `/devbridge/providers/${selectedProvider}/projects/${selectedProject.slug}/publish`,
        { build_id: buildId },
      )
      toast(t('devbridge.publishDone'), { type: 'success', message: result.play_url })
      void loadReleases(selectedProvider, selectedProject.slug)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.publishFailed'), { type: 'error' })
    } finally {
      setPublishingId(null)
    }
  }

  const handleRollback = async (releaseId: string) => {
    if (!selectedProvider || !selectedProject) return
    setRollingBackId(releaseId)
    try {
      const result = await api.post<{ play_url?: string }>(
        `/devbridge/providers/${selectedProvider}/projects/${selectedProject.slug}/rollback`,
        { release_id: releaseId },
      )
      toast(t('devbridge.rollbackDone'), { type: 'success', message: result.play_url })
      void loadReleases(selectedProvider, selectedProject.slug)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('devbridge.rollbackFailed'), { type: 'error' })
    } finally {
      setRollingBackId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Code2 className="w-7 h-7 text-primary-600" />
            {t('devbridge.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('devbridge.pageSubtitle')}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-100/80 dark:bg-gray-900/50 p-0.5">
            <button
              type="button"
              onClick={() => setSearchParams({})}
              className={cn(
                'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                activeTab === 'projects'
                  ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200',
              )}
            >
              {t('devbridge.tabProjects')}
            </button>
            {canDevbridgeSettings && (
              <button
                type="button"
                onClick={() => setSearchParams({ tab: 'settings' })}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors inline-flex items-center gap-1.5',
                  activeTab === 'settings'
                    ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200',
                )}
              >
                <Settings className="w-3.5 h-3.5" />
                {t('devbridge.tabSettings')}
              </button>
            )}
          </div>
          {activeTab === 'projects' && (
            <Button
              variant="secondary"
              leftIcon={<RefreshCw className="w-4 h-4" />}
              onClick={() => {
                void loadProviders()
                if (selectedProvider) void loadProjects(selectedProvider)
              }}
            >
              {t('common.refresh')}
            </Button>
          )}
        </div>
      </div>

      {activeTab === 'settings' ? (
        <DevBridgeSettingsPanel />
      ) : loadingProviders ? (
        <div className="flex justify-center py-16"><Spinner size="md" /></div>
      ) : providers.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-gray-500 dark:text-gray-400">
            {t('devbridge.noProviders')}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5">
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">{t('devbridge.providers')}</div>
            <div className="flex flex-wrap gap-2">
              {providers.map((provider) => (
                <button
                  key={provider.key}
                  type="button"
                  onClick={() => setSelectedProvider(provider.key)}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors',
                    selectedProvider === provider.key
                      ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-800 dark:text-primary-200'
                      : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200',
                  )}
                >
                  <span className="font-medium">{provider.title}</span>
                  <Badge variant={provider.enabled ? 'success' : 'default'} className="text-[10px] px-1.5 py-0">
                    {provider.enabled ? t('common.enabled') : t('common.disabled')}
                  </Badge>
                  <span className="text-[11px] text-gray-400 dark:text-gray-500">{provider.key}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-6 xl:grid-cols-12 gap-4">
          <Card className="xl:col-span-2 min-w-0">
            <CardHeader className="pb-2 space-y-2 px-3 py-2">
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('devbridge.projects')}</div>
              {activeProvider?.enabled && projects.length > 0 && (
                <Input
                  value={projectQuery}
                  onChange={(e) => setProjectQuery(e.target.value)}
                  placeholder={t('devbridge.projectSearchPlaceholder')}
                  leftIcon={<Search className="w-3.5 h-3.5" />}
                  className="text-xs"
                  aria-label={t('devbridge.projectSearchPlaceholder')}
                />
              )}
            </CardHeader>
            <CardContent className="px-2 pb-2">
              {!activeProvider?.enabled ? (
                <p className="text-sm text-amber-700 dark:text-amber-300">{t('devbridge.providerDisabledHint')}</p>
              ) : loadingProjects ? (
                <div className="flex justify-center py-8"><Spinner size="sm" /></div>
              ) : projects.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">{t('devbridge.noProjects')}</p>
              ) : filteredProjects.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">{t('devbridge.noProjectMatches')}</p>
              ) : (
                <div className="space-y-1 max-h-[calc(100vh-16rem)] overflow-y-auto">
                  {projectQuery.trim() && (
                    <p className="text-[11px] text-gray-500 dark:text-gray-400 px-1">
                      {t('devbridge.projectSearchCount', { count: filteredProjects.length, total: projects.length })}
                    </p>
                  )}
                  {filteredProjects.map((project) => (
                    <button
                      key={project.slug}
                      type="button"
                      onClick={() => handleSelectProject(project)}
                      className={cn(
                        'w-full text-left rounded-md border px-2 py-1.5 transition-colors',
                        selectedProject?.slug === project.slug
                          ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                          : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800',
                      )}
                    >
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate" title={project.name}>
                        {project.name}
                      </div>
                      <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate" title={project.slug}>
                        {project.slug}
                      </div>
                      <div className="mt-0.5">
                        <Badge variant={project.has_build ? 'success' : 'default'} className="text-[10px] px-1 py-0">
                          {project.has_build ? t('devbridge.hasBuild') : t('devbridge.noBuild')}
                        </Badge>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-10 min-w-0">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {selectedProject ? selectedProject.name : t('devbridge.projectDetail')}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {selectedProject && selectedProvider && canBuild && (
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={building ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Hammer className="w-3.5 h-3.5" />}
                      onClick={() => void handleBuild()}
                      disabled={building}
                    >
                      {t('devbridge.build')}
                    </Button>
                  )}
                  {selectedProject && selectedProvider && canListChanges && (
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<History className="w-3.5 h-3.5" />}
                      onClick={() => {
                        setShowChanges((v) => !v)
                        if (!showChanges) void loadChanges(selectedProvider, selectedProject.slug)
                      }}
                    >
                      {t('devbridge.changes')}
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {!selectedProject ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">{t('devbridge.selectProjectHint')}</p>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                    <div className="flex items-start gap-2 text-gray-600 dark:text-gray-300">
                      <Server className="w-4 h-4 mt-0.5 shrink-0" />
                      <span className="break-all">{selectedProject.path}</span>
                    </div>
                    {selectedProject.source_updated_at && (
                      <div className="text-gray-500 dark:text-gray-400">
                        {t('devbridge.sourceUpdated')}: {formatDate(selectedProject.source_updated_at)}
                      </div>
                    )}
                    {selectedProject.build_updated_at && (
                      <div className="text-gray-500 dark:text-gray-400">
                        {t('devbridge.buildUpdated')}: {formatDate(selectedProject.build_updated_at)}
                      </div>
                    )}
                    {selectedProject.readable_roots && selectedProject.readable_roots.length > 0 && (
                      <div className="text-gray-500 dark:text-gray-400">
                        {t('devbridge.readableRoots')}: {selectedProject.readable_roots.join(', ')}
                      </div>
                    )}
                  </div>

                  {showChanges && (
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('devbridge.recentChanges')}</div>
                      {loadingChanges ? (
                        <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin" /></div>
                      ) : changes.length === 0 ? (
                        <p className="text-xs text-gray-500">{t('devbridge.noChanges')}</p>
                      ) : (
                        <div className="space-y-2 max-h-40 overflow-y-auto">
                          {changes.map((change) => (
                            <div key={change.id} className="text-xs border-b border-gray-100 dark:border-gray-800 pb-2 last:border-0">
                              <div className="font-medium text-gray-800 dark:text-gray-200">{change.path}</div>
                              <div className="text-gray-500">{change.status} · {formatDate(change.created_at)}</div>
                              {change.summary && <div className="text-gray-500">{change.summary}</div>}
                              {canPatch && change.status === 'applied' && selectedProvider && selectedProject && (
                                <button
                                  type="button"
                                  className="mt-1 text-primary-600 hover:underline"
                                  onClick={() => void handleRevert(change.id)}
                                >
                                  {t('devbridge.revert')}
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
                      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-200">
                          <FolderOpen className="w-4 h-4" />
                          {currentPath || '/'}
                        </div>
                        {currentPath && (
                          <button type="button" onClick={handleGoUp} className="text-xs text-primary-600 hover:underline">
                            {t('devbridge.goUp')}
                          </button>
                        )}
                      </div>
                      <div className="max-h-64 overflow-y-auto">
                        {loadingFiles ? (
                          <div className="flex justify-center py-8"><Spinner size="sm" /></div>
                        ) : files.length === 0 ? (
                          <p className="text-xs text-gray-500 p-3">{t('devbridge.noFiles')}</p>
                        ) : (
                          files.map((entry) => (
                            <button
                              key={entry.path}
                              type="button"
                              onClick={() => (entry.is_dir ? handleEnterDir(entry) : selectedProvider && selectedProject && loadFileContent(selectedProvider, selectedProject.slug, entry.path))}
                              className={`w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-2 ${
                                selectedFile === entry.path ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                              }`}
                            >
                              {entry.is_dir ? <FolderOpen className="w-3.5 h-3.5 text-amber-500" /> : <FileText className="w-3.5 h-3.5 text-blue-500" />}
                              <span className="truncate">{entry.name}</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
                      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700">
                        <div className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                          {selectedFile || t('devbridge.filePreview')}
                        </div>
                        {canPatch && selectedFile && fileContent != null && (
                          <Button
                            size="sm"
                            leftIcon={savingPatch ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                            onClick={() => void handleSavePatch()}
                            disabled={savingPatch}
                          >
                            {t('common.save')}
                          </Button>
                        )}
                      </div>
                      <div className="max-h-64 overflow-auto p-3">
                        {loadingFile ? (
                          <div className="flex justify-center py-8"><Spinner size="sm" /></div>
                        ) : fileContent == null ? (
                          <p className="text-xs text-gray-500">{t('devbridge.selectFileHint')}</p>
                        ) : canPatch ? (
                          <textarea
                            className="w-full min-h-[220px] text-xs font-mono rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2"
                            value={editingContent}
                            onChange={(e) => setEditingContent(e.target.value)}
                          />
                        ) : (
                          <pre className="text-xs whitespace-pre-wrap break-all text-gray-800 dark:text-gray-200 font-mono">{fileContent}</pre>
                        )}
                      </div>
                    </div>
                  </div>

                  {(canBuild || canPublish) && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      {canBuild && (
                        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('devbridge.builds')}</div>
                          {loadingBuilds ? (
                            <div className="flex justify-center py-4"><Spinner size="sm" /></div>
                          ) : builds.length === 0 ? (
                            <p className="text-xs text-gray-500">{t('devbridge.noBuilds')}</p>
                          ) : (
                            <div className="space-y-2 max-h-40 overflow-y-auto">
                              {builds.map((build) => (
                                <div key={build.id} className="text-xs flex items-center justify-between gap-2 border-b border-gray-100 dark:border-gray-800 pb-2">
                                  <div>
                                    <div className="font-medium">{build.id.slice(0, 8)} · {build.status}</div>
                                    <div className="text-gray-500">{formatDate(build.created_at)}</div>
                                  </div>
                                  {canPublish && build.status === 'built' && selectedProvider && selectedProject && (
                                    <Button
                                      size="sm"
                                      variant="secondary"
                                      leftIcon={publishingId === build.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Rocket className="w-3 h-3" />}
                                      onClick={() => void handlePublish(build.id)}
                                      disabled={publishingId === build.id}
                                    >
                                      {t('devbridge.publish')}
                                    </Button>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {canPublish && (
                        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('devbridge.releases')}</div>
                          {loadingReleases ? (
                            <div className="flex justify-center py-4"><Spinner size="sm" /></div>
                          ) : releases.length === 0 ? (
                            <p className="text-xs text-gray-500">{t('devbridge.noReleases')}</p>
                          ) : (
                            <div className="space-y-2 max-h-40 overflow-y-auto">
                              {releases.map((release) => (
                                <div key={release.id} className="text-xs flex items-center justify-between gap-2 border-b border-gray-100 dark:border-gray-800 pb-2">
                                  <div>
                                    <div className="font-medium">
                                      {release.id.slice(0, 8)}
                                      {release.is_current ? ` · ${t('devbridge.currentRelease')}` : ''}
                                    </div>
                                    {release.play_url && <div className="text-gray-500 break-all">{release.play_url}</div>}
                                  </div>
                                  {!release.is_current && selectedProvider && selectedProject && (
                                    <Button
                                      size="sm"
                                      variant="secondary"
                                      leftIcon={rollingBackId === release.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                                      onClick={() => void handleRollback(release.id)}
                                      disabled={rollingBackId === release.id}
                                    >
                                      {t('devbridge.rollback')}
                                    </Button>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
          </div>
        </div>
      )}
    </div>
  )
}
