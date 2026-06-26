import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  FileCode2,
  Image as ImageIcon,
  Maximize2,
  Presentation,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import {
  absoluteArtifactUrl,
  downloadArtifact,
  extractWorkflowReportArtifacts,
  extractWorkflowReportCharts,
  extractWorkflowReportNarrative,
  officeOnlinePreviewUrl,
  reportFormatLabel,
  type ReportArtifactFormat,
  type WorkflowReportArtifact,
} from '@/lib/workflowReportAssets'

type NodeRun = {
  node_id?: string
  node_name?: string
  node_type?: string
  result?: unknown
}

const FORMAT_ICONS: Record<ReportArtifactFormat, React.ReactNode> = {
  png: <ImageIcon className="w-4 h-4" />,
  xlsx: <FileSpreadsheet className="w-4 h-4" />,
  docx: <FileText className="w-4 h-4" />,
  pptx: <Presentation className="w-4 h-4" />,
  md: <FileCode2 className="w-4 h-4" />,
  other: <FileText className="w-4 h-4" />,
}

interface Props {
  nodeRuns?: NodeRun[] | null
  outputPayload?: Record<string, unknown> | null
}

export function WorkflowReportPanel({ nodeRuns, outputPayload }: Props) {
  const { t } = useTranslation()
  const artifacts = useMemo(
    () => extractWorkflowReportArtifacts(nodeRuns, outputPayload),
    [nodeRuns, outputPayload]
  )
  const images = useMemo(
    () => extractWorkflowReportCharts(nodeRuns, outputPayload),
    [nodeRuns, outputPayload]
  )
  const narrative = useMemo(
    () => extractWorkflowReportNarrative(nodeRuns, outputPayload),
    [nodeRuns, outputPayload]
  )
  const officeFiles = artifacts

  const [previewOffice, setPreviewOffice] = useState<WorkflowReportArtifact | null>(() => {
    const first = officeFiles.find((f) => officeOnlinePreviewUrl(f.url))
    return first || officeFiles[0] || null
  })

  // Markdown 全屏预览
  const [mdPreview, setMdPreview] = useState<WorkflowReportArtifact | null>(null)
  const [mdText, setMdText] = useState('')
  const [mdLoading, setMdLoading] = useState(false)

  const mdFiles = useMemo(() => officeFiles.filter((f) => f.format === 'md'), [officeFiles])

  const openMdPreview = async (file: WorkflowReportArtifact) => {
    setMdPreview(file)
    setMdText('')
    setMdLoading(true)
    try {
      const res = await fetch(absoluteArtifactUrl(file.url))
      const text = await res.text()
      setMdText(text)
    } catch {
      setMdText(t('workflows.reportMdLoadError', { defaultValue: '加载失败' }))
    } finally {
      setMdLoading(false)
    }
  }

  if (artifacts.length === 0 && images.length === 0 && !narrative) return null

  const officeEmbed = previewOffice ? officeOnlinePreviewUrl(previewOffice.url) : null

  return (
    <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-950/30 p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {t('workflows.reportPanelTitle')}
        </h3>
        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
          {t('workflows.reportPanelHint')}
        </p>
      </div>

      {narrative ? (
        <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-gray-900/50 p-3">
          {narrative.summary ? (
            <div>
              <p className="text-xs font-semibold text-gray-800 dark:text-gray-200 mb-1">
                {t('workflows.reportSummary')}
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                {narrative.summary}
              </p>
            </div>
          ) : null}
          {narrative.interpretation ? (
            <div>
              <p className="text-xs font-semibold text-gray-800 dark:text-gray-200 mb-1">
                {t('workflows.reportInterpretation')}
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                {narrative.interpretation}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      {images.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
            {t('workflows.reportChartsPreview')}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {images.map((img) => (
              <a
                key={img.url}
                href={absoluteArtifactUrl(img.url)}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden hover:ring-2 hover:ring-blue-400 transition-shadow"
              >
                <img
                  src={absoluteArtifactUrl(img.url)}
                  alt={img.label || img.filename}
                  className="w-full h-auto max-h-64 object-contain bg-gray-50 dark:bg-gray-950"
                />
                <p className="text-xs px-2 py-1.5 text-gray-600 dark:text-gray-400 truncate">
                  {img.label || img.filename}
                </p>
              </a>
            ))}
          </div>
        </div>
      ) : null}

      {officeFiles.length > 0 ? (
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
          {t('workflows.reportDownloads')}
        </p>
        <div className="space-y-2">
          {officeFiles.map((file) => (
            <div
              key={file.url}
              className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
            >
              <span className="shrink-0 text-gray-400 dark:text-gray-500">{FORMAT_ICONS[file.format]}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-gray-800 dark:text-gray-200 truncate">{file.filename}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{reportFormatLabel(file.format)}</p>
              </div>
              {file.format === 'md' ? (
                <Button
                  size="sm"
                  variant="primary"
                  leftIcon={<Maximize2 className="w-4 h-4" />}
                  onClick={() => openMdPreview(file)}
                >
                  {t('workflows.reportPreview', { defaultValue: '预览' })}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Download className="w-4 h-4" />}
                onClick={() => downloadArtifact(file)}
              >
                {t('common.download', { defaultValue: '下载' })}
              </Button>
            </div>
          ))}
        </div>
      </div>
      ) : null}

      {officeFiles.length > 0 ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300 shrink-0">
              {t('workflows.reportOfficePreview')}
            </p>
            {officeFiles.map((file) => (
              <button
                key={file.url}
                type="button"
                onClick={() => setPreviewOffice(file)}
                className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                  previewOffice?.url === file.url
                    ? 'border-blue-500 bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200'
                    : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                {reportFormatLabel(file.format)}
              </button>
            ))}
            {previewOffice ? (
              <a
                href={absoluteArtifactUrl(previewOffice.url)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline ml-auto"
              >
                <ExternalLink className="w-3 h-3" />
                {t('workflows.reportOpenNewTab')}
              </a>
            ) : null}
          </div>
          {officeEmbed ? (
            <iframe
              title={previewOffice?.filename || 'report-preview'}
              src={officeEmbed}
              className="w-full h-[min(520px,70vh)] rounded-lg border border-gray-200 dark:border-gray-700 bg-white"
            />
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-4">
              {t('workflows.reportOfficePreviewFallback')}
            </p>
          )}
        </div>
      ) : null}

      {/* Markdown 全屏预览 */}
      <Dialog
        open={mdPreview !== null}
        onClose={() => setMdPreview(null)}
        title={mdPreview?.label || mdPreview?.filename || 'Markdown'}
        size="full"
      >
        <div className="flex items-center justify-between gap-2 pb-3 border-b border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{mdPreview?.filename}</p>
          {mdPreview ? (
            <a
              href={absoluteArtifactUrl(mdPreview.url)}
              download={mdPreview.filename}
              className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline shrink-0"
            >
              <Download className="w-3 h-3" />
              {t('workflows.reportDownload', { defaultValue: '下载' })}
            </a>
          ) : null}
        </div>
        <div className="mt-4 overflow-auto max-h-[calc(95vh-8rem)]">
          {mdLoading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('common.loading', { defaultValue: '加载中…' })}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{mdText}</ReactMarkdown>
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
