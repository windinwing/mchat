/** Display label for workflow run list / detail (report name vs workflow template name). */

export function resolveRunDisplayName(run: {
  display_name?: string | null
  workflow_name: string
  input_payload?: Record<string, unknown> | null
}): string {
  const fromApi = String(run.display_name || '').trim()
  if (fromApi) return fromApi
  const payload = run.input_payload || {}
  const runLabel = String(payload.run_label || '').trim()
  if (runLabel) return runLabel
  const reportTitle = String(payload.report_title || '').trim()
  if (reportTitle) return reportTitle
  const keyword = String(payload.keyword || '').trim()
  if (keyword) return keyword
  return run.workflow_name || 'Workflow run'
}

export function runListSubtitle(run: {
  display_name?: string | null
  workflow_name: string
  input_payload?: Record<string, unknown> | null
}): string | null {
  const display = resolveRunDisplayName(run)
  const wf = (run.workflow_name || '').trim()
  if (!wf || display === wf) return null
  return wf
}
