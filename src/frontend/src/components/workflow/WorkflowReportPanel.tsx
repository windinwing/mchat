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
import { resolveUploadUrl } from '@/lib/mediaUrl'

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

// ── Structured data extraction (stocks / signals / gainers) ──────────────
interface StockRow { code: string; name: string; price?: number | null; changePct?: number | null; amount?: number | null; board?: string }
interface SignalRow { type: string; direction?: string; note?: string; value?: unknown }
interface StructuredBlock {
  title?: string
  stocks?: StockRow[]
  signals?: SignalRow[]
  topGainers?: StockRow[]
  topLosers?: StockRow[]
  boardAvgPct?: number | null
}

/** Scan node runs for skill outputs carrying structured lists and normalize
 *  them into renderable blocks. Covers stock-search (stocks/top_gainers) and
 *  stock-overseas / stock-quote (signals), plus any skill emitting `stocks`
 *  or `signals` on its result. */
function extractStructuredData(nodeRuns?: NodeRun[] | null): StructuredBlock[] {
  if (!nodeRuns?.length) return []
  const blocks: StructuredBlock[] = []
  for (const nr of nodeRuns) {
    const r = nr?.result as Record<string, unknown> | null | undefined
    if (!r || typeof r !== 'object') continue
    const block: StructuredBlock = {}
    if (nr.node_name) block.title = String(nr.node_name)

    // 成分股 / 股票列表
    const stocksRaw = (r.stocks ?? r.items ?? r.rows) as unknown
    if (Array.isArray(stocksRaw) && stocksRaw.length) {
      block.stocks = stocksRaw.slice(0, 50).map((s) => normalizeStock(s as Record<string, unknown>)).filter((s) => s.code || s.name)
    }
    // 涨跌幅居前
    if (Array.isArray(r.top_gainers)) {
      block.topGainers = (r.top_gainers as Record<string, unknown>[]).slice(0, 5).map(normalizeStock)
    }
    if (Array.isArray(r.top_losers)) {
      block.topLosers = (r.top_losers as Record<string, unknown>[]).slice(0, 5).map(normalizeStock)
    }
    // 板块平均涨跌幅
    if (typeof r.board_avg_pct === 'number') block.boardAvgPct = r.board_avg_pct

    // 技术信号（envelope.signals 或顶层 signals）
    const sigSrc = (r.signals ?? (r.envelope as Record<string, unknown> | undefined)?.signals) as unknown
    if (Array.isArray(sigSrc) && sigSrc.length) {
      block.signals = (sigSrc as Record<string, unknown>[]).slice(0, 30).map((s) => ({
        type: String(s.type ?? s.name ?? ''),
        direction: typeof s.direction === 'string' ? s.direction : undefined,
        note: typeof s.note === 'string' ? s.note : undefined,
        value: s.value,
      })).filter((s) => s.type)
    }

    if (block.stocks?.length || block.signals?.length || block.topGainers?.length || block.topLosers?.length || block.boardAvgPct != null) {
      blocks.push(block)
    }
  }
  return blocks
}

function normalizeStock(s: Record<string, unknown>): StockRow {
  return {
    code: String(s.code ?? s.symbol ?? s.f12 ?? ''),
    name: String(s.name ?? s.f14 ?? ''),
    price: numOrNull(s.price ?? s['最新价'] ?? s.currentPrice),
    changePct: numOrNull(s.change_pct ?? s.changePct ?? s.pct_chg),
    amount: numOrNull(s.amount ?? s['成交额']),
    board: typeof s.board === 'string' ? s.board : undefined,
  }
}
function numOrNull(v: unknown): number | null {
  const n = typeof v === 'string' ? parseFloat(v) : (v as number)
  return typeof n === 'number' && !Number.isNaN(n) ? n : null
}
function fmtNum(n: number | null | undefined): string {
  return n == null ? '—' : n.toFixed(2)
}
function fmtPct(n: number | null | undefined): string {
  return n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}
function fmtAmount(yuan: number | null | undefined): string {
  if (yuan == null) return '—'
  if (yuan >= 1e8) return `${(yuan / 1e8).toFixed(2)}亿`
  if (yuan >= 1e4) return `${(yuan / 1e4).toFixed(1)}万`
  return `${yuan.toFixed(0)}`
}
function pctColor(n: number | null | undefined): string {
  if (n == null) return 'text-gray-500 dark:text-gray-400'
  return n > 0 ? 'text-red-600 dark:text-red-400' : n < 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'
}
function directionBadge(d?: string): string {
  if (d === 'bull') return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
  if (d === 'bear') return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
}

