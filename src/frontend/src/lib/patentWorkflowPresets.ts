import type { WorkflowSkillCategory } from '@/lib/workflowSkillMeta'

/** Default canonical ids — override via GET /workflows/showcase-config */
export const DEFAULT_PATENT_SEARCH_SKILL = 'patent-search'
export const DEFAULT_PATENT_REPORT_SKILL = 'patent-report'

export interface PatentShowcaseConfig {
  enabled: boolean
  search_skill: string
  report_skill: string
  skills_dir?: string
  extra_skills_dirs?: string[]
  patent_skills_source?: string
  installed?: { search?: boolean; report?: boolean }
  on_disk?: { search?: boolean; report?: boolean }
  ready?: boolean
}

export interface PatentWorkflowPreset {
  id: string
  workflowRole: WorkflowSkillCategory
  skillName: string
  payloadTemplate: Record<string, unknown>
  i18n: {
    zh: { title: string; description: string }
    en: { title: string; description: string }
  }
}

export function buildPatentWorkflowPresets(
  searchSkill: string = DEFAULT_PATENT_SEARCH_SKILL,
  reportSkill: string = DEFAULT_PATENT_REPORT_SKILL,
): PatentWorkflowPreset[] {
  return [
    {
      id: 'patent_search',
      workflowRole: 'search',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'search',
        query: '${input.keyword}',
        industry: '${input.industry}',
      },
      i18n: {
        zh: { title: '行业专利检索', description: `${searchSkill} · search` },
        en: { title: 'Industry patent search', description: `${searchSkill} · search` },
      },
    },
    {
      id: 'patent_applicant',
      workflowRole: 'analyze',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'analysis',
        query: '${input.keyword}',
        dimension: 'applicant',
      },
      i18n: {
        zh: { title: '申请人分析', description: `${searchSkill} · analysis/applicant` },
        en: { title: 'Applicant analysis', description: `${searchSkill} · analysis/applicant` },
      },
    },
    {
      id: 'patent_year',
      workflowRole: 'analyze',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'analysis',
        query: '${input.keyword}',
        dimension: 'applicationYear',
        year_from: '2020',
        year_to: '2024',
      },
      i18n: {
        zh: { title: '年份趋势', description: `${searchSkill} · analysis/applicationYear` },
        en: { title: 'Application year trend', description: `${searchSkill} · analysis/applicationYear` },
      },
    },
    {
      id: 'patent_province',
      workflowRole: 'analyze',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'analysis',
        query: '${input.keyword}',
        dimension: 'province',
      },
      i18n: {
        zh: { title: '区域分布', description: `${searchSkill} · analysis/province` },
        en: { title: 'Regional distribution', description: `${searchSkill} · analysis/province` },
      },
    },
    {
      id: 'patent_legal',
      workflowRole: 'analyze',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'analysis',
        query: '${input.keyword}',
        dimension: 'legalStatus',
      },
      i18n: {
        zh: { title: '法律状态', description: `${searchSkill} · analysis/legalStatus` },
        en: { title: 'Legal status', description: `${searchSkill} · analysis/legalStatus` },
      },
    },
    {
      id: 'patent_ipc',
      workflowRole: 'analyze',
      skillName: searchSkill,
      payloadTemplate: {
        command: 'analysis',
        query: '${input.keyword}',
        dimension: 'ipc',
      },
      i18n: {
        zh: { title: 'IPC 分类', description: `${searchSkill} · analysis/ipc` },
        en: { title: 'IPC classification', description: `${searchSkill} · analysis/ipc` },
      },
    },
    {
      id: 'patent_chart',
      workflowRole: 'visualize',
      skillName: reportSkill,
      payloadTemplate: {
        command: 'chart',
        sections: '${nodes.merge.sections}',
        title: '${input.report_title}',
      },
      i18n: {
        zh: { title: '图表生成', description: `${reportSkill} · chart` },
        en: { title: 'Chart generation', description: `${reportSkill} · chart` },
      },
    },
    {
      id: 'patent_export_excel',
      workflowRole: 'export',
      skillName: reportSkill,
      payloadTemplate: {
        command: 'excel',
        sections: '${nodes.merge.sections}',
        title: '${input.report_title}',
        filename: '${input.report_title}',
      },
      i18n: {
        zh: { title: '导出 Excel', description: `${reportSkill} · excel` },
        en: { title: 'Export Excel', description: `${reportSkill} · excel` },
      },
    },
    {
      id: 'patent_export_word',
      workflowRole: 'export',
      skillName: reportSkill,
      payloadTemplate: {
        command: 'word',
        sections: '${nodes.merge.sections}',
        charts: '${nodes.chart.charts}',
        title: '${input.report_title}',
        filename: '${input.report_title}',
      },
      i18n: {
        zh: { title: '导出 Word', description: `${reportSkill} · word` },
        en: { title: 'Export Word', description: `${reportSkill} · word` },
      },
    },
    {
      id: 'patent_export_ppt',
      workflowRole: 'export',
      skillName: reportSkill,
      payloadTemplate: {
        command: 'ppt',
        sections: '${nodes.merge.sections}',
        charts: '${nodes.chart.charts}',
        title: '${input.report_title}',
        filename: '${input.report_title}',
      },
      i18n: {
        zh: { title: '导出 PPT', description: `${reportSkill} · ppt` },
        en: { title: 'Export PowerPoint', description: `${reportSkill} · ppt` },
      },
    },
    {
      id: 'patent_export',
      workflowRole: 'export',
      skillName: reportSkill,
      payloadTemplate: {
        command: 'all',
        sections: '${nodes.merge.sections}',
        charts: '${nodes.chart.charts}',
        title: '${input.report_title}',
        filename: '${input.report_title}',
      },
      i18n: {
        zh: { title: '全套报告导出', description: `${reportSkill} · all` },
        en: { title: 'Full report export', description: `${reportSkill} · all` },
      },
    },
  ]
}

/** Fallback when showcase-config API is unavailable */
export const PATENT_WORKFLOW_PRESETS = buildPatentWorkflowPresets()

export function getPatentPresetById(
  id: string,
  presets: PatentWorkflowPreset[] = PATENT_WORKFLOW_PRESETS,
): PatentWorkflowPreset | undefined {
  return presets.find((p) => p.id === id)
}

export function getPatentPresetTitle(preset: PatentWorkflowPreset, locale: string): string {
  return locale.startsWith('zh') ? preset.i18n.zh.title : preset.i18n.en.title
}

export function getPatentPresetDescription(preset: PatentWorkflowPreset, locale: string): string {
  return locale.startsWith('zh') ? preset.i18n.zh.description : preset.i18n.en.description
}
