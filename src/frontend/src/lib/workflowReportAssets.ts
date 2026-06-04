import { resolveUploadUrl } from '@/lib/mediaUrl'

export type ReportArtifactFormat = 'png' | 'xlsx' | 'docx' | 'pptx' | 'other'

export interface WorkflowReportArtifact {
  format: ReportArtifactFormat
  filename: string
  url: string
  label?: string
}

const FORMAT_LABELS: Record<ReportArtifactFormat, string> = {
  png: 'PNG',
  xlsx: 'Excel',
  docx: 'Word',
  pptx: 'PPT',
  other: 'File',
}

export function reportFormatLabel(format: ReportArtifactFormat): string {
  return FORMAT_LABELS[format] || format
}

function inferFormat(filename: string, fmt?: string): ReportArtifactFormat {
  const f = (fmt || filename || '').toLowerCase()
  if (f.includes('png') || f.endsWith('.png')) return 'png'
  if (f.includes('xlsx') || f.endsWith('.xlsx')) return 'xlsx'
  if (f.includes('docx') || f.endsWith('.docx')) return 'docx'
  if (f.includes('pptx') || f.endsWith('.pptx')) return 'pptx'
  return 'other'
}

function absoluteUploadUrl(url: string): string {
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}${url.startsWith('/') ? url : `/${url}`}`
}

export function officeOnlinePreviewUrl(fileUrl: string): string | null {
  const abs = absoluteUploadUrl(fileUrl)
  if (!abs.startsWith('http')) return null
  const ext = abs.split('?')[0].split('.').pop()?.toLowerCase()
  if (!ext || !['xlsx', 'xls', 'docx', 'doc', 'pptx', 'ppt'].includes(ext)) return null
  return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(abs)}`
}

function addArtifact(
  items: WorkflowReportArtifact[],
  seen: Set<string>,
  raw: { url?: string; filename?: string; format?: string; name?: string }
) {
  const resolved = resolveUploadUrl(raw.url)
  if (!resolved || seen.has(resolved)) return
  seen.add(resolved)
  const filename = raw.filename || raw.name || resolved.split('/').pop()?.split('?')[0] || 'file'
  const format = inferFormat(filename, raw.format)
  items.push({ format, filename, url: resolved, label: raw.name })
}

function parseMarkdownUploadLinks(text: string): Array<{ url: string; filename: string }> {
  const out: Array<{ url: string; filename: string }> = []
  const re = /\[([^\]]*)\]\((\/uploads\/[^)]+)\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    out.push({ url: m[2], filename: m[1] || m[2].split('/').pop() || 'file' })
  }
  return out
}

function collectFromResult(
  result: unknown,
  items: WorkflowReportArtifact[],
  seen: Set<string>
) {
  if (!result || typeof result !== 'object') return
  const r = result as Record<string, unknown>
  for (const key of ['report_files', 'files']) {
    const list = r[key]
    if (Array.isArray(list)) {
      for (const f of list) {
        if (f && typeof f === 'object') addArtifact(items, seen, f as Record<string, string>)
      }
    }
  }
  for (const key of ['report_charts', 'charts']) {
    const list = r[key]
    if (Array.isArray(list)) {
      for (const c of list) {
        if (c && typeof c === 'object') {
          const row = c as Record<string, string>
          addArtifact(items, seen, {
            url: row.url,
            filename: row.filename,
            format: 'png',
            name: row.name,
          })
        }
      }
    }
  }
  const msg = r.message
  if (typeof msg === 'string') {
    for (const link of parseMarkdownUploadLinks(msg)) {
      addArtifact(items, seen, { url: link.url, filename: link.filename })
    }
  }
}

type NodeRun = {
  node_id?: string
  node_name?: string
  node_type?: string
  result?: unknown
}

export interface WorkflowReportNarrative {
  summary: string
  interpretation: string
}

