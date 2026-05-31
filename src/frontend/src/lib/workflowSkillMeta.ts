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
          title: '${input.keyword}',
        }
      }
      return {
        sections: '${nodes.merge.sections}',
        title: '${input.keyword}',
      }
    case 'export':
      if (isPatentReport) {
        return {
          command: 'all',
          sections: '${nodes.merge.sections}',
          charts: '${nodes.chart.charts}',
          title: '${input.keyword}',
          filename: '${input.keyword}-patent-report',
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
}

export function extractStartInputFields(
  nodes: Array<{ type: string; config?: Record<string, unknown> | null }>,
): InputFieldDef[] {
  const start = nodes.find((n) => n.type === 'start')
  const fields = (start?.config as any)?.input_fields
  if (!Array.isArray(fields)) {
    return [
      { key: 'keyword', label: 'keyword', placeholder: '', required: true },
    ]
  }
  return fields.map((f: any) => ({
    key: String(f.key || ''),
    label: String(f.label || f.key || ''),
    placeholder: f.placeholder ? String(f.placeholder) : undefined,
    required: Boolean(f.required),
  })).filter((f) => f.key)
}

export const PRESET_VAR_GROUPS = [
  { id: 'input', prefix: 'input' },
  { id: 'nodes', prefix: 'nodes' },
] as const
