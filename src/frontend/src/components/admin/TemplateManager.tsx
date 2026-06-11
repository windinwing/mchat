import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff, Edit3, Plus, Trash2, Bot, MessageSquare, FileSearch, Stethoscope, Scale, ShoppingCart, GraduationCap, Building2, Globe, Headphones } from 'lucide-react'
import api from '@/lib/api'
import { tenantSelectableSkills } from '@/lib/skillUtils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { Tabs, TabPanel } from '@/components/ui/Tabs'

interface Template {
  id: string; name: string; description: string | null; category: string
  icon: string | null; price_monthly_cents: number; price_yearly_cents: number
  trial_days: number; is_published: boolean; sort_order: number
  default_ai_config_id: string | null; default_ai_config_spec: any
  default_skill_ids: string[] | null
  default_knowledge_base_ids: string[] | null
  default_knowledge_base_spec: any; default_theme: any
  default_welcome_message: string | null; default_offline_message: string | null
  created_at: string; updated_at: string
}

interface AiConfigItem { id: string; name: string; provider: string; model: string }
interface SkillItem {
  id: string
  name: string
  description?: string | null
  config?: Record<string, unknown> | null
}
interface KnowledgeBaseItem { id: string; name: string; description?: string | null }

const ICONS: { name: string; icon: React.ComponentType<{className?: string}>; label: string }[] = [
  { name: 'MessageSquare', icon: MessageSquare, label: 'Chat/客服' },
  { name: 'Bot', icon: Bot, label: 'Bot/AI' },
  { name: 'FileSearch', icon: FileSearch, label: 'Patent/搜索' },
  { name: 'Stethoscope', icon: Stethoscope, label: 'Medical/医疗' },
  { name: 'Scale', icon: Scale, label: 'Legal/法律' },
  { name: 'ShoppingCart', icon: ShoppingCart, label: 'E-commerce' },
  { name: 'GraduationCap', icon: GraduationCap, label: 'Education' },
  { name: 'Building2', icon: Building2, label: 'Enterprise' },
  { name: 'Globe', icon: Globe, label: 'Web/通用' },
  { name: 'Headphones', icon: Headphones, label: 'Support' },
]

const CATEGORIES = [
  { value: 'customer_service', label: 'Customer Service (客服)' },
  { value: 'patent_rag', label: 'Patent RAG (专利)' },
  { value: 'medical_rag', label: 'Medical RAG (医疗)' },
  { value: 'legal_rag', label: 'Legal RAG (法律)' },
  { value: 'education', label: 'Education (教育)' },
  { value: 'enterprise', label: 'Enterprise (企业)' },
]

