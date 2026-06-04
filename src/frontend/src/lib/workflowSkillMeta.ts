export type WorkflowSkillCategory = 'search' | 'analyze' | 'visualize' | 'export' | 'other'

export type WorkflowRole = WorkflowSkillCategory | 'control'

export interface WorkflowSkillOption {
  id: string
  name: string
  description?: string | null
  config?: Record<string, unknown> | null
}

export type GraphNodeType = 'start' | 'skill' | 'condition' | 'end' | 'approval' | 'merge'

export const NODE_COLORS: Record<GraphNodeType, string> = {
  start: '#22c55e',
  skill: '#3b82f6',
  condition: '#f59e0b',
  end: '#a855f7',
  approval: '#ef4444',
  merge: '#6366f1',
}

export const CONTROL_NODE_TYPES: GraphNodeType[] = ['start', 'condition', 'approval', 'merge', 'end']

export const CATEGORY_ORDER: WorkflowSkillCategory[] = [
  'search',
  'analyze',
  'visualize',
  'export',
  'other',
]

export function inferSkillCategory(skill: WorkflowSkillOption): WorkflowSkillCategory {
  const role = String((skill.config as any)?.workflow_role || '').trim().toLowerCase()
  if (role === 'search' || role === 'analyze' || role === 'visualize' || role === 'export') {
    return role
  }
  const n = skill.name.toLowerCase()
  if (n.includes('search') || n.includes('检索') || n.includes('query')) return 'search'
  if (n.includes('chart') || n.includes('graph') || n.includes('图表') || n.includes('可视化')) {
    return 'visualize'
  }
  if (n.includes('export') || n.includes('report') || n.includes('导出') || n.includes('word') || n.includes('excel')) {
    return 'export'
  }
  if (n.includes('analysis') || n.includes('analyze') || n.includes('分析') || n.includes('summary') || n.includes('总结')) {
    return 'analyze'
  }
  return 'other'
}

export function groupSkillsByCategory(skills: WorkflowSkillOption[]) {
  const groups: Record<WorkflowSkillCategory, WorkflowSkillOption[]> = {
    search: [],
    analyze: [],
    visualize: [],
    export: [],
    other: [],
  }
  for (const skill of skills) {
    groups[inferSkillCategory(skill)].push(skill)
  }
  return groups
}

export function defaultPayloadForSkill(skill: WorkflowSkillOption, upstreamNodeIds: string[]): Record<string, unknown> {
  const category = inferSkillCategory(skill)
  const isPatentSearch = skill.name === 'patent-search'
  const isPatentReport = skill.name === 'patent-report'
  switch (category) {
    case 'search':
      if (isPatentSearch) {
        return {
          command: 'search',
          query: '${input.keyword}',
          industry: '${input.industry}',
        }
      }
      return {
        command: 'search',
        query: '${input.keyword}',
        industry: '${input.industry}',
      }
    case 'analyze':
      if (isPatentSearch) {
        return {
          command: 'analysis',
          query: '${input.keyword}',
          dimension: 'applicant',
        }
      }
      return {
        patent_ids: upstreamNodeIds.includes('search')
          ? '${nodes.search.patent_ids}'
          : '${nodes.search.result}',
        dimension: skill.name.includes('year') || skill.name.includes('年份') ? 'year' : 'applicant',
      }
    case 'visualize':
      if (isPatentReport) {
        return {
          command: 'chart',
          sections: '${nodes.merge.sections}',
          title: '${input.report_title}',
        }
      }
      return {
        sections: '${nodes.merge.sections}',
        title: '${input.report_title}',
      }
    case 'export':
      if (isPatentReport) {
        return {
          command: 'all',
          sections: '${nodes.merge.sections}',
          charts: '${nodes.chart.charts}',
          title: '${input.report_title}',
          filename: '${input.report_title}',
        }
      }
      if (isPatentSearch) {
        return {
          command: 'export_analysis',
          query: '${input.keyword}',
          filename: '${input.keyword}-patent-report',
        }
      }
      return {
        sections: '${nodes.merge.sections}',
        charts: '${nodes.chart.charts}',
        filename: '${input.keyword}-report',
      }
    default:
      return {}
  }
}

