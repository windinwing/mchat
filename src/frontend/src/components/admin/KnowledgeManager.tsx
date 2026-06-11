import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  Upload,
  FileText,
  Trash2,
  Search,
  Loader2,
  CheckCircle,
  AlertCircle,
  Settings2,
} from 'lucide-react'
import api from '@/lib/api'
import {
  defaultRag,
  mapDocument,
  mapKnowledgeBase,
  mapReindexResult,
  mapUploadedEmbeddingModel,
  ragSettingsToPayload,
  type UploadedEmbeddingModel,
  type ChunkStrategy,
  type KnowledgeBase,
  type KnowledgeBaseRagSettings,
  type KnowledgeDocument,
  type RetrievalMode,
  type RerankProvider,
} from '@/lib/knowledgeApi'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { Switch } from '@/components/ui/Switch'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate } from '@/lib/utils'
import { Select } from '@/components/ui/Select'

interface GroupOption {
  id: string
  name: string
}

/** Shared form styles for RAG settings (dark-mode safe + compact). */
const ragLabel = 'block text-xs font-medium text-gray-600 dark:text-gray-300 mb-0.5'
const ragSelect =
  'w-full h-8 rounded-md border border-gray-300 bg-white px-2.5 text-sm text-gray-900 ' +
  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ' +
  'dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 dark:color-scheme-dark'
const ragHint = 'text-[11px] leading-snug text-gray-500 dark:text-gray-400'
const ragSectionTitle = 'text-xs font-semibold text-gray-700 dark:text-gray-200'
const ragSection = 'border-t border-gray-200 dark:border-gray-700 pt-3 space-y-2'
const ragInputCompact =
  '[&_label]:text-xs [&_label]:mb-0.5 [&_label]:text-gray-600 dark:[&_label]:text-gray-300 [&_input]:h-8 [&_input]:py-1.5 [&_input]:text-sm'
const milvusInput =
  'h-8 rounded-md border border-gray-300 bg-white px-2.5 text-sm text-gray-900 ' +
  'placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 ' +
  'dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 dark:placeholder:text-gray-500'