function narrativeFromResult(result: unknown): WorkflowReportNarrative | null {
  if (!result || typeof result !== 'object') return null
  const r = result as Record<string, unknown>
  const summary = typeof r.summary === 'string' ? r.summary.trim() : ''
  const interpretation =
    typeof r.interpretation === 'string' ? r.interpretation.trim() : ''
  if (!summary && !interpretation) return null
  return { summary, interpretation }
}

export function extractWorkflowReportNarrative(
  nodeRuns?: NodeRun[] | null,
  outputPayload?: Record<string, unknown> | null
): WorkflowReportNarrative | null {
  const preferIds = new Set(['export', 'chart', '报告导出', '图表生成'])
  const sorted = [...(nodeRuns || [])].sort((a, b) => {
    const aP = preferIds.has(a.node_id || '') || preferIds.has(a.node_name || '') ? 0 : 1
    const bP = preferIds.has(b.node_id || '') || preferIds.has(b.node_name || '') ? 0 : 1
    return aP - bP
  })
  for (const node of sorted) {
    const found = narrativeFromResult(node.result)
    if (found) return found
  }
  const outputs = outputPayload?.outputs
  if (outputs && typeof outputs === 'object') {
    for (const val of Object.values(outputs as Record<string, unknown>)) {
      const found = narrativeFromResult(val)
      if (found) return found
    }
  }
  return null
}

export function extractWorkflowReportArtifacts(
  nodeRuns?: NodeRun[] | null,
  outputPayload?: Record<string, unknown> | null
): WorkflowReportArtifact[] {
  const items: WorkflowReportArtifact[] = []
  const seen = new Set<string>()

  const preferIds = new Set(['export', 'chart', '报告导出', '图表生成'])
  const sorted = [...(nodeRuns || [])].sort((a, b) => {
    const aP = preferIds.has(a.node_id || '') || preferIds.has(a.node_name || '') ? 0 : 1
    const bP = preferIds.has(b.node_id || '') || preferIds.has(b.node_name || '') ? 0 : 1
    return aP - bP
  })

  for (const node of sorted) {
    collectFromResult(node.result, items, seen)
  }

  const outputs = outputPayload?.outputs
  if (outputs && typeof outputs === 'object') {
    for (const val of Object.values(outputs as Record<string, unknown>)) {
      if (val && typeof val === 'object') {
        const row = val as Record<string, unknown>
        collectFromResult(row, items, seen)
      }
    }
  }

  const order: ReportArtifactFormat[] = ['xlsx', 'docx', 'pptx', 'png', 'other']
  return items
    .filter((a) => a.format !== 'png')
    .sort((a, b) => order.indexOf(a.format) - order.indexOf(b.format))
}

/** Chart PNGs for inline preview only (not listed in download buttons). */
export function extractWorkflowReportCharts(
  nodeRuns?: NodeRun[] | null,
  outputPayload?: Record<string, unknown> | null
): WorkflowReportArtifact[] {
  const items: WorkflowReportArtifact[] = []
  const seen = new Set<string>()
  const preferIds = new Set(['export', 'chart', '报告导出', '图表生成'])
  const sorted = [...(nodeRuns || [])].sort((a, b) => {
    const aP = preferIds.has(a.node_id || '') || preferIds.has(a.node_name || '') ? 0 : 1
    const bP = preferIds.has(b.node_id || '') || preferIds.has(b.node_name || '') ? 0 : 1
    return aP - bP
  })
  for (const node of sorted) {
    if (!node.result || typeof node.result !== 'object') continue
    const r = node.result as Record<string, unknown>
    for (const key of ['report_charts', 'charts']) {
      const list = r[key]
      if (Array.isArray(list)) {
        for (const c of list) {
          if (c && typeof c === 'object') {
            const row = c as Record<string, string>
            addArtifact(items, seen, {
              url: row.url,
              filename: row.filename,
              format: 'png',
              name: row.name,
            })
          }
        }
      }
    }
  }
  return items
}

export function absoluteArtifactUrl(url: string): string {
  return absoluteUploadUrl(url)
}

export function downloadArtifact(artifact: WorkflowReportArtifact) {
  window.open(absoluteArtifactUrl(artifact.url), '_blank', 'noopener,noreferrer')
}