export function collectUpstreamNodeIds(
  nodeId: string,
  edges: Array<{ source: string; target: string }>,
): string[] {
  const incoming = edges.filter((e) => e.target === nodeId).map((e) => e.source)
  const seen = new Set<string>()
  const queue = [...incoming]
  const result: string[] = []
  while (queue.length) {
    const id = queue.shift()!
    if (seen.has(id)) continue
    seen.add(id)
    result.push(id)
    for (const e of edges) {
      if (e.target === id) queue.push(e.source)
    }
  }
  return result
}

export interface InputFieldDef {
  key: string
  label: string
  placeholder?: string
  required?: boolean
  type?: 'text' | 'number'
}

/** True when graph includes patent-report chart/export nodes. */
export function graphNeedsReportTitle(
  nodes: Array<{ type: string; config?: Record<string, unknown> | null }>,
  skills?: Array<{ id: string; name: string }>,
): boolean {
  for (const node of nodes) {
    if (node.type !== 'skill') continue
    const cfg = node.config as {
      skill_name?: string
      skill_id?: string
      payload_template?: Record<string, unknown>
    } | undefined
    const skillName = String(cfg?.skill_name || '').toLowerCase()
    if (skillName === 'patent-report' || skillName.includes('patent-report')) return true
    if (skills?.length && cfg?.skill_id) {
      const sk = skills.find((s) => s.id === cfg.skill_id)
      if (sk?.name === 'patent-report') return true
    }
    const pt = cfg?.payload_template || {}
    const cmd = String(pt.command || '').toLowerCase()
    if (['chart', 'excel', 'word', 'ppt', 'all'].includes(cmd) && ('sections' in pt || 'title' in pt)) {
      return true
    }
    const blob = JSON.stringify(pt)
    if (blob.includes('report_title') || blob.includes('专利分析')) return true
  }
  return false
}

export function buildDefaultReportTitle(
  keyword: string,
  options?: { industry?: string; locale?: string },
): string {
  const kw = keyword.trim()
  if (!kw) return ''
  const industry = options?.industry?.trim()
  const en = options?.locale?.startsWith('en')
  if (en) {
    return industry ? `${kw} (${industry}) Patent Analysis Report` : `${kw} Patent Analysis Report`
  }
  return industry ? `${kw}（${industry}）专利分析报告` : `${kw} 专利分析报告`
}

export function extractStartInputFields(
  nodes: Array<{ type: string; config?: Record<string, unknown> | null }>,
  options?: { t?: (key: string) => string; skills?: Array<{ id: string; name: string }> },
): InputFieldDef[] {
  const start = nodes.find((n) => n.type === 'start')
  const fields = (start?.config as any)?.input_fields
  let result: InputFieldDef[]
  if (!Array.isArray(fields)) {
    result = [
      { key: 'keyword', label: 'keyword', placeholder: '', required: true },
    ]
  } else {
    result = fields.map((f: any) => ({
      key: String(f.key || ''),
      label: String(f.label || f.key || ''),
      placeholder: f.placeholder ? String(f.placeholder) : undefined,
      required: Boolean(f.required),
      type: (f.type === 'number' ? 'number' : 'text') as 'number' | 'text',
    })).filter((f) => f.key)
  }

  if (graphNeedsReportTitle(nodes, options?.skills)) {
    const keys = new Set(result.map((f) => f.key))
    if (!keys.has('report_title')) {
      const tr = (key: string, fallback: string) => (options?.t ? options.t(key) : fallback)
      const field: InputFieldDef = {
        key: 'report_title',
        label: tr('workflows.inputReportTitle', '报告名称'),
        placeholder: tr('workflows.inputReportTitlePh', '根据检索词自动生成，可修改'),
        required: false,
        type: 'text',
      }
      const keywordIdx = result.findIndex((f) => f.key === 'keyword')
      if (keywordIdx >= 0) {
        result.splice(keywordIdx + 1, 0, field)
      } else {
        result.unshift(field)
      }
    }
  }
  return result
}

export const PRESET_VAR_GROUPS = [
  { id: 'input', prefix: 'input' },
  { id: 'nodes', prefix: 'nodes' },
] as const
