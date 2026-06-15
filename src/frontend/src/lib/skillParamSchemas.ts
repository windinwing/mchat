/** Schema-driven skill node parameters for workflow graph editor. */

export interface SkillParamFieldDef {
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'json'
  placeholder?: string
  hint?: string
  options?: Array<{ value: string; label: string }>
  /** When omitted, field is always shown for the resolved schema group. */
  show?: (payload: Record<string, unknown>) => boolean
}

const PATENT_ANALYSIS_DIMENSIONS = [
  { value: 'applicant', label: 'applicant / 申请人' },
  { value: 'applicationYear', label: 'applicationYear / 申请年份' },
  { value: 'province', label: 'province / 省份' },
  { value: 'legalStatus', label: 'legalStatus / 法律状态' },
  { value: 'ipc', label: 'ipc / IPC 分类' },
]

function patentSearchFields(
  payload: Record<string, unknown>,
  tr: (key: string, fallback: string) => string,
): SkillParamFieldDef[] {
  const cmd = String(payload.command || 'search').toLowerCase()
  const fields: SkillParamFieldDef[] = [
    {
      key: 'command',
      label: tr('workflows.payloadCommand', 'command'),
      type: 'select',
      options: [
        { value: 'search', label: 'search' },
        { value: 'analysis', label: 'analysis' },
        { value: 'export_analysis', label: 'export_analysis' },
      ],
    },
  ]

  if (cmd === 'search' || cmd === 'analysis' || cmd === 'export_analysis') {
    fields.push({
      key: 'query',
      label: tr('workflows.payloadQuery', 'query'),
      type: 'text',
      placeholder: '${input.keyword}',
      hint: tr('workflows.paramBindHint', '可填固定值，或 ${input.xxx} 绑定开始节点'),
    })
  }

  if (cmd === 'search') {
    fields.push({
      key: 'industry',
      label: tr('workflows.payloadIndustry', 'industry'),
      type: 'text',
      placeholder: '${input.industry}',
    })
  }

  if (cmd === 'analysis') {
    fields.push({
      key: 'dimension',
      label: tr('workflows.payloadDimension', 'dimension'),
      type: 'select',
      options: PATENT_ANALYSIS_DIMENSIONS,
    })
    const dim = String(payload.dimension || '')
    if (dim === 'applicationYear') {
      fields.push(
        {
          key: 'year_from',
          label: tr('workflows.inputYearFrom', '申请年份起'),
          type: 'number',
          placeholder: '2020',
          hint: tr('workflows.paramYearEmptyHint', '留空表示不限制起始年'),
        },
        {
          key: 'year_to',
          label: tr('workflows.inputYearTo', '申请年份止'),
          type: 'number',
          placeholder: '2024',
          hint: tr('workflows.paramYearEmptyHint', '留空表示不限制结束年'),
        },
      )
    }
  }

  if (cmd === 'export_analysis') {
    fields.push({
      key: 'filename',
      label: tr('workflows.payloadFilename', 'filename'),
      type: 'text',
      placeholder: '${input.report_title}',
    })
  }

  return fields
}

function patentReportFields(
  payload: Record<string, unknown>,
  tr: (key: string, fallback: string) => string,
): SkillParamFieldDef[] {
  const cmd = String(payload.command || 'chart').toLowerCase()
  const fields: SkillParamFieldDef[] = [
    {
      key: 'command',
      label: tr('workflows.payloadCommand', 'command'),
      type: 'select',
      options: [
        { value: 'chart', label: 'chart' },
        { value: 'excel', label: 'excel' },
        { value: 'word', label: 'word' },
        { value: 'ppt', label: 'ppt' },
        { value: 'all', label: 'all' },
      ],
    },
    {
      key: 'sections',
      label: 'sections',
      type: 'text',
      placeholder: '${nodes.merge.sections}',
      hint: tr('workflows.paramSectionsHint', '通常绑定 merge 节点输出'),
    },
  ]

  if (cmd === 'chart' || cmd === 'all' || cmd === 'word' || cmd === 'ppt') {
    fields.push({
      key: 'charts',
      label: 'charts',
      type: 'text',
      placeholder: '${nodes.chart.charts}',
      show: (p) => ['all', 'word', 'ppt'].includes(String(p.command || '').toLowerCase()),
    })
  }

  fields.push(
    {
      key: 'title',
      label: tr('workflows.payloadTitle', 'title'),
      type: 'text',
      placeholder: '${input.report_title}',
      hint: tr('workflows.paramReportTitleHint', '运行时可改报告名称；此处可绑定 ${input.report_title}'),
    },
  )

  if (cmd !== 'chart') {
    fields.push({
      key: 'filename',
      label: tr('workflows.payloadFilename', 'filename'),
      type: 'text',
      placeholder: '${input.report_title}',
    })
  }

  return fields.filter((f) => !f.show || f.show(payload))
}

function genericSkillFields(tr: (key: string, fallback: string) => string): SkillParamFieldDef[] {
  return [
    { key: 'command', label: tr('workflows.payloadCommand', 'command'), type: 'text' },
    { key: 'query', label: tr('workflows.payloadQuery', 'query'), type: 'text', placeholder: '${input.keyword}' },
    { key: 'title', label: tr('workflows.payloadTitle', 'title'), type: 'text' },
    { key: 'filename', label: tr('workflows.payloadFilename', 'filename'), type: 'text' },
  ]
}

export function resolveSkillParamFields(
  skillName: string,
  payload: Record<string, unknown>,
  t?: (key: string) => string,
  workflowFields?: Record<string, any>,
): SkillParamFieldDef[] {
  if (workflowFields) {
    return Object.entries(workflowFields).map(([k, def]) => ({ key: k, ...def } as SkillParamFieldDef))
  }
  const tr = (key: string, fallback: string) => (t ? t(key) : fallback)
  const name = skillName.trim().toLowerCase()
  if (name === 'patent-search') return patentSearchFields(payload, tr)
  if (name === 'patent-report') return patentReportFields(payload, tr)
  return genericSkillFields(tr)
}

/** When dimension switches to applicationYear, ensure year keys exist on payload. */
export function patchPayloadForSkillParams(
  skillName: string,
  payload: Record<string, unknown>,
  changedKey: string,
): Record<string, unknown> {
  if (skillName !== 'patent-search' || changedKey !== 'dimension') return payload
  const dim = String(payload.dimension || '')
  const next = { ...payload }
  if (dim === 'applicationYear') {
    if (!('year_from' in next)) next.year_from = ''
    if (!('year_to' in next)) next.year_to = ''
  } else {
    delete next.year_from
    delete next.year_to
  }
  return next
}
