import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { File, FolderOpen, Save, X, Code2, ArrowLeft, Upload, Loader2, Eye, Columns2, Pencil, Maximize2, Minimize2, Image, ChevronDown, ChevronUp } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { MarkdownToolbar } from './MarkdownToolbar'

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
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [resourcePickerOpen, setResourcePickerOpen] = useState(false)
  const [frontmatterExpanded, setFrontmatterExpanded] = useState(false)
  const [workspaceFiles, setWorkspaceFiles] = useState<Array<{ path: string; name: string; size: number; is_dir: boolean }>>([])
  const [workspaceFilesLoading, setWorkspaceFilesLoading] = useState(false)
  const [workspaceSubdir, setWorkspaceSubdir] = useState('user')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

  const loadWorkspaceFiles = async (subdir = 'user') => {
    setWorkspaceFilesLoading(true)
    try {
      const res = await api.get<{ items: Array<{ path: string; name: string; size: number; is_dir: boolean }>; subdir: string }>('/workspace/files', { subdir })
      setWorkspaceFiles((res.items || []).filter((f) => !f.is_dir))
      setWorkspaceSubdir(res.subdir || subdir)
    } catch (err: any) {
      toast(t('files.loadFailed'), { type: 'error' })
    } finally {
      setWorkspaceFilesLoading(false)
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
    setIsFullscreen(false)
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

  const fileExt = fileContent?.name.split('.').pop()?.toLowerCase() || ''
  const isMarkdown = fileExt === 'md'
  const isPython = fileExt === 'py'
  const editorHeight = isFullscreen ? 'calc(100vh - 220px)' : '24rem'

  // Extract frontmatter for pretty rendering
  const frontmatterMatch = editingContent.match(/^---\n([\s\S]*?)\n---\n?/)
  const hasFrontmatter = frontmatterMatch !== null
  const frontmatter = frontmatterMatch ? frontmatterMatch[0] : ''
  const bodyContent = hasFrontmatter ? editingContent.slice(frontmatter.length) : editingContent

  const isImage = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase() || ''
    return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)
  }

  const insertResource = (resourcePath: string, resourceName: string, subdir: string) => {
    const textarea = textareaRef.current
    if (!textarea) return

    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const before = editingContent.slice(0, start)
    const after = editingContent.slice(end)

    const url = `/api/workspace/files/download?subdir=${encodeURIComponent(subdir)}&path=${encodeURIComponent(resourcePath)}`
    const insertText = isImage(resourceName)
      ? `![${resourceName}](${url})`
      : `[${resourceName}](${url})`

    setEditingContent(before + insertText + after)
    setResourcePickerOpen(false)

    setTimeout(() => {
      const newPos = start + insertText.length
      textarea.focus()
      textarea.setSelectionRange(newPos, newPos)
    }, 0)
  }

  return (
    <Dialog open={open} onClose={onClose} title={`${skillName} — ${t('skills.files')}`} size={isFullscreen ? 'full' : 'lg'}>
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
          <div className="flex items-center justify-between gap-3">
            <Button variant="secondary" size="sm" onClick={backToList} leftIcon={<ArrowLeft className="w-4 h-4" />}>
              {t('skills.backToFiles')}
            </Button>
            <span className="text-sm text-gray-500 dark:text-gray-400 truncate flex-1 text-right">{selectedFile}</span>
            <button
              type="button"
              onClick={() => setIsFullscreen((v) => !v)}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700 transition-colors"
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
          {isEditable(fileContent?.name || '') ? (
            <>
              <div className="flex items-center gap-1 flex-wrap">
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

              </div>
              <div className={previewMode === 'split' ? 'grid grid-cols-2 gap-3' : ''}>
                {previewMode !== 'preview' && (
                  <div className="space-y-1">
                    {isMarkdown && writable && (
                      <MarkdownToolbar
                        textareaRef={textareaRef}
                        value={editingContent}
                        onChange={setEditingContent}
                        onOpenResourcePicker={() => {
                          loadWorkspaceFiles('user')
                          setResourcePickerOpen(true)
                        }}
                        hasResources={true}
                      />
                    )}
                    <textarea
                      ref={textareaRef}
                      className="w-full font-mono text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-3 resize-none"
                      style={{ height: editorHeight }}
                      value={editingContent}
                      onChange={(e) => setEditingContent(e.target.value)}
                      readOnly={!writable}
                      spellCheck={false}
                    />
                  </div>
                )}
                {(previewMode === 'preview' || previewMode === 'split') && (
                  <div
                    className="overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-900 p-4 max-w-none"
                    style={{ height: editorHeight }}
                  >
                    {isMarkdown ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        {hasFrontmatter && (
                          <div className="mb-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-hidden">
                            <button
                              type="button"
                              onClick={() => setFrontmatterExpanded((v) => !v)}
                              className="w-full flex items-center justify-between px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                            >
                              <span>SKILL.md Frontmatter</span>
                              {frontmatterExpanded ? (
                                <ChevronUp className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5" />
                              )}
                            </button>
                            <div
                              className="transition-[max-height] duration-300 ease-in-out overflow-hidden"
                              style={{ maxHeight: frontmatterExpanded ? '500px' : '0px' }}
                            >
                              <SyntaxHighlighter language="yaml" style={oneDark} className="!m-0 !bg-transparent !p-3 text-xs">
                                {frontmatter.replace(/^---\n/, '').replace(/\n---\n?$/, '')}
                              </SyntaxHighlighter>
                            </div>
                          </div>
                        )}
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {bodyContent || ' '}
                        </ReactMarkdown>
                      </div>
                    ) : isPython ? (
                      <SyntaxHighlighter language="python" style={oneDark} className="!m-0 !bg-transparent !p-0 text-sm">
                        {editingContent || ''}
                      </SyntaxHighlighter>
                    ) : (
                      <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                        {editingContent}
                      </pre>
                    )}
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

          {/* Resource Picker Dialog */}
          <Dialog
            open={resourcePickerOpen}
            onClose={() => setResourcePickerOpen(false)}
            title={t('skills.insertResource', 'Insert resource')}
            size="md"
          >
            <div className="space-y-3">
              {workspaceFilesLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner size="sm" />
                </div>
              ) : workspaceFiles.length === 0 ? (
                <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                  {t('files.empty', 'No files')}
                </div>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 max-h-[60vh] overflow-y-auto p-1">
                  {workspaceFiles.map((f) => (
                    <button
                      key={f.path}
                      type="button"
                      onClick={() => insertResource(f.path, f.name, workspaceSubdir)}
                      className="flex flex-col items-center gap-2 p-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:border-primary-400 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors text-center"
                      title={f.path}
                    >
                      <div className="w-12 h-12 rounded-lg bg-white dark:bg-gray-700 border border-gray-100 dark:border-gray-600 flex items-center justify-center">
                        {isImage(f.name) ? (
                          <Image className="w-6 h-6 text-primary-500" />
                        ) : (
                          <File className="w-6 h-6 text-gray-400" />
                        )}
                      </div>
                      <span className="text-xs text-gray-700 dark:text-gray-200 truncate w-full">{f.name}</span>
                      <span className="text-[10px] text-gray-400">{formatSize(f.size)}</span>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex justify-end">
                <Button variant="secondary" size="sm" onClick={() => setResourcePickerOpen(false)}>
                  {t('common.cancel')}
                </Button>
              </div>
            </div>
          </Dialog>
        </div>
      )}
    </Dialog>
  )
}
