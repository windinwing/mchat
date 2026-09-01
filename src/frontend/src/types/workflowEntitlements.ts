export interface WorkflowEntitlements {
  plan: string
  max_workflows: number | null
  max_schedules: number | null
  max_runs_month: number | null
  dag_enabled: boolean
  channel_triggers_enabled: boolean
  workflow_count: number
  schedule_count: number
  runs_month: number
  can_create_workflow: boolean
  can_create_schedule: boolean
  can_run_workflow: boolean
  upgrade_required: boolean
  upgrade_template_id: string | null
  upgrade_channel_id: string | null
  upgrade_template_name: string | null
  upgrade_amount_cents: number | null
  upgrade_instant: boolean
  upgrade_purpose: string
  plan_label: string
}
