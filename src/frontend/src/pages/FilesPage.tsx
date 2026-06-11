import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FolderOpen, FolderPlus, Upload, Trash2, Download, RefreshCw, ArrowUp, Folder } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { formatDate } from '@/lib/utils'

interface TenantFileEntry {
  path: string
  name: string
  size: number
  is_dir: boolean
  modified_at?: string | null
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export function FilesPage() {
  const { t } = useTranslation()
  const [files, setFiles] = useState<TenantFileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [currentDir, setCurrentDir] = useState('user')
  const [showNewDir, setShowNewDir] = useState(false)
  const [newDirName, setNewDirName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<{ items: TenantFileEntry[] }>('/workspace/files', {
        subdir: currentDir,
      })
      const items = res.items || []
      // Dirs first, then files
      items.sort((a, b) => {
        if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      setFiles(items)
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : t('files.loadFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [t, currentDir])

  useEffect(() => {
    loadFiles()
  }, [loadFiles])

  const handleUpload = async (list: FileList | null) => {
    if (!list?.length) return
    setUploading(true)
    try {
      for (const file of Array.from(list)) {
        const form = new FormData()
        form.append('file', file)
        form.append('subdir', currentDir)
        await api.upload('/workspace/files/upload', form)
      }
      toast(t('files.uploadSuccess'), { type: 'success' })
      await loadFiles()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : t('files.uploadFailed'), { type: 'error' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async (path: string) => {
    if (!window.confirm(t('files.deleteConfirm', { name: path }))) return
    try {
      await api.delete('/workspace/files', { subdir: currentDir, path })
      toast(t('files.deleteSuccess'), { type: 'success' })
      await loadFiles()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : t('files.deleteFailed'), { type: 'error' })
    }
  }

  const handleDownload = async (path: string, name: string) => {
    try {
      await api.download('/workspace/files/download', { subdir: currentDir, path }, name)
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : t('files.downloadFailed', 'Download failed'), { type: 'error' })
    }
  }

  const handleCreateDir = async () => {
    const name = newDirName.trim()
    if (!name) return
    try {
      await api.post('/workspace/files/mkdir', { subdir: currentDir, name })
      toast(t('files.dirCreated'), { type: 'success' })
      setShowNewDir(false)
      setNewDirName('')
      await loadFiles()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : t('files.dirCreateFailed'), { type: 'error' })
    }
  }

  const navigateTo = (dirName: string) => {
    setCurrentDir(`${currentDir}/${dirName}`)
  }

  const navigateUp = () => {
    const parts = currentDir.split('/')
    if (parts.length <= 1) return
    setCurrentDir(parts.slice(0, -1).join('/'))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <FolderOpen className="w-7 h-7 text-primary-600" />
            {t('files.pageTitle')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {currentDir}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadFiles} leftIcon={<RefreshCw className="w-4 h-4" />}>
            {t('common.refresh')}
          </Button>
          <Button variant="outline" onClick={() => setShowNewDir(true)} leftIcon={<FolderPlus className="w-4 h-4" />}>
            {t('files.newDir')}
          </Button>
          <Button onClick={() => fileInputRef.current?.click()} isLoading={uploading} leftIcon={<Upload className="w-4 h-4" />}>
            {t('files.upload')}
          </Button>
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => handleUpload(e.target.files)} />
        </div>
      </div>

      {showNewDir && (
        <div className="flex gap-2 items-end bg-white dark:bg-gray-800 border rounded-xl p-4">
          <Input
            label={t('files.dirName')}
            value={newDirName}
            onChange={(e) => setNewDirName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateDir()}
            placeholder={t('files.dirNamePlaceholder')}
            className="max-w-64"
            autoFocus
          />
          <Button onClick={handleCreateDir} size="sm" className="w-[135px]">{t('common.create')}</Button>
          <Button variant="secondary" size="sm" onClick={() => setShowNewDir(false)} className="w-[135px]">{t('common.cancel')}</Button>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16"><Spinner size="lg" /></div>
        ) : files.length === 0 ? (
          <p className="text-center text-gray-500 py-16">{t('files.empty')}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50 text-left text-gray-500">
              <tr>
                <th className="px-4 py-3 font-medium">{t('files.colName')}</th>
                <th className="px-4 py-3 font-medium">{t('files.colSize')}</th>
                <th className="px-4 py-3 font-medium">{t('files.colModified')}</th>
                <th className="px-4 py-3 font-medium text-right">{t('files.colActions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {currentDir !== 'user' && (
                <tr className="hover:bg-gray-50/50 dark:hover:bg-gray-900/20 cursor-pointer" onClick={navigateUp}>
                  <td className="px-4 py-3 font-medium text-primary-600" colSpan={4}>
                    <span className="flex items-center gap-2">
                      <ArrowUp className="w-4 h-4" />
                      {t('files.parentDir')}
                    </span>
                  </td>
                </tr>
              )}
              {files.map((file) => (
                <tr key={file.path} className="hover:bg-gray-50/50 dark:hover:bg-gray-900/20">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                    {file.is_dir ? (
                      <button
                        type="button"
                        onClick={() => navigateTo(file.name)}
                        className="flex items-center gap-2 text-primary-600 hover:underline"
                      >
                        <Folder className="w-4 h-4" />
                        {file.name}
                      </button>
                    ) : (
                      file.name
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                    {file.is_dir ? '—' : formatBytes(file.size)}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                    {file.modified_at ? formatDate(file.modified_at) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right space-x-1">
                    {!file.is_dir && (
                      <>
                        <button type="button" onClick={() => handleDownload(file.path, file.name)}
                          className="inline-flex p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
                          title={t('files.download')}>
                          <Download className="w-4 h-4" />
                        </button>
                        <button type="button" onClick={() => handleDelete(file.path)}
                          className="inline-flex p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                          title={t('common.delete')}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </>
                    )}
                    {file.is_dir && (
                      <button type="button" onClick={() => handleDelete(file.path)}
                        className="inline-flex p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                        title={t('common.delete')}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