function GainersLosersRow({ label, items }: { label: string; items: StockRow[] }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
      {items.map((s, i) => (
        <span key={s.code || i} className="inline-flex items-center gap-1">
          <span className="text-gray-900 dark:text-gray-100">{s.name}</span>
          <span className={pctColor(s.changePct)}>{fmtPct(s.changePct)}</span>
        </span>
      ))}
    </div>
  )
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
  // Structured data blocks (stocks lists, technical signals, gainers/losers).
  // Skills like stock-search / stock-overseas emit these on node.result; the
  // panel renders them as tables instead of just the summary string.
  const structuredBlocks = useMemo(() => extractStructuredData(nodeRuns), [nodeRuns])
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

  if (artifacts.length === 0 && images.length === 0 && !narrative && structuredBlocks.length === 0) return null

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

      {structuredBlocks.map((blk, i) => (
        <div key={i} className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-gray-900/50 p-3">
          {blk.title ? (
            <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">{blk.title}</p>
          ) : null}

          {/* 涨跌幅居前（top gainers / losers） */}
          {blk.topGainers?.length ? (
            <GainersLosersRow label={t('workflows.reportTopGainers', { defaultValue: '📈 涨幅居前' })} items={blk.topGainers} />
          ) : null}
          {blk.topLosers?.length ? (
            <GainersLosersRow label={t('workflows.reportTopLosers', { defaultValue: '📉 跌幅居前' })} items={blk.topLosers} />
          ) : null}

          {/* 板块强弱概览 */}
          {blk.boardAvgPct != null ? (
            <p className="text-xs text-gray-600 dark:text-gray-400">
              {t('workflows.reportBoardTrend', { defaultValue: '板块平均涨跌幅' })}：
              <span className={blk.boardAvgPct >= 0 ? 'text-red-600 dark:text-red-400 font-medium' : 'text-green-600 dark:text-green-400 font-medium'}>
                {blk.boardAvgPct >= 0 ? '+' : ''}{blk.boardAvgPct.toFixed(2)}%
              </span>
            </p>
          ) : null}

          {/* 成分股 / 股票列表表格 */}
          {blk.stocks?.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left border-b border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                    <th className="py-1.5 pr-3">{t('workflows.colCode', { defaultValue: '代码' })}</th>
                    <th className="py-1.5 pr-3">{t('workflows.colName', { defaultValue: '名称' })}</th>
                    <th className="py-1.5 pr-3">{t('workflows.colPrice', { defaultValue: '最新价' })}</th>
                    <th className="py-1.5 pr-3">{t('workflows.colChangePct', { defaultValue: '涨跌幅' })}</th>
                    <th className="py-1.5 pr-3">{t('workflows.colAmount', { defaultValue: '成交额' })}</th>
                    <th className="py-1.5 pr-3">{t('workflows.colBoard', { defaultValue: '板块' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {blk.stocks.map((s, idx) => (
                    <tr key={s.code || idx} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-1.5 pr-3 font-mono text-gray-700 dark:text-gray-300">{s.code}</td>
                      <td className="py-1.5 pr-3 text-gray-900 dark:text-gray-100">{s.name}</td>
                      <td className="py-1.5 pr-3 text-gray-700 dark:text-gray-300">{fmtNum(s.price)}</td>
                      <td className={'py-1.5 pr-3 font-medium ' + pctColor(s.changePct)}>{fmtPct(s.changePct)}</td>
                      <td className="py-1.5 pr-3 text-gray-500 dark:text-gray-400">{fmtAmount(s.amount)}</td>
                      <td className="py-1.5 pr-3 text-gray-500 dark:text-gray-400">{s.board || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {/* 技术信号列表 */}
          {blk.signals?.length ? (
            <div className="space-y-1">
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300">{t('workflows.reportSignals', { defaultValue: '技术信号' })}</p>
              {blk.signals.map((sig, idx) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  <span className={'px-1.5 py-0.5 rounded font-medium ' + directionBadge(sig.direction)}>
                    {sig.direction === 'bull' ? '多' : sig.direction === 'bear' ? '空' : '中'}
                  </span>
                  <span className="text-gray-700 dark:text-gray-300">{sig.type}{sig.note ? ` — ${sig.note}` : ''}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ))}

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
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    urlTransform={(url) => resolveUploadUrl(url) || url}
                  >
                    {mdText}
                  </ReactMarkdown>
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
