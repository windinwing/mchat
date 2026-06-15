import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Layers, Clock, Loader2 } from 'lucide-react'
import { WorkflowGraphEditor, type WorkflowGraphValue } from '@/components/workflow/WorkflowGraphEditor'
import { WorkflowTemplateGallery } from '@/components/workflow/WorkflowTemplateGallery'
import { WorkflowRunOverlay } from '@/components/workflow/WorkflowRunOverlay'
import { WorkflowSidebar } from '@/components/workflow/WorkflowSidebar'
import type { PresetItem } from '@/components/workflow/WorkflowSidebar'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { getPatentPresetTitle, getPatentPresetDescription, buildPatentWorkflowPresets } from '@/lib/patentWorkflowPresets'
import type { WorkflowSkillOption } from '@/lib/workflowSkillMeta'

interface WorkflowDetail {
  id: string
  name: string
  graph_json?: WorkflowGraphValue | null
}

export function WorkflowGraphPage() {
  const { t, i18n } = useTranslation()
  const { workflowId } = useParams<{ workflowId: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const locale = i18n.language || 'zh'

  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null)
  const [skills, setSkills] = useState<WorkflowSkillOption[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Overlays
  const [showTemplates, setShowTemplates] = useState(false)
  const [showRuns, setShowRuns] = useState(false)

  // Patent presets
  const presets: PresetItem[] = buildPatentWorkflowPresets().map((p) => ({
    id: p.id,
    title: getPatentPresetTitle(p, locale),
    description: getPatentPresetDescription(p, locale),
    skillName: p.skillName,
    missing: !skills.some((s) => s.name === p.skillName),
  }))

  useEffect(() => {
    const load = async () => {
      if (!workflowId) return
      setLoading(true)
      try {
        const [wf, sk] = await Promise.all([
          api.get<WorkflowDetail>(`/workflows/wf/${workflowId}`),
          api.get<WorkflowSkillOption[]>('/skills'),
        ])
        setWorkflow(wf)
        setSkills(sk || [])
      } catch {
        // navigate back on error
        navigate('/admin/workflows')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [workflowId, navigate])

  const handleSave = useCallback(
    async (graph: WorkflowGraphValue) => {
      if (!workflowId) return
      setSaving(true)
      try {
        await api.patch(`/workflows/${workflowId}`, { graph_json: graph })
        setWorkflow((prev) => (prev ? { ...prev, graph_json: graph } : prev))
      } catch {
        // ignore
      } finally {
        setSaving(false)
      }
    },
    [workflowId],
  )

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    )
  }

  return (
    <div className="h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <WorkflowGraphEditor
        value={workflow?.graph_json}
        skills={skills}
        onSave={handleSave}
        workflowId={workflowId}
        workflowName={workflow?.name}
        onBack={() => navigate('/admin/workflows')}
        presets={presets}
        headerExtra={
          <>
            <button
              type="button"
              onClick={() => setShowTemplates(true)}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Layers className="w-3.5 h-3.5" />
              {t('workflows.sidebarTemplates', 'Templates')}
            </button>
            <button
              type="button"
              onClick={() => setShowRuns(true)}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Clock className="w-3.5 h-3.5" />
              {t('workflows.sidebarHistory', 'History')}
            </button>
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
          </>
        }
      />

      {/* Overlay modals */}
      <WorkflowTemplateGallery
        open={showTemplates}
        onClose={() => setShowTemplates(false)}
        onApply={(graph) => {
          // Reload editor with template graph
          if (workflowId) {
            void handleSave(graph as WorkflowGraphValue)
          }
        }}
      />
      <WorkflowRunOverlay
        open={showRuns}
        onClose={() => setShowRuns(false)}
        workflowId={workflowId}
      />
    </div>
  )
}