export function KnowledgeManager() {
  const { t } = useTranslation()
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [milvusEnabled, setMilvusEnabled] = useState(false)
  const [milvusHost, setMilvusHost] = useState('localhost')
  const [milvusPort, setMilvusPort] = useState('19530')
  const [milvusSaving, setMilvusSaving] = useState(false)
  const [milvusTesting, setMilvusTesting] = useState(false)
  const [globalEmbedProvider, setGlobalEmbedProvider] = useState('ollama')
  const [globalEmbedModel, setGlobalEmbedModel] = useState('nomic-embed-text')
  const [globalEmbedApiBase, setGlobalEmbedApiBase] = useState('http://localhost:11434')
  const [globalEmbedDimension, setGlobalEmbedDimension] = useState('768')
  const [globalEmbedApiKey, setGlobalEmbedApiKey] = useState('')
  const [globalEmbedSaving, setGlobalEmbedSaving] = useState(false)
  const [selectedKB, setSelectedKB] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [kbName, setKbName] = useState('')
  const [kbDesc, setKbDesc] = useState('')
  const [search, setSearch] = useState('')
  const [uploading, setUploading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [ragSettings, setRagSettings] = useState<KnowledgeBaseRagSettings>(defaultRag)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [reindexRechunk, setReindexRechunk] = useState(true)
  const [reindexing, setReindexing] = useState(false)
  const [settingsTab, setSettingsTab] = useState<'form' | 'json'>('form')
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [embeddingModels, setEmbeddingModels] = useState<UploadedEmbeddingModel[]>([])
  const [groups, setGroups] = useState<GroupOption[]>([])
  const [scopeValue, setScopeValue] = useState('personal')
  const [modelUploading, setModelUploading] = useState(false)
  const embeddingModelInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const embeddingProvider =
    ragSettings.embeddingProvider?.trim().toLowerCase() || 'openai'
  const readyEmbeddingModels = embeddingModels.filter((m) => m.status === 'ready')

  const selectedKbMeta = knowledgeBases.find((kb) => kb.id === selectedKB)

  const docStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
      case 'indexed':
        return t('knowledge.docStatusCompleted')
      case 'processing':
        return t('knowledge.docStatusProcessing')
      case 'failed':
        return t('knowledge.docStatusFailed')
      default:
        return t('knowledge.docStatusPending')
    }
  }

  useEffect(() => {
    loadKnowledgeBases()
    loadPlatformKnowledgeSettings()
    loadEmbeddingModels()
    api.get<GroupOption[]>('/groups/mine').then(setGroups).catch(() => setGroups([]))
  }, [])

  useEffect(() => {
    setSelectedKB(null)
    setDocuments([])
    void loadKnowledgeBases()
  }, [scopeValue])

  const selectedGroupId = scopeValue.startsWith('group:')
    ? scopeValue.slice('group:'.length)
    : undefined
  const createKbPayload = {
    name: kbName,
    description: kbDesc,
    ...(selectedGroupId ? { group_id: selectedGroupId } : {}),
  }

  const loadEmbeddingModels = async () => {
    try {
      const data = await api.get<Record<string, unknown>[]>('/knowledge/embedding-models')
      setEmbeddingModels(data.map(mapUploadedEmbeddingModel))
    } catch (err) {
      console.error('Failed to load embedding models:', err)
    }
  }

  const handleUploadEmbeddingModel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files?.length) return
    const file = files[0]
    setModelUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('name', file.name.replace(/\.zip$/i, ''))
      const res = await api.upload<{ model: Record<string, unknown> }>(
        '/knowledge/embedding-models/upload',
        formData,
      )
      const model = mapUploadedEmbeddingModel(res.model)
      setEmbeddingModels((prev) => [model, ...prev])
      toast(t('knowledge.toastModelUploaded'), { type: 'success' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastModelUploadFailed'), { type: 'error', message })
    } finally {
      setModelUploading(false)
      if (embeddingModelInputRef.current) embeddingModelInputRef.current.value = ''
    }
  }

  const handleDeleteEmbeddingModel = async (modelId: string) => {
    if (!window.confirm(t('knowledge.deleteModelConfirm'))) return
    try {
      await api.delete(`/knowledge/embedding-models/${modelId}`)
      setEmbeddingModels((prev) => prev.filter((m) => m.id !== modelId))
      toast(t('knowledge.toastModelDeleted'), { type: 'success' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastModelDeleteFailed'), { type: 'error', message })
    }
  }

  const handleSelectLocalModel = (modelId: string) => {
    const model = readyEmbeddingModels.find((m) => m.id === modelId)
    if (!model) return
    setRagSettings((s) => ({
      ...s,
      embeddingProvider: 'local',
      embeddingModel: model.id,
      embeddingDimension: model.dimension,
      embeddingApiBase: undefined,
    }))
  }

  useEffect(() => {
    if (selectedKB) {
      loadDocuments(selectedKB)
      const meta = knowledgeBases.find((k) => k.id === selectedKB)
      if (meta) {
        setRagSettings({
          ...defaultRag,
          chunkStrategy: meta.chunkStrategy,
          chunkSize: meta.chunkSize,
          chunkOverlap: meta.chunkOverlap,
          chunkMinSize: meta.chunkMinSize,
          chunkSemanticThreshold: meta.chunkSemanticThreshold,
          chunkParentEnabled: meta.chunkParentEnabled,
          embeddingProvider: meta.embeddingProvider ?? globalEmbedProvider,
          embeddingModel: meta.embeddingModel ?? globalEmbedModel,
          embeddingApiBase: meta.embeddingApiBase ?? (globalEmbedApiBase || undefined),
          embeddingDimension:
            meta.embeddingDimension ??
            (Number(globalEmbedDimension) || defaultRag.embeddingDimension),
          retrievalMode: meta.retrievalMode,
          retrievalTopK: meta.retrievalTopK,
          retrievalCandidateK: meta.retrievalCandidateK,
          rerankEnabled: meta.rerankEnabled,
          rerankTopN: meta.rerankTopN,
          rerankProvider: meta.rerankProvider,
          rerankModel: meta.rerankModel,
          retrievalBm25Enabled: meta.retrievalBm25Enabled,
          retrievalBm25K1: meta.retrievalBm25K1,
          retrievalBm25B: meta.retrievalBm25B,
          retrievalQueryRewriteEnabled: meta.retrievalQueryRewriteEnabled,
          retrievalQueryRewriteCount: meta.retrievalQueryRewriteCount,
        })
      }
    }
  }, [selectedKB, knowledgeBases])

  const loadPlatformKnowledgeSettings = async () => {
    try {
      const data = await api.get<Record<string, unknown>>('/settings')
      setMilvusEnabled(Boolean(data.milvus_enabled))
      setMilvusHost(String(data.milvus_host ?? 'localhost'))
      setMilvusPort(String(data.milvus_port ?? 19530))
      setGlobalEmbedProvider(String(data.embedding_provider ?? 'ollama'))
      setGlobalEmbedModel(String(data.embedding_model ?? 'nomic-embed-text'))
      setGlobalEmbedApiBase(String(data.embedding_api_base ?? 'http://localhost:11434'))
      setGlobalEmbedDimension(String(data.embedding_dimension ?? 768))
      setGlobalEmbedApiKey(String(data.embedding_api_key ?? ''))
    } catch (err) {
      console.error('Failed to load platform knowledge settings:', err)
    }
  }

  const saveGlobalEmbeddingSettings = async () => {
    setGlobalEmbedSaving(true)
    try {
      const payload: Record<string, unknown> = {
        embedding_provider: globalEmbedProvider,
        embedding_model: globalEmbedModel,
        embedding_api_base: globalEmbedApiBase,
        embedding_dimension: Number(globalEmbedDimension) || 768,
      }
      if (globalEmbedApiKey.trim()) {
        payload.embedding_api_key = globalEmbedApiKey.trim()
      }
      await api.put('/settings', payload)
      toast(t('knowledge.toastGlobalEmbeddingSaved'), { type: 'success' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastSaveFailed'), { type: 'error', message })
    } finally {
      setGlobalEmbedSaving(false)
    }
  }

  const saveMilvusSettings = async () => {
    setMilvusSaving(true)
    try {
      await api.put('/settings', {
        milvus_enabled: milvusEnabled,
        milvus_host: milvusHost,
        milvus_port: Number(milvusPort) || 19530,
      })
      toast(t('knowledge.toastMilvusSaved'), { type: 'success' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastSaveFailed'), { type: 'error', message })
    } finally {
      setMilvusSaving(false)
    }
  }

  const testMilvus = async () => {
    setMilvusTesting(true)
    try {
      const result = await api.post<{ ok: boolean; message: string }>(
        '/settings/milvus/test',
        {
          milvus_enabled: milvusEnabled,
          milvus_host: milvusHost,
          milvus_port: Number(milvusPort) || 19530,
        },
      )
      toast(result.message, { type: result.ok ? 'success' : 'error' })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastConnectionTestFailed'), { type: 'error', message })
    } finally {
      setMilvusTesting(false)
    }
  }

  const loadKnowledgeBases = async () => {
    try {
      const data = await api.get<Record<string, unknown>[]>('/knowledge/bases', selectedGroupId ? { group_id: selectedGroupId } : undefined)
      setKnowledgeBases(data.map(mapKnowledgeBase))
    } catch (err) {
      console.error('Failed to load knowledge bases:', err)
      toast(t('knowledge.toastLoadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const loadDocuments = async (kbId: string) => {
    try {
      const data = await api.get<Record<string, unknown>[]>(
        `/knowledge/bases/${kbId}/documents`,
      )
      setDocuments(data.map(mapDocument))
    } catch (err) {
      console.error('Failed to load documents:', err)
    }
  }

  const handleCreate = async () => {
    if (!kbName.trim()) return
    try {
      const kb = await api.post<Record<string, unknown>>('/knowledge/bases', createKbPayload)
      setKnowledgeBases((prev) => [...prev, mapKnowledgeBase(kb)])
      toast(t('knowledge.toastKbCreated'), { type: 'success' })
      setCreateOpen(false)
      setKbName('')
      setKbDesc('')
    } catch (err) {
      console.error('Failed to create knowledge base:', err)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || !selectedKB) return

    setUploading(true)
    try {
      for (let i = 0; i < files.length; i++) {
        const formData = new FormData()
        formData.append('file', files[i])
        const doc = await api.upload<Record<string, unknown>>(
          `/knowledge/bases/${selectedKB}/import-file`,
          formData,
        )
        const mapped = mapDocument(doc)
        setDocuments((prev) => [...prev, mapped])
        if (mapped.status === 'failed') {
          toast(t('knowledge.toastParseFailed', { name: mapped.filename }), {
            type: 'error',
          })
        }
      }
      toast(t('knowledge.toastUploadComplete'), { type: 'success' })
      loadKnowledgeBases()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastUploadFailed'), { type: 'error', message })
      console.error('Failed to upload document:', err)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async (docId: string) => {
    if (!selectedKB) return
    try {
      await api.delete(`/knowledge/documents/${docId}`)
      setDocuments((prev) => prev.filter((d) => d.id !== docId))
    } catch (err) {
      console.error('Failed to delete document:', err)
    }
  }

  const handleReindex = async () => {
    if (!selectedKB) return
    if (
      !window.confirm(
        t('knowledge.reindexConfirm', {
          count: selectedKbMeta?.documentCount ?? 0,
        }),
      )
    ) {
      return
    }
    setReindexing(true)
    try {
      const raw = await api.post<Record<string, unknown>>(
        `/knowledge/bases/${selectedKB}/reindex`,
        { rechunk: reindexRechunk },
      )
      const result = mapReindexResult(raw)
      await loadKnowledgeBases()
      if (selectedKB) loadDocuments(selectedKB)
      toast(
        t('knowledge.toastReindexDone', {
          succeeded: result.succeeded,
          total: result.total,
          failed: result.failed,
        }),
        { type: result.failed > 0 ? 'warning' : 'success' },
      )
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastReindexFailed'), { type: 'error', message })
    } finally {
      setReindexing(false)
    }
  }

  const handleSaveRagSettings = async () => {
    if (!selectedKB) return
    setSettingsSaving(true)
    try {
      const kb = await api.patch<Record<string, unknown>>(
        `/knowledge/bases/${selectedKB}`,
        ragSettingsToPayload(ragSettings),
      )
      const mapped = mapKnowledgeBase(kb)
      setKnowledgeBases((prev) =>
        prev.map((item) => (item.id === mapped.id ? mapped : item)),
      )
      toast(t('knowledge.toastRagSaved'), { type: 'success' })
      setSettingsOpen(false)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.failed')
      toast(t('knowledge.toastSaveFailed'), { type: 'error', message })
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleDeleteKB = async (kbId: string) => {
    try {
      await api.delete(`/knowledge/bases/${kbId}`)
      setKnowledgeBases((prev) => prev.filter((kb) => kb.id !== kbId))
      if (selectedKB === kbId) {
        setSelectedKB(null)
        setDocuments([])
      }
    } catch (err) {
      console.error('Failed to delete knowledge base:', err)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const filteredDocs = documents.filter((d) =>
    d.filename.toLowerCase().includes(search.toLowerCase()),
  )

  const docStatusVariant = (status: string): 'default' | 'success' | 'warning' | 'danger' => {
    switch (status) {
      case 'completed': return 'success'
      case 'processing': return 'warning'
      case 'failed': return 'danger'
      default: return 'default'
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="md" />
      </div>
    )
  }

  return (
    <div className="space-y-3 h-full flex flex-col">
      <Card>
        <CardContent className="py-3 space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h3 className="text-sm font-medium text-gray-800 dark:text-gray-100">
                {t('knowledge.localModelsTitle')}
              </h3>
              <p className={`${ragHint} mt-0.5`}>{t('knowledge.localModelsHint')}</p>
            </div>
            <Button
              size="sm"
              leftIcon={<Upload className="w-4 h-4" />}
              isLoading={modelUploading}
              onClick={() => embeddingModelInputRef.current?.click()}
            >
              {t('knowledge.uploadModelZip')}
            </Button>
            <input
              ref={embeddingModelInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              aria-label={t('knowledge.uploadModelZip')}
              title={t('knowledge.uploadModelZip')}
              onChange={handleUploadEmbeddingModel}
            />
          </div>
          {embeddingModels.length > 0 ? (
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {embeddingModels.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between gap-2 text-sm py-1 px-2 rounded-md bg-gray-50 dark:bg-gray-900/60 border border-transparent dark:border-gray-700/80"
                >
                  <div className="min-w-0">
                    <span className="font-medium text-gray-800 dark:text-gray-100">{m.name}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                      {m.status === 'ready'
                        ? t('knowledge.modelDim', { dim: m.dimension })
                        : m.status === 'failed'
                          ? t('knowledge.modelFailed')
                          : t('knowledge.modelProcessing')}
                    </span>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {m.status === 'ready' ? (
                      <Button size="sm" variant="ghost" onClick={() => handleSelectLocalModel(m.id)}>
                        {t('knowledge.useModel')}
                      </Button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => handleDeleteEmbeddingModel(m.id)}
                      className="p-1 text-gray-400 hover:text-red-500"
                      aria-label={t('common.delete')}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className={ragHint}>{t('knowledge.noLocalModels')}</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="py-3 space-y-3">
          <div>
            <h3 className="text-sm font-medium text-gray-800 dark:text-gray-100">
              {t('knowledge.globalEmbeddingTitle')}
            </h3>
            <p className={`${ragHint} mt-0.5`}>{t('knowledge.globalEmbeddingHint')}</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className={ragLabel}>{t('knowledge.embeddingProvider')}</label>
              <select
                className={ragSelect}
                value={globalEmbedProvider}
                title={t('knowledge.embeddingProvider')}
                onChange={(e) => setGlobalEmbedProvider(e.target.value)}
              >
                <option value="ollama">Ollama</option>
                <option value="openai">OpenAI API</option>
                <option value="openai-compatible">{t('knowledge.providerCompatible')}</option>
                <option value="local">{t('knowledge.providerLocal')}</option>
              </select>
            </div>
            <div>
              <label className={ragLabel}>{t('knowledge.embeddingModel')}</label>
              <input
                className={`w-full ${milvusInput}`}
                value={globalEmbedModel}
                aria-label={t('knowledge.embeddingModel')}
                title={t('knowledge.embeddingModel')}
                onChange={(e) => setGlobalEmbedModel(e.target.value)}
                placeholder={
                  globalEmbedProvider === 'ollama' ? 'nomic-embed-text' : 'text-embedding-3-small'
                }
              />
            </div>
            <div>
              <label className={ragLabel}>{t('knowledge.embeddingApiBase')}</label>
              <input
                className={`w-full ${milvusInput}`}
                value={globalEmbedApiBase}
                aria-label={t('knowledge.embeddingApiBase')}
                title={t('knowledge.embeddingApiBase')}
                onChange={(e) => setGlobalEmbedApiBase(e.target.value)}
                placeholder={
                  globalEmbedProvider === 'ollama'
                    ? 'http://localhost:11434'
                    : 'https://api.openai.com/v1'
                }
              />
            </div>
            <div>
              <label className={ragLabel}>{t('knowledge.embeddingDimension')}</label>
              <input
                type="number"
                className={`w-full ${milvusInput}`}
                value={globalEmbedDimension}
                aria-label={t('knowledge.embeddingDimension')}
                title={t('knowledge.embeddingDimension')}
                onChange={(e) => setGlobalEmbedDimension(e.target.value.replace(/[^\d]/g, ''))}
              />
            </div>
          </div>
          {globalEmbedProvider === 'local' && (
            <p className={ragHint}>{t('knowledge.globalLocalEmbedHint')}</p>
          )}
          {(globalEmbedProvider === 'openai' ||
            globalEmbedProvider === 'openai-compatible') && (
            <div className="max-w-md">
              <label className={ragLabel}>{t('knowledge.embeddingApiKey')}</label>
              <input
                type="password"
                autoComplete="off"
                className={`w-full ${milvusInput}`}
                value={globalEmbedApiKey}
                onChange={(e) => setGlobalEmbedApiKey(e.target.value)}
                placeholder={t('knowledge.embeddingApiKeyPlaceholder')}
              />
            </div>
          )}
          <div>
            <Button size="sm" onClick={saveGlobalEmbeddingSettings} isLoading={globalEmbedSaving}>
              {t('common.save')}
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="py-3 space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap lg:flex-nowrap">
            <div className="min-w-0 shrink-0">
              <h3 className="text-sm font-medium text-gray-800 dark:text-gray-100">{t('knowledge.milvusTitle')}</h3>
              <p className={`${ragHint} mt-0.5`}>{t('knowledge.milvusHint')}</p>
            </div>
            <div className="flex flex-wrap lg:flex-nowrap items-center gap-2 ml-auto">
              <div className="shrink-0">
                <Switch checked={milvusEnabled} onChange={setMilvusEnabled} />
              </div>
              {milvusEnabled && (
                <>
                  <input
                    aria-label={t('knowledge.host')}
                    title={t('knowledge.host')}
                    value={milvusHost}
                    onChange={(e) => setMilvusHost(e.target.value)}
                    placeholder={t('knowledge.host')}
                    className={`w-48 ${milvusInput}`}
                  />
                  <input
                    aria-label={t('knowledge.port')}
                    title={t('knowledge.port')}
                    value={milvusPort}
                    onChange={(e) => setMilvusPort(e.target.value.replace(/[^\d]/g, ''))}
                    placeholder={t('knowledge.port')}
                    className={`w-24 ${milvusInput}`}
                  />
                  <Button variant="secondary" size="sm" onClick={testMilvus} isLoading={milvusTesting}>{t('knowledge.testConnection')}</Button>
                </>
              )}
              <Button size="sm" onClick={saveMilvusSettings} isLoading={milvusSaving}>{t('common.save')}</Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <div className="flex gap-6 flex-1 min-h-0">
      {/* Knowledge Base List */}
      <div className="w-72 shrink-0 space-y-3">
        <Select
          label={t('knowledge.scopeLabel', '知识库作用域')}
          value={scopeValue}
          options={[
            { value: 'personal', label: t('knowledge.scopePersonal', '个人知识库') },
            ...groups.map((group) => ({
              value: `group:${group.id}`,
              label: `${t('knowledge.scopeGroup', '群组')}: ${group.name}`,
            })),
          ]}
          onChange={(e) => setScopeValue(e.target.value)}
        />
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('knowledge.kbListTitle')}</h3>
          <Button size="sm" variant="ghost" onClick={() => setCreateOpen(true)}>
            + {t('knowledge.newKb')}
          </Button>
        </div>

        {knowledgeBases.length === 0 ? (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center py-8 text-gray-400">
                <BookOpen className="w-8 h-8 mb-2 opacity-50" />
                <p className="text-xs">{t('knowledge.emptyKb')}</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {knowledgeBases.map((kb) => (
              <Card
                key={kb.id}
                hover
                className={selectedKB === kb.id ? 'ring-2 ring-primary-500' : ''}
                onClick={() => setSelectedKB(kb.id)}
              >
                <CardContent className="py-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {kb.name}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {t('knowledge.documentCount', { count: kb.documentCount })}
                        {kb.needsReindex ? (
                          <span className="text-amber-600 dark:text-amber-400 ml-1">
                            · {t('knowledge.needsReindexBadge')}
                          </span>
                        ) : null}
                      </p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteKB(kb.id)
                      }}
                      aria-label={t('common.delete')}
                      title={t('common.delete')}
                      className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="flex-1 min-w-0">
        {selectedKB ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('knowledge.docListTitle')}
                {selectedKbMeta ? (
                  <span className="text-gray-400 font-normal ml-2">
                    · {selectedKbMeta.name}
                  </span>
                ) : null}
              </h3>
              <div className="flex gap-2">
                <Button
                  size="actionWide"
                  variant="secondary"
                  leftIcon={<Settings2 className="w-4 h-4" />}
                  onClick={() => setSettingsOpen(true)}
                >
                  {t('knowledge.ragSettings')}
                </Button>
                <Input
                  placeholder={t('knowledge.searchDocsPlaceholder')}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  leftIcon={<Search className="w-4 h-4" />}
                  className="w-60"
                />
                <Button
                  size="actionWide"
                  leftIcon={<Upload className="w-4 h-4" />}
                  onClick={() => {
                    setUploadOpen(true)
                    fileInputRef.current?.click()
                  }}
                >
                  {t('knowledge.uploadDocument')}
                </Button>
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              aria-label={t('knowledge.uploadDocument')}
              title={t('knowledge.uploadDocument')}
              onChange={handleUpload}
              accept=".txt,.pdf,.doc,.docx,.md"
            />

            {filteredDocs.length === 0 ? (
              <Card>
                <CardContent>
                  <div className="flex flex-col items-center py-12 text-gray-400">
                    <FileText className="w-12 h-12 mb-3 opacity-50" />
                    <p className="text-sm">{t('knowledge.emptyDocs')}</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {filteredDocs.map((doc) => (
                  <Card key={doc.id}>
                    <CardContent className="py-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 min-w-0">
                          <FileText className="w-5 h-5 text-gray-400 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                              {doc.filename}
                            </p>
                            <p className="text-xs text-gray-400">
                              {formatFileSize(doc.fileSize)} · {formatDate(doc.createdAt)}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant={docStatusVariant(doc.status)} size="sm">
                            {doc.status === 'processing' && (
                              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                            )}
                            {doc.status === 'completed' && (
                              <CheckCircle className="w-3 h-3 mr-1" />
                            )}
                            {doc.status === 'failed' && (
                              <AlertCircle className="w-3 h-3 mr-1" />
                            )}
                            {docStatusLabel(doc.status)}
                          </Badge>
                          <button
                            onClick={() => handleDelete(doc.id)}
                            aria-label={t('common.delete')}
                            title={t('common.delete')}
                            className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {uploading && (
              <div className="flex items-center justify-center py-4 text-sm text-gray-500">
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {t('knowledge.uploading')}
              </div>
            )}
          </div>
        ) : (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <BookOpen className="w-16 h-16 mb-4 opacity-30" />
                <p className="text-sm">{t('knowledge.selectKbHint')}</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <Dialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title={t('knowledge.dialogRagTitle')}
        size="md"
        className="max-w-md"
        bodyClassName="p-4 pt-3"
      >
        <div className="space-y-3 max-h-[75vh] overflow-y-auto pr-0.5 text-gray-900 dark:text-gray-100">
          {selectedKbMeta?.needsReindex ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-700/80 dark:bg-amber-950/40 px-2.5 py-1.5 text-xs text-amber-900 dark:text-amber-100">
              {t('knowledge.needsReindexHint')}
            </div>
          ) : null}
          {/* Tabs */}
          <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 pb-2">
            <button
              type="button"
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                settingsTab === 'form'
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
              onClick={() => {
                setSettingsTab('form')
                setJsonError('')
              }}
            >
              {t('knowledge.ragSettingsTabForm')}
            </button>
            <button
              type="button"
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                settingsTab === 'json'
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
              onClick={() => {
                setJsonText(JSON.stringify(ragSettingsToPayload(ragSettings), null, 2))
                setJsonError('')
                setSettingsTab('json')
              }}
            >
              {t('knowledge.ragSettingsTabJson')}
            </button>
          </div>
          {settingsTab === 'form' ? (
          <>
          <div>
            <label className={ragLabel}>{t('knowledge.chunkStrategy')}</label>
            <select
              className={ragSelect}
              value={ragSettings.chunkStrategy}
              title={t('knowledge.chunkStrategy')}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  chunkStrategy: e.target.value as ChunkStrategy,
                }))
              }
            >
              <option value="fixed">{t('knowledge.chunkFixed')}</option>
              <option value="paragraph">{t('knowledge.chunkParagraph')}</option>
              <option value="markdown">{t('knowledge.chunkMarkdown')}</option>
              <option value="semantic">{t('knowledge.chunkSemantic')}</option>
            </select>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Input
              className={ragInputCompact}
              label={t('knowledge.chunkSize')}
              type="number"
              value={String(ragSettings.chunkSize)}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  chunkSize: Number(e.target.value) || 500,
                }))
              }
            />
            <Input
              className={ragInputCompact}
              label={t('knowledge.chunkOverlap')}
              type="number"
              value={String(ragSettings.chunkOverlap)}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  chunkOverlap: Number(e.target.value) || 0,
                }))
              }
            />
            <Input
              className={ragInputCompact}
              label={t('knowledge.chunkMinSize')}
              type="number"
              value={String(ragSettings.chunkMinSize)}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  chunkMinSize: Number(e.target.value) || 80,
                }))
              }
            />
          </div>
          {ragSettings.chunkStrategy === 'semantic' && (
            <div className="flex items-center gap-3">
              <Input
                className={ragInputCompact}
                label={t('knowledge.chunkSemanticThreshold')}
                type="number"
                step={0.05}
                min={0.5}
                max={0.95}
                value={String(ragSettings.chunkSemanticThreshold)}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    chunkSemanticThreshold: Number(e.target.value) || 0.7,
                  }))
                }
              />
              <div className="text-xs text-gray-500 mt-5">
                {t('knowledge.chunkSemanticThresholdHint')}
              </div>
            </div>
          )}
          <div
            className={
              'flex items-center gap-2 rounded-md border px-2.5 py-2 mt-2 ' +
              'border-gray-200 bg-gray-50/80 dark:border-gray-600 dark:bg-gray-900/50'
            }
          >
            <Switch
              checked={ragSettings.chunkParentEnabled}
              onChange={(v) =>
                setRagSettings((s) => ({ ...s, chunkParentEnabled: v }))
              }
            />
            <span className="text-xs text-gray-700 dark:text-gray-200">
              {t('knowledge.chunkParentEnabled')}
            </span>
            <span className="text-[10px] text-gray-400 ml-auto">
              {t('knowledge.chunkParentEnabledHint')}
            </span>
          </div>
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.embeddingSection')}</p>
            <div>
              <label className={ragLabel}>{t('knowledge.embeddingProvider')}</label>
              <select
                className={ragSelect}
                value={embeddingProvider}
                title={t('knowledge.embeddingProvider')}
                onChange={(e) => {
                  const v = e.target.value
                  setRagSettings((s) => ({
                    ...s,
                    embeddingProvider: v,
                    embeddingModel: v === 'local' ? s.embeddingModel : undefined,
                    embeddingApiBase:
                      v === 'local' ? undefined : s.embeddingApiBase,
                  }))
                }}
              >
                <option value="openai">OpenAI API</option>
                <option value="openai-compatible">{t('knowledge.providerCompatible')}</option>
                <option value="local">{t('knowledge.providerLocal')}</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            {embeddingProvider === 'local' ? (
              <div>
                <label className={ragLabel}>{t('knowledge.localModelSelect')}</label>
                <select
                  className={ragSelect}
                  value={ragSettings.embeddingModel ?? ''}
                  title={t('knowledge.localModelSelect')}
                  onChange={(e) => handleSelectLocalModel(e.target.value)}
                >
                  <option value="">{t('knowledge.pickLocalModel')}</option>
                  {readyEmbeddingModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.dimension}d)
                    </option>
                  ))}
                </select>
                <p className={`${ragHint} mt-1`}>{t('knowledge.localModelReindexHint')}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <Input
                  className={ragInputCompact}
                  label={t('knowledge.embeddingModel')}
                  value={ragSettings.embeddingModel ?? ''}
                  onChange={(e) =>
                    setRagSettings((s) => ({
                      ...s,
                      embeddingModel: e.target.value || undefined,
                    }))
                  }
                  placeholder={
                    embeddingProvider === 'ollama'
                      ? 'nomic-embed-text'
                      : 'text-embedding-3-small'
                  }
                />
                <Input
                  className={ragInputCompact}
                  label={t('knowledge.embeddingApiBase')}
                  value={ragSettings.embeddingApiBase ?? ''}
                  onChange={(e) =>
                    setRagSettings((s) => ({
                      ...s,
                      embeddingApiBase: e.target.value || undefined,
                    }))
                  }
                  placeholder={
                    embeddingProvider === 'ollama'
                      ? 'http://localhost:11434'
                      : 'https://api.openai.com/v1'
                  }
                />
              </div>
            )}
            <Input
              className={ragInputCompact}
              label={t('knowledge.embeddingDimension')}
              type="number"
              value={String(ragSettings.embeddingDimension)}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  embeddingDimension: Number(e.target.value) || 1536,
                }))
              }
            />
          </div>
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.retrievalSection')}</p>
            <select
              className={ragSelect}
              value={ragSettings.retrievalMode}
              title={t('knowledge.retrievalSection')}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  retrievalMode: e.target.value as RetrievalMode,
                }))
              }
            >
              <option value="hybrid">{t('knowledge.retrievalHybrid')}</option>
              <option value="vector">{t('knowledge.retrievalVector')}</option>
              <option value="keyword">{t('knowledge.retrievalKeyword')}</option>
            </select>
            <div className="grid grid-cols-2 gap-2">
              <Input
                className={ragInputCompact}
                label={t('knowledge.retrievalTopK')}
                type="number"
                min={1}
                max={50}
                value={String(ragSettings.retrievalTopK)}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    retrievalTopK: Number(e.target.value) || 5,
                  }))
                }
              />
              <Input
                className={ragInputCompact}
                label={t('knowledge.retrievalCandidateK')}
                type="number"
                min={5}
                max={100}
                value={String(ragSettings.retrievalCandidateK)}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    retrievalCandidateK: Number(e.target.value) || 20,
                  }))
                }
              />
            </div>
            <p className={ragHint}>{t('knowledge.retrievalCountHint')}</p>
            <div
              className={
                'flex items-center gap-2 rounded-md border px-2.5 py-2 ' +
                'border-gray-200 bg-gray-50/80 dark:border-gray-600 dark:bg-gray-900/50'
              }
            >
              <Switch
                checked={ragSettings.rerankEnabled}
                onChange={(v) =>
                  setRagSettings((s) => ({ ...s, rerankEnabled: v }))
                }
              />
              <span className="text-xs text-gray-700 dark:text-gray-200 shrink-0">
                {t('knowledge.rerankEnabled')}
              </span>
              {ragSettings.rerankEnabled && (
                <span className="flex items-center gap-1 text-xs text-gray-700 dark:text-gray-200">
                  Top{' '}
                  <input
                    type="number"
                    min={1}
                    max={20}
                    aria-label={t('knowledge.rerankEnabled')}
                    title={t('knowledge.rerankEnabled')}
                    className="w-12 h-6 rounded border border-gray-300 bg-white px-1 text-center text-xs text-gray-900
                      focus:outline-none focus:ring-1 focus:ring-primary-500
                      dark:border-gray-500 dark:bg-gray-800 dark:text-gray-100"
                    value={ragSettings.rerankTopN}
                    onChange={(e) =>
                      setRagSettings((s) => ({
                        ...s,
                        rerankTopN: Number(e.target.value) || 5,
                      }))
                    }
                  />
                </span>
              )}
            </div>
          </div>
          {/* Reranker provider */}
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.rerankProviderSection')}</p>
            <p className={`${ragHint} -mt-1`}>{t('knowledge.rerankProviderHint')}</p>
            <select
              className={ragSelect}
              value={ragSettings.rerankProvider}
              title={t('knowledge.rerankProvider')}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  rerankProvider: e.target.value as RerankProvider,
                }))
              }
            >
              <option value="lexical">{t('knowledge.rerankProviderLexical')}</option>
              <option value="cohere">{t('knowledge.rerankProviderCohere')}</option>
              <option value="bge">{t('knowledge.rerankProviderBge')}</option>
              <option value="cross-encoder">{t('knowledge.rerankProviderCrossEncoder')}</option>
              <option value="none">{t('knowledge.rerankProviderNone')}</option>
            </select>
            {(ragSettings.rerankProvider === 'cohere' ||
              ragSettings.rerankProvider === 'bge' ||
              ragSettings.rerankProvider === 'cross-encoder') && (
              <Input
                className={ragInputCompact}
                label={t('knowledge.rerankModel')}
                value={ragSettings.rerankModel ?? ''}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    rerankModel: e.target.value || undefined,
                  }))
                }
                placeholder={t('knowledge.rerankModelPlaceholder')}
              />
            )}
          </div>
          {/* BM25 */}
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.bm25Section')}</p>
            <div
              className={
                'flex items-center gap-2 rounded-md border px-2.5 py-2 ' +
                'border-gray-200 bg-gray-50/80 dark:border-gray-600 dark:bg-gray-900/50'
              }
            >
              <Switch
                checked={ragSettings.retrievalBm25Enabled}
                onChange={(v) =>
                  setRagSettings((s) => ({ ...s, retrievalBm25Enabled: v }))
                }
              />
              <span className="text-xs text-gray-700 dark:text-gray-200">
                {t('knowledge.bm25Enabled')}
              </span>
              <span className="text-[10px] text-gray-400 ml-auto">
                {t('knowledge.bm25EnabledHint')}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input
                className={ragInputCompact}
                label={t('knowledge.bm25K1')}
                type="number"
                step={0.1}
                min={0.5}
                max={3.0}
                disabled={!ragSettings.retrievalBm25Enabled}
                value={String(ragSettings.retrievalBm25K1)}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    retrievalBm25K1: Number(e.target.value) || 1.5,
                  }))
                }
              />
              <Input
                className={ragInputCompact}
                label={t('knowledge.bm25B')}
                type="number"
                step={0.05}
                min={0.0}
                max={1.0}
                disabled={!ragSettings.retrievalBm25Enabled}
                value={String(ragSettings.retrievalBm25B)}
                onChange={(e) =>
                  setRagSettings((s) => ({
                    ...s,
                    retrievalBm25B: Number(e.target.value) || 0.75,
                  }))
                }
              />
            </div>
          </div>
          {/* Query rewrite */}
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.queryRewriteSection')}</p>
            <div
              className={
                'flex items-center gap-2 rounded-md border px-2.5 py-2 ' +
                'border-gray-200 bg-gray-50/80 dark:border-gray-600 dark:bg-gray-900/50'
              }
            >
              <Switch
                checked={ragSettings.retrievalQueryRewriteEnabled}
                onChange={(v) =>
                  setRagSettings((s) => ({
                    ...s,
                    retrievalQueryRewriteEnabled: v,
                  }))
                }
              />
              <span className="text-xs text-gray-700 dark:text-gray-200">
                {t('knowledge.queryRewriteEnabled')}
              </span>
              <span className="text-[10px] text-gray-400 ml-auto">
                {t('knowledge.queryRewriteEnabledHint')}
              </span>
            </div>
            <Input
              className={ragInputCompact}
              label={t('knowledge.queryRewriteCount')}
              type="number"
              min={1}
              max={5}
              disabled={!ragSettings.retrievalQueryRewriteEnabled}
              value={String(ragSettings.retrievalQueryRewriteCount)}
              onChange={(e) =>
                setRagSettings((s) => ({
                  ...s,
                  retrievalQueryRewriteCount: Number(e.target.value) || 3,
                }))
              }
            />
          </div>
          <div className={ragSection}>
            <p className={ragSectionTitle}>{t('knowledge.reindexSection')}</p>
            <p className={`${ragHint} -mt-1`}>{t('knowledge.reindexSectionHint')}</p>
            <div
              className={
                'flex flex-wrap items-center gap-2 rounded-md border px-2.5 py-2 ' +
                'border-gray-200 bg-gray-50/80 dark:border-gray-600 dark:bg-gray-900/50'
              }
            >
              <Switch checked={reindexRechunk} onChange={setReindexRechunk} />
              <span className="text-xs text-gray-700 dark:text-gray-200 flex-1 min-w-[10rem]">
                {t('knowledge.reindexRechunk')}
              </span>
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0"
                onClick={handleReindex}
                isLoading={reindexing}
                disabled={!selectedKB || (selectedKbMeta?.documentCount ?? 0) === 0}
              >
                {t('knowledge.reindexRun')}
              </Button>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1 border-t border-gray-200 dark:border-gray-700">
            <Button variant="secondary" onClick={() => setSettingsOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSaveRagSettings} isLoading={settingsSaving}>
              {t('common.save')}
            </Button>
          </div>
          </>
          ) : (
          <>
            {/* JSON editor */}
            <div className="space-y-2">
              <textarea
                className="w-full h-[55vh] font-mono text-xs p-3 rounded-md border border-gray-300 bg-gray-50
                  text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500
                  dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 resize-none"
                value={jsonText}
                aria-label={t('knowledge.ragSettingsTabJson')}
                title={t('knowledge.ragSettingsTabJson')}
                onChange={(e) => {
                  setJsonText(e.target.value)
                  setJsonError('')
                }}
                spellCheck={false}
              />
              {jsonError && (
                <p className="text-xs text-red-600 dark:text-red-400">{jsonError}</p>
              )}
              <p className="text-[11px] text-gray-400">{t('knowledge.jsonEditorHint')}</p>
            </div>
            <div className="flex justify-end gap-2 pt-1 border-t border-gray-200 dark:border-gray-700">
              <Button variant="secondary" onClick={() => setSettingsOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                onClick={() => {
                  try {
                    const parsed = JSON.parse(jsonText)
                    // Basic validation: should be an object
                    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
                      setJsonError(t('knowledge.jsonEditorInvalidObject'))
                      return
                    }
                    // Apply parsed settings
                    const mapped = mapKnowledgeBase({
                      ...parsed,
                      id: selectedKB || '',
                      name: selectedKbMeta?.name || '',
                      document_count: selectedKbMeta?.documentCount || 0,
                      created_at: selectedKbMeta?.createdAt || '',
                      updated_at: selectedKbMeta?.updatedAt || '',
                    })
                    setRagSettings({
                      ...defaultRag,
                      chunkStrategy: mapped.chunkStrategy,
                      chunkSize: mapped.chunkSize,
                      chunkOverlap: mapped.chunkOverlap,
                      chunkMinSize: mapped.chunkMinSize,
                      chunkSemanticThreshold: mapped.chunkSemanticThreshold,
                      chunkParentEnabled: mapped.chunkParentEnabled,
                      embeddingProvider: mapped.embeddingProvider,
                      embeddingModel: mapped.embeddingModel,
                      embeddingApiBase: mapped.embeddingApiBase,
                      embeddingDimension: mapped.embeddingDimension,
                      retrievalMode: mapped.retrievalMode,
                      retrievalTopK: mapped.retrievalTopK,
                      retrievalCandidateK: mapped.retrievalCandidateK,
                      rerankEnabled: mapped.rerankEnabled,
                      rerankTopN: mapped.rerankTopN,
                      rerankProvider: mapped.rerankProvider,
                      rerankModel: mapped.rerankModel,
                      retrievalBm25Enabled: mapped.retrievalBm25Enabled,
                      retrievalBm25K1: mapped.retrievalBm25K1,
                      retrievalBm25B: mapped.retrievalBm25B,
                      retrievalQueryRewriteEnabled: mapped.retrievalQueryRewriteEnabled,
                      retrievalQueryRewriteCount: mapped.retrievalQueryRewriteCount,
                    })
                    setSettingsTab('form')
                    setJsonError('')
                    toast(t('knowledge.toastJsonApplied'), { type: 'success' })
                  } catch (err) {
                    setJsonError(
                      err instanceof SyntaxError
                        ? t('knowledge.jsonEditorParseError', { message: err.message })
                        : t('common.failed'),
                    )
                  }
                }}
                disabled={!jsonText.trim()}
              >
                {t('knowledge.jsonEditorApply')}
              </Button>
            </div>
          </>
          )}
        </div>
      </Dialog>

      {/* Create Knowledge Base Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title={t('knowledge.dialogCreateKbTitle')} size="sm">
        <div className="space-y-4">
          <Input
            label={t('common.name')}
            value={kbName}
            onChange={(e) => setKbName(e.target.value)}
            placeholder={t('knowledge.kbNamePlaceholder')}
          />
          <Input
            label={t('knowledge.descriptionOptional')}
            value={kbDesc}
            onChange={(e) => setKbDesc(e.target.value)}
            placeholder={t('knowledge.kbDescriptionPlaceholder')}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={!kbName.trim()}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Dialog>
      </div>
    </div>
  )
}
