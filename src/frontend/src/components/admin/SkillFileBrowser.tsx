import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { File, FolderOpen, Save, X, Code2, ArrowLeft, Upload, Loader2, Eye, Columns2, Pencil } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

interface SkillFile {
  path: string
  name: string
  size: number
  updated_at: number
}

interface SkillFileContent {
  path: string
  name: string
  content: string
}

interface Props {
  skillId: string
  skillName: string
  open: boolean
  writable?: boolean
  onClose: () => void
}

export function SkillFileBrowser({
  skillId,
  skillName,
  open,
  writable = true,
  onClose,
}: Props) {
  const { t } = useTranslation()
  const [files, setFiles] = useState<SkillFile[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<SkillFileContent | null>(null)
  const [editingContent, setEditingContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [previewMode, setPreviewMode] = useState<'edit' | 'preview' | 'split'>('edit')
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open && skillId) {
      loadFiles()
    }
  }, [open, skillId])

  const loadFiles = async () => {
    setLoading(true)
    try {
      const data = await api.get<SkillFile[]>(`/skills/${skillId}/files`)
      setFiles(data)
    } catch (err: any) {
      toast(t('skills.toastLoadFilesFailed'), { type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await api.upload(`/skills/${skillId}/files`, formData)
      toast(t('skills.toastFileUploaded'), { type: 'success' })
      await loadFiles()
    } catch (err: any) {
      toast(t('skills.toastFileUploadFailed'), { type: 'error' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const openFile = async (filePath: string) => {
    try {
      const data = await api.get<SkillFileContent>(`/skills/${skillId}/files/${encodeURIComponent(filePath)}`)
      setSelectedFile(filePath)
      setFileContent(data)
      setEditingContent(data.content)
    } catch (err: any) {
      toast(t('skills.toastReadFileFailed'), { type: 'error' })
    }
  }

  const saveFile = async () => {
    if (!selectedFile) return
    setSaving(true)
    try {
      await api.put(`/skills/${skillId}/files/${encodeURIComponent(selectedFile)}`, {
        content: editingContent,
      })
      toast(t('skills.toastFileSaved'), { type: 'success' })
    } catch (err: any) {
      toast(t('skills.toastSaveFileFailed'), { type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const backToList = () => {
    setSelectedFile(null)
    setFileContent(null)
    setEditingContent('')
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const isEditable = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase()
    return ['md', 'txt', 'py', 'js', 'ts', 'json', 'yaml', 'yml', 'xml', 'html', 'css', 'sh', 'cfg', 'ini', 'toml', 'env'].includes(ext || '')
  }

  return (
    <Dialog open={open} onClose={onClose} title={`${skillName} — ${t('skills.files')}`} size="lg">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleUpload}
      />
      {!selectedFile ? (
        <div className="space-y-2">
          {writable && (
            <div className="flex items-center justify-end">
              <Button
                size="sm"
                leftIcon={uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                onClick={() => fileInputRef.current?.click()}
                isLoading={uploading}
              >
                {t('skills.uploadFile')}
              </Button>
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner size="sm" />
            </div>
          ) : files.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
              {t('skills.noFiles')}
            </p>
          ) : (
            <div className="max-h-96 overflow-y-auto space-y-0.5">
              {files.map((f) => (
                <button
                  key={f.path}
                  type="button"
                  onClick={() => openFile(f.path)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  <File className="w-4 h-4 text-gray-400 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-700 dark:text-gray-300 truncate">{f.path}</p>
                    <p className="text-xs text-gray-400">{formatSize(f.size)}</p>
                  </div>
                  {isEditable(f.name) && (
                    <Code2 className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Button variant="secondary" size="sm" onClick={backToList} leftIcon={<ArrowLeft className="w-4 h-4" />}>
              {t('skills.backToFiles')}
            </Button>
            <span className="text-sm text-gray-500 dark:text-gray-400 truncate">{selectedFile}</span>
          </div>
          {isEditable(fileContent?.name || '') ? (
            <>
              <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 w-fit">
                <button
                  type="button"
                  onClick={() => setPreviewMode('edit')}
                  className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                    previewMode === 'edit'
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Pencil className="w-3.5 h-3.5 inline mr-1" />
                  {t('skills.edit')}
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode('preview')}
                  className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                    previewMode === 'preview'
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Eye className="w-3.5 h-3.5 inline mr-1" />
                  {t('skills.preview')}
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode('split')}
                  className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                    previewMode === 'split'
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Columns2 className="w-3.5 h-3.5 inline mr-1" />
                  {t('skills.split')}
                </button>
              </div>
              <div className={previewMode === 'split' ? 'grid grid-cols-2 gap-3' : ''}>
                {previewMode !== 'preview' && (
                  <textarea
                    className="w-full h-96 font-mono text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-3 resize-none"
                    value={editingContent}
                    onChange={(e) => setEditingContent(e.target.value)}
                    readOnly={!writable}
                    spellCheck={false}
                  />
                )}
                {(previewMode === 'preview' || previewMode === 'split') && (
                  <div className="h-96 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-900 p-4 prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {editingContent || ' '}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="sm" onClick={backToList} leftIcon={<X className="w-4 h-4" />}>
                  {writable ? t('common.cancel') : t('common.close')}
                </Button>
                {writable && (
                  <Button size="sm" onClick={saveFile} isLoading={saving} leftIcon={<Save className="w-4 h-4" />}>
                    {t('common.save')}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <pre className="max-h-96 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 p-4 text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {fileContent?.content}
            </pre>
          )}
        </div>
      )}
    </Dialog>
  )
}