export function TemplateManager() {
  const { t } = useTranslation()
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Template | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [aiConfigs, setAiConfigs] = useState<AiConfigItem[]>([])
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([])
  const [activeTab, setActiveTab] = useState('basic')

  const defaultKbSpec = {
    name: '工作空间知识库',
    description: '租用模板时自动创建',
    chunk_strategy: 'fixed',
    chunk_size: 1000,
    chunk_overlap: 100,
    retrieval_mode: 'hybrid',
  }

  const emptyForm = {
    name: '', description: '', category: 'customer_service', icon: 'MessageSquare',
    price_monthly_cents: 0, price_yearly_cents: 0, trial_days: 14,
    is_published: false, sort_order: 0,
    default_welcome_message: '', default_offline_message: '',
    default_ai_config_id: '',
    default_skill_ids: [] as string[],
    kb_mode: 'auto' as 'none' | 'existing' | 'auto',
    default_knowledge_base_ids: [] as string[],
    kb_auto_name: defaultKbSpec.name,
    kb_auto_description: defaultKbSpec.description,
    kb_auto_chunk_size: defaultKbSpec.chunk_size,
    kb_auto_chunk_overlap: defaultKbSpec.chunk_overlap,
    kb_auto_retrieval_mode: defaultKbSpec.retrieval_mode,
    default_theme: JSON.stringify({ primaryColor: '#3b82f6', botName: 'Assistant', widgetTitle: 'Chat' }, null, 2),
  }
  const [form, setForm] = useState(emptyForm)
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))

  const load = async () => {
    setLoading(true)
    try {
      const [tpl, aic, sk, kb] = await Promise.all([
        api.get<Template[]>('/admin/templates'),
        api.get<AiConfigItem[]>('/agents/ai-configs').catch(() => []),
        api.get<SkillItem[]>('/skills').catch(() => []),
        api.get<KnowledgeBaseItem[]>('/knowledge/bases').catch(() => []),
      ])
      setTemplates(tpl)
      setAiConfigs(aic)
      setSkills(tenantSelectableSkills(sk))
      setKnowledgeBases(kb)
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const kbSpecToForm = (spec: any) => {
    const s = spec || defaultKbSpec
    return {
      kb_auto_name: s.name || defaultKbSpec.name,
      kb_auto_description: s.description || defaultKbSpec.description,
      kb_auto_chunk_size: s.chunk_size ?? defaultKbSpec.chunk_size,
      kb_auto_chunk_overlap: s.chunk_overlap ?? defaultKbSpec.chunk_overlap,
      kb_auto_retrieval_mode: s.retrieval_mode || defaultKbSpec.retrieval_mode,
    }
  }

  const resolveKbMode = (tmpl: Template): 'none' | 'existing' | 'auto' => {
    if (tmpl.default_knowledge_base_ids?.length) return 'existing'
    if (tmpl.default_knowledge_base_spec?.name) return 'auto'
    return 'none'
  }

  const openEdit = (tmpl: Template) => {
    setEditing(tmpl); setCreating(false); setActiveTab('basic')
    const kbMode = resolveKbMode(tmpl)
    setForm({
      name: tmpl.name, description: tmpl.description || '', category: tmpl.category,
      icon: tmpl.icon || 'MessageSquare',
      price_monthly_cents: tmpl.price_monthly_cents, price_yearly_cents: tmpl.price_yearly_cents,
      trial_days: tmpl.trial_days, is_published: tmpl.is_published, sort_order: tmpl.sort_order,
      default_welcome_message: tmpl.default_welcome_message || '',
      default_offline_message: tmpl.default_offline_message || '',
      default_ai_config_id: tmpl.default_ai_config_id || '',
      default_skill_ids: tmpl.default_skill_ids || [],
      kb_mode: kbMode,
      default_knowledge_base_ids: tmpl.default_knowledge_base_ids || [],
      ...kbSpecToForm(tmpl.default_knowledge_base_spec),
      default_theme: JSON.stringify(tmpl.default_theme || {}, null, 2),
    })
  }

  const openCreate = () => {
    setEditing(null); setCreating(true); setActiveTab('basic'); setForm(emptyForm)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      let parsedTheme: any = {}
      try { parsedTheme = JSON.parse(form.default_theme) } catch {}
      let default_knowledge_base_ids: string[] | null = null
      let default_knowledge_base_spec: Record<string, unknown> | null = null
      if (form.kb_mode === 'existing') {
        default_knowledge_base_ids = form.default_knowledge_base_ids?.length
          ? form.default_knowledge_base_ids
          : null
      } else if (form.kb_mode === 'auto') {
        default_knowledge_base_spec = {
          name: form.kb_auto_name || defaultKbSpec.name,
          description: form.kb_auto_description || defaultKbSpec.description,
          chunk_strategy: 'fixed',
          chunk_size: Number(form.kb_auto_chunk_size) || defaultKbSpec.chunk_size,
          chunk_overlap: Number(form.kb_auto_chunk_overlap) || defaultKbSpec.chunk_overlap,
          retrieval_mode: form.kb_auto_retrieval_mode || defaultKbSpec.retrieval_mode,
        }
      }
      const payload = {
        name: form.name,
        description: form.description,
        category: form.category,
        icon: form.icon,
        price_monthly_cents: Number(form.price_monthly_cents),
        price_yearly_cents: Number(form.price_yearly_cents),
        trial_days: Number(form.trial_days),
        sort_order: Number(form.sort_order),
        is_published: form.is_published,
        default_welcome_message: form.default_welcome_message,
        default_offline_message: form.default_offline_message,
        default_ai_config_id: form.default_ai_config_id || null,
        default_skill_ids: form.default_skill_ids?.length ? form.default_skill_ids : null,
        default_knowledge_base_ids,
        default_knowledge_base_spec,
        default_theme: parsedTheme,
      }
      if (editing) await api.put(`/admin/templates/${editing.id}`, payload)
      else await api.post('/admin/templates', payload)
      setEditing(null); setCreating(false); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete?')) return
    try { await api.delete(`/admin/templates/${id}`); load() }
    catch (e: any) { setError(e.message) }
  }

  const handleTogglePublish = async (tmpl: Template) => {
    try { await api.put(`/admin/templates/${tmpl.id}`, { is_published: !tmpl.is_published }); load() }
    catch (e: any) { setError(e.message) }
  }

  if (loading) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>

  const toggleSkill = (skillId: string) => {
    setForm((f: any) => {
      const ids: string[] = f.default_skill_ids || []
      const next = ids.includes(skillId)
        ? ids.filter((id: string) => id !== skillId)
        : [...ids, skillId]
      return { ...f, default_skill_ids: next }
    })
  }

  const toggleKnowledgeBase = (kbId: string) => {
    setForm((f: any) => {
      const ids: string[] = f.default_knowledge_base_ids || []
      const next = ids.includes(kbId)
        ? ids.filter((id: string) => id !== kbId)
        : [...ids, kbId]
      return { ...f, default_knowledge_base_ids: next }
    })
  }

  const formTabs = [
    { id: 'basic', label: 'Basic' },
    { id: 'ai', label: 'AI' },
    { id: 'skills', label: 'Skills' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'widget', label: '网站挂件' },
  ]

  return (
    <div className="space-y-4">
      {error && <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">{error}</div>}

      <div className="flex justify-between items-center">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Templates ({templates.length})</h2>
        <Button onClick={openCreate} size="sm"><Plus className="w-4 h-4 mr-1" />New</Button>
      </div>

      <div className="space-y-2">
        {templates.map((tmpl) => {
          const IconComp = ICONS.find(i => i.name === tmpl.icon)?.icon || MessageSquare
          return (
            <div key={tmpl.id} className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <IconComp className="w-5 h-5 text-gray-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate text-gray-900 dark:text-gray-100">{tmpl.name}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500">{tmpl.category}</span>
                  {tmpl.is_published ? <Eye className="w-3.5 h-3.5 text-green-500" /> : <EyeOff className="w-3.5 h-3.5 text-gray-400" />}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {tmpl.price_monthly_cents > 0 ? `¥${(tmpl.price_monthly_cents / 100).toFixed(0)}/mo` : 'Free'} · {tmpl.trial_days}d trial · #{tmpl.sort_order}
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => handleTogglePublish(tmpl)} className="p-1.5 text-gray-400 hover:text-primary-500 rounded">{tmpl.is_published ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                <button onClick={() => openEdit(tmpl)} className="p-1.5 text-gray-400 hover:text-primary-500 rounded"><Edit3 className="w-4 h-4" /></button>
                <button onClick={() => handleDelete(tmpl.id)} className="p-1.5 text-gray-400 hover:text-red-500 rounded"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          )
        })}
      </div>

      {(editing || creating) && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center pt-10 px-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-xl max-h-[85vh] overflow-y-auto">
            <div className="sticky top-0 bg-white dark:bg-gray-800 z-10 px-6 pt-6 pb-2 border-b border-gray-100 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{creating ? 'New Template' : `Edit: ${editing?.name}`}</h3>
            </div>
            <div className="px-6 py-4">
              <Tabs tabs={formTabs} activeTab={activeTab} onChange={setActiveTab} />
              <TabPanel id="basic" activeTab={activeTab}>
                <div className="space-y-4">
                  <Input label="Name *" value={form.name} onChange={e => set('name', e.target.value)} />
                  <div>
                    <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Description</label>
                    <textarea className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 p-2 text-sm" rows={3}
                      value={form.description} onChange={e => set('description', e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Category (行业分类，决定模板归属哪个垂直领域)</label>
                    <select className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 p-2 text-sm"
                      value={form.category} onChange={e => set('category', e.target.value)}>
                      {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Icon (在模板市场展示的图标)</label>
                    <div className="grid grid-cols-5 gap-2">
                      {ICONS.map(ic => (
                        <button key={ic.name} type="button" onClick={() => set('icon', ic.name)}
                          className={`flex flex-col items-center gap-1 p-2 rounded-lg border text-xs transition-colors ${
                            form.icon === ic.name ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700' : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:border-gray-300'
                          }`}>
                          <ic.icon className="w-5 h-5" />
                          <span className="truncate w-full text-center">{ic.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <Input label="Price (分/月, 0=免费)" type="number" value={String(form.price_monthly_cents)} onChange={e => set('price_monthly_cents', Number(e.target.value))} />
                    <Input label="Trial (天, 0=无试用)" type="number" value={String(form.trial_days)} onChange={e => set('trial_days', Number(e.target.value))} />
                    <Input label="Sort order" type="number" value={String(form.sort_order)} onChange={e => set('sort_order', Number(e.target.value))} />
                  </div>
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <input type="checkbox" checked={form.is_published} onChange={e => set('is_published', e.target.checked)} />
                    Published (在模板市场显示)
                  </label>
                </div>
              </TabPanel>
              <TabPanel id="ai" activeTab={activeTab}>
                <div className="space-y-3">
                  <p className="text-xs text-gray-500">选择引用的 AI 配置。新用户租用时会自动关联此配置。选"自定义"则在租用时实时创建。</p>
                  <div>
                    <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">引用 AI 配置 (在「AI 配置」页面管理)</label>
                    <select className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 p-2 text-sm"
                      value={form.default_ai_config_id} onChange={e => set('default_ai_config_id', e.target.value)}>
                      <option value="">-- 自定义（租用时创建新配置）--</option>
                      {aiConfigs.map(ac => (
                        <option key={ac.id} value={ac.id}>{ac.name} ({ac.provider} / {ac.model})</option>
                      ))}
                    </select>
                  </div>
                </div>
              </TabPanel>
              <TabPanel id="skills" activeTab={activeTab}>
                <div className="space-y-3">
                  <p className="text-xs text-gray-500">
                    租用模板时默认绑定的 Skill（如 patent-search）。用户可在工作空间详情页继续管理知识库与文档。
                  </p>
                  <div className="max-h-56 overflow-y-auto space-y-2 border border-gray-200 dark:border-gray-700 rounded-lg p-2">
                    {skills.length === 0 && (
                      <p className="text-xs text-gray-400 p-2">暂无技能，请先在「技能管理」中安装。</p>
                    )}
                    {skills.map((skill) => (
                      <label
                        key={skill.id}
                        className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={(form.default_skill_ids || []).includes(skill.id)}
                          onChange={() => toggleSkill(skill.id)}
                        />
                        <span className="text-sm">
                          <span className="font-medium text-gray-900 dark:text-gray-100">{skill.name}</span>
                          {skill.description && (
                            <span className="block text-xs text-gray-500 mt-0.5 line-clamp-2">{skill.description}</span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              </TabPanel>
              <TabPanel id="knowledge" activeTab={activeTab}>
                <div className="space-y-4">
                  <p className="text-xs text-gray-500">
                    租用模板时绑定到工作空间的知识库。可引用已有库，或按表单自动新建空库（用户再在「我的工作空间 → 知识库」上传文档）。
                  </p>
                  <div className="flex flex-wrap gap-4 text-sm">
                    {([
                      ['none', '不绑定知识库'],
                      ['existing', '引用已有知识库'],
                      ['auto', '租用时自动新建'],
                    ] as const).map(([value, label]) => (
                      <label key={value} className="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
                        <input
                          type="radio"
                          name="kb_mode"
                          checked={form.kb_mode === value}
                          onChange={() => set('kb_mode', value)}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                  {form.kb_mode === 'existing' && (
                    <div className="max-h-56 overflow-y-auto space-y-2 border border-gray-200 dark:border-gray-700 rounded-lg p-2">
                      {knowledgeBases.length === 0 && (
                        <p className="text-xs text-gray-400 p-2">暂无知识库，请先在「知识库管理」中创建。</p>
                      )}
                      {knowledgeBases.map((kb) => (
                        <label
                          key={kb.id}
                          className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={(form.default_knowledge_base_ids || []).includes(kb.id)}
                            onChange={() => toggleKnowledgeBase(kb.id)}
                          />
                          <span className="text-sm">
                            <span className="font-medium text-gray-900 dark:text-gray-100">{kb.name}</span>
                            {kb.description && (
                              <span className="block text-xs text-gray-500 mt-0.5 line-clamp-2">{kb.description}</span>
                            )}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                  {form.kb_mode === 'auto' && (
                    <div className="space-y-3 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                      <Input label="知识库名称" value={form.kb_auto_name} onChange={e => set('kb_auto_name', e.target.value)} />
                      <Input label="描述" value={form.kb_auto_description} onChange={e => set('kb_auto_description', e.target.value)} />
                      <div className="grid grid-cols-2 gap-3">
                        <Input label="分块大小" type="number" value={String(form.kb_auto_chunk_size)} onChange={e => set('kb_auto_chunk_size', Number(e.target.value))} />
                        <Input label="分块重叠" type="number" value={String(form.kb_auto_chunk_overlap)} onChange={e => set('kb_auto_chunk_overlap', Number(e.target.value))} />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">检索模式</label>
                        <select
                          className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 p-2 text-sm"
                          value={form.kb_auto_retrieval_mode}
                          onChange={e => set('kb_auto_retrieval_mode', e.target.value)}
                        >
                          <option value="hybrid">hybrid</option>
                          <option value="vector">vector</option>
                          <option value="keyword">keyword</option>
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              </TabPanel>
              <TabPanel id="widget" activeTab={activeTab}>
                <div className="space-y-3">
                  <Input label="Welcome message" value={form.default_welcome_message} onChange={e => set('default_welcome_message', e.target.value)} />
                  <Input label="Offline message" value={form.default_offline_message} onChange={e => set('default_offline_message', e.target.value)} />
                  <div>
                    <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Theme (JSON) — primaryColor, botName, widgetTitle, position</label>
                    <textarea className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 p-2 text-xs font-mono" rows={5}
                      value={form.default_theme} onChange={e => set('default_theme', e.target.value)} />
                  </div>
                </div>
              </TabPanel>
            </div>
            <div className="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-100 dark:border-gray-700 px-6 py-3 flex gap-2 justify-end">
              <Button variant="outline" onClick={() => { setEditing(null); setCreating(false) }}>Cancel</Button>
              <Button onClick={handleSave} isLoading={saving}>Save</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
