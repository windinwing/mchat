import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft,
  LayoutTemplate,
  Network,
  Search,
  Share2,
  Users,
} from 'lucide-react'
import api from '@/lib/api'
import { extractAutomationLimit, automationCheckoutPath, limitMessage, type AutomationLimitDetail } from '@/lib/automationLimit'
import { EntitlementConfirmDialog } from '@/components/workflow/EntitlementConfirmDialog'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { WorkflowEntitlementBanner } from '@/components/portal/WorkflowEntitlementBanner'
import { cn } from '@/lib/utils'

interface WorkflowTemplateItem {
  id: string
  name: string
  description: string
  category: string
  locale?: string | null
  node_count: number
  builtin?: boolean
  visibility?: string
  author_id?: string | null
  author_name?: string | null
  use_count?: number
  is_mine?: boolean
}

interface WorkflowMarketplace {
  system: WorkflowTemplateItem[]
  community: WorkflowTemplateItem[]
  mine: WorkflowTemplateItem[]
}

type TabKey = 'all' | 'system' | 'community' | 'mine'

export function WorkflowCenterPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const isPortal = location.pathname.startsWith('/portal')
  const workflowsPath = isPortal ? '/portal/workflows' : '/admin/workflows'
  const uiLocale = i18n.language?.startsWith('zh') ? 'zh' : 'en'

  const [loading, setLoading] = useState(true)
  const [creatingId, setCreatingId] = useState<string | null>(null)
  const [sharingId, setSharingId] = useState<string | null>(null)
  const [data, setData] = useState<WorkflowMarketplace | null>(null)
  const [tab, setTab] = useState<TabKey>('all')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [entitlementLimit, setEntitlementLimit] = useState<AutomationLimitDetail | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get<WorkflowMarketplace>('/workflows/marketplace', {
        locale: uiLocale,
      })
      setData(res)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('workflows.toastLoadFailed'), {
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [uiLocale])

  const items = useMemo(() => {
    if (!data) return []
    if (tab === 'system') return data.system
    if (tab === 'community') return data.community
    if (tab === 'mine') return data.mine
    return [...data.system, ...data.community, ...data.mine]
  }, [data, tab])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items.filter((item) => {
      if (category !== 'all' && item.category !== category) return false
      if (!q) return true
      return (
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        (item.author_name || '').toLowerCase().includes(q)
      )
    })
  }, [items, search, category])

  const useTemplate = async (tpl: WorkflowTemplateItem) => {
    setCreatingId(tpl.id)
    try {
      const wf = await api.post<{ id: string }>(`/workflows/from-template/${tpl.id}`, {
        name: tpl.name,
      })
      toast(t('workflows.toastTemplateCreated'), { type: 'success' })
      navigate(`${workflowsPath}?open=${wf.id}`)
    } catch (err: unknown) {
      const limit = extractAutomationLimit(err)
      if (limit) {
        setEntitlementLimit(limit)
      } else {
        toast(err instanceof Error ? err.message : t('workflows.toastTemplateCreateFailed'), {
          type: 'error',
        })
      }
    } finally {
      setCreatingId(null)
    }
  }

  const toggleShare = async (tpl: WorkflowTemplateItem) => {
    if (!tpl.is_mine || tpl.builtin) return
    const next = tpl.visibility === 'shared' ? 'private' : 'shared'
    setSharingId(tpl.id)
    try {
      await api.patch(`/workflows/templates/${tpl.id}/visibility`, { visibility: next })
      toast(
        next === 'shared'
          ? t('workflowCenter.toastShared')
          : t('workflowCenter.toastUnshared'),
        { type: 'success' },
      )
      await load()
    } catch (err) {
      toast(err instanceof Error ? err.message : t('workflowCenter.toastShareFailed'), {
        type: 'error',
      })
    } finally {
      setSharingId(null)
    }
  }

  const categoryOptions = [
    { value: 'all', label: t('common.all') },
    { value: 'patent', label: t('workflowCenter.categoryPatent') },
    { value: 'notification', label: t('workflowCenter.categoryNotify') },
    { value: 'custom', label: t('workflowCenter.categoryCustom') },
    { value: 'general', label: t('workflowCenter.categoryGeneral') },
  ]

  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: 'all', label: t('common.all'), count: (data?.system.length || 0) + (data?.community.length || 0) + (data?.mine.length || 0) },
    { key: 'system', label: t('workflowCenter.tabSystem'), count: data?.system.length || 0 },
    { key: 'community', label: t('workflowCenter.tabCommunity'), count: data?.community.length || 0 },
    { key: 'mine', label: t('workflowCenter.tabMine'), count: data?.mine.length || 0 },
  ]

  if (loading && !data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            to={workflowsPath}
            className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-primary-600 mb-2"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('workflowCenter.backWorkflows')}
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <LayoutTemplate className="w-6 h-6 text-primary-600" />
            {t('workflowCenter.title')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('workflowCenter.subtitle')}
          </p>
        </div>
        <Link to={workflowsPath}>
          <Button variant="secondary" leftIcon={<Network className="w-4 h-4" />}>
            {t('workflowCenter.openEditor')}
          </Button>
        </Link>
      </div>

      {isPortal && <WorkflowEntitlementBanner />}

      <div className="flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={cn(
              'px-3 py-1.5 rounded-full text-sm border transition-colors',
              tab === item.key
                ? 'bg-primary-600 text-white border-primary-600'
                : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800',
            )}
          >
            {item.label}
            <span className="ml-1 opacity-80">({item.count})</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[12rem]">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('workflowCenter.searchPlaceholder')}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="w-44 shrink-0">
          <Select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            options={categoryOptions}
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          <LayoutTemplate className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p>{t('workflowCenter.empty')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {filtered.map((tpl) => (
            <article
              key={`${tpl.builtin ? 'b' : 'u'}-${tpl.id}`}
              className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm flex flex-col gap-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                    {tpl.name}
                  </h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                    {tpl.description || t('common.noData')}
                  </p>
                </div>
                <Badge variant="info" size="sm" className="shrink-0">
                  {tpl.node_count} {t('workflowCenter.nodes')}
                </Badge>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {tpl.builtin || tpl.visibility === 'system' ? (
                  <Badge variant="info" size="sm">{t('workflowCenter.badgeSystem')}</Badge>
                ) : tpl.visibility === 'shared' ? (
                  <Badge variant="success" size="sm">{t('workflowCenter.badgeShared')}</Badge>
                ) : (
                  <Badge variant="default" size="sm">{t('workflowCenter.badgePrivate')}</Badge>
                )}
                {tpl.category ? (
                  <Badge variant="default" size="sm">{tpl.category}</Badge>
                ) : null}
              </div>

              <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                <Users className="w-3.5 h-3.5" />
                {tpl.author_name || (tpl.builtin ? 'MChat' : t('workflowCenter.authorUnknown'))}
                {(tpl.use_count || 0) > 0 && (
                  <span className="ml-2">
                    · {t('workflowCenter.useCount', { count: tpl.use_count })}
                  </span>
                )}
              </p>

              <div className="flex flex-wrap gap-2 mt-auto pt-1">
                <Button
                  size="sm"
                  isLoading={creatingId === tpl.id}
                  onClick={() => useTemplate(tpl)}
                >
                  {t('workflows.useTemplate')}
                </Button>
                {tpl.is_mine && !tpl.builtin ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<Share2 className="w-4 h-4" />}
                    isLoading={sharingId === tpl.id}
                    onClick={() => toggleShare(tpl)}
                  >
                    {tpl.visibility === 'shared'
                      ? t('workflowCenter.unshare')
                      : t('workflowCenter.share')}
                  </Button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
      <EntitlementConfirmDialog
        limit={entitlementLimit}
        onClose={() => setEntitlementLimit(null)}
        isPortal={isPortal}
      />
    </div>
  )
}
