import { useState, useMemo } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  Bot,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Container,
  FolderOpen,
  Globe,
  Headphones,
  Home,
  LayoutDashboard,
  LayoutTemplate,
  Lock,
  MessageCircle,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Puzzle,
  Settings,
  Send,
  BarChart3,
  Users,
  Workflow as WorkflowIcon,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { isCloudEdition } from '@/lib/edition'

interface NavItem {
  path: string
  labelKey: string
  icon: React.ComponentType<{ className?: string }>
  exact?: boolean
}

interface NavGroup {
  titleKey: string
  items: NavItem[]
}

const adminNavGroups: NavGroup[] = [
  {
    titleKey: 'navGroup.core',
    items: [
      { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true },
      { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    ],
  },
  {
    titleKey: 'navGroup.knowledge',
    items: [
      { path: '/admin/knowledge', labelKey: 'nav.knowledge', icon: BookOpen },
    ],
  },
  {
    titleKey: 'navGroup.ai',
    items: [
      { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
      { path: '/admin/agents', labelKey: 'nav.agents', icon: Bot },
      { path: '/admin/customer-agents', labelKey: 'nav.customerAgents', icon: Headphones },
    ],
  },
  {
    titleKey: 'navGroup.dev',
    items: [
      { path: '/admin/workflows', labelKey: 'nav.workflows', icon: WorkflowIcon },
      { path: '/admin/workflow-center', labelKey: 'nav.workflowCenter', icon: LayoutTemplate },
      { path: '/admin/devbridge', labelKey: 'nav.devbridge', icon: Code2 },
      { path: '/admin/workspace', labelKey: 'nav.workspace', icon: Container },
      { path: '/admin/files', labelKey: 'nav.files', icon: FolderOpen },
      { path: '/admin/schedules', labelKey: 'nav.schedules', icon: Clock3 },
    ],
  },
  {
    titleKey: 'navGroup.management',
    items: [
      { path: '/admin/settings', labelKey: 'nav.settings', icon: Settings },
      { path: '/admin/channels', labelKey: 'nav.channels', icon: Globe },
      { path: '/admin/publishing-accounts', labelKey: 'nav.publishingAccounts', icon: Send },
      { path: '/admin/send-records', labelKey: 'nav.sendRecords', icon: BarChart3 },
      { path: '/admin/users', labelKey: 'nav.users', icon: Users },
      { path: '/admin/roles', labelKey: 'nav.roles', icon: Lock },
      { path: '/admin/groups', labelKey: 'nav.groups', icon: Users },
    ],
  },
]

const agentNavGroups: NavGroup[] = [
  {
    titleKey: 'navGroup.core',
    items: [
      { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true },
      { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    ],
  },
  {
    titleKey: 'navGroup.ai',
    items: [
      { path: '/admin/knowledge', labelKey: 'nav.knowledge', icon: BookOpen },
      { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
      { path: '/admin/agents', labelKey: 'nav.agents', icon: Bot },
      { path: '/admin/customer-agents', labelKey: 'nav.customerAgents', icon: Headphones },
    ],
  },
  {
    titleKey: 'navGroup.dev',
    items: [
      { path: '/admin/workflows', labelKey: 'nav.workflows', icon: WorkflowIcon },
      { path: '/admin/devbridge', labelKey: 'nav.devbridge', icon: Code2 },
      { path: '/admin/workspace', labelKey: 'nav.workspace', icon: Container },
      { path: '/admin/files', labelKey: 'nav.files', icon: FolderOpen },
      { path: '/admin/schedules', labelKey: 'nav.schedules', icon: Clock3 },
    ],
  },
]

interface SidebarProps {
  onClose?: () => void
  onCollapseChange?: (collapsed: boolean) => void
}

export function Sidebar({ onClose, onCollapseChange }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [collapsed, setCollapsed] = useState(false)
  const navGroups = useMemo(
    () =>
      user?.role === 'admin'
        ? adminNavGroups.filter((group) => isCloudEdition || group.titleKey !== 'navGroup.business')
        : agentNavGroups,
    [user?.role],
  )

  // Collapse state per group (persisted)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('mchat-nav-collapsed')
      return saved ? new Set(JSON.parse(saved)) : new Set()
    } catch {
      return new Set()
    }
  })

  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      localStorage.setItem('mchat-nav-collapsed', JSON.stringify([...next]))
      return next
    })
  }

  const isActive = (item: NavItem) => {
    if (item.exact) return location.pathname === item.path
    return location.pathname.startsWith(item.path)
  }

  // Auto-expand group containing active route
  const activeGroupKey = useMemo(() => {
    for (const g of navGroups) {
      if (g.items.some(isActive)) return g.titleKey
    }
    return null
  }, [navGroups, location.pathname])

  const handleToggle = () => {
    const next = !collapsed
    setCollapsed(next)
    onCollapseChange?.(next)
  }

  return (
    <aside className={cn(
      'h-full bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col transition-all duration-200',
      collapsed ? 'w-16' : 'w-64'
    )}>
      {/* Header */}
      <div className={cn(
        'h-16 flex items-center border-b border-gray-200 dark:border-gray-700 shrink-0 gap-2',
        collapsed ? 'justify-center px-2' : 'justify-between px-4'
      )}>
        {!collapsed && (
          <div className="flex items-center gap-2 cursor-pointer min-w-0" onClick={() => navigate('/admin')}>
            <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-gray-900 dark:text-gray-100 truncate">MChat</span>
          </div>
        )}
        <button
          type="button"
          onClick={handleToggle}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700 shrink-0 hidden lg:block"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </button>
        {!collapsed && onClose && (
          <button type="button" onClick={onClose} className="lg:hidden p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700" title="Close sidebar" aria-label="Close sidebar">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Nav items — grouped */}
      <nav className="flex-1 py-2 px-2 overflow-y-auto scrollbar-hide">
        {navGroups.map((group) => {
          const isCollapsed = collapsedGroups.has(group.titleKey)
          const hasActive = group.titleKey === activeGroupKey
          return (
            <div key={group.titleKey} className="mb-0.5">
              {!collapsed && (
                <button
                  type="button"
                  onClick={() => toggleGroup(group.titleKey)}
                  className={cn(
                    'flex w-full items-center gap-1 px-2 py-1 text-xs font-medium tracking-wide rounded transition-colors',
                    hasActive
                      ? 'text-primary-600 dark:text-primary-400'
                      : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'
                  )}
                >
                  {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  <span>{t(group.titleKey)}</span>
                </button>
              )}
              {(!isCollapsed || collapsed) && (
                <ul className={cn('space-y-0.5', !collapsed && 'mt-0.5')}>
                  {group.items.map((item) => (
                    <li key={item.path}>
                      <button
                        type="button"
                        onClick={() => { navigate(item.path); onClose?.() }}
                        className={cn(
                          'w-full flex items-center gap-3 rounded-lg text-sm font-medium transition-colors',
                          collapsed ? 'justify-center px-2 py-2' : 'px-3 py-1.5',
                          isActive(item)
                            ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                            : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700',
                        )}
                        title={collapsed ? t(item.labelKey) : undefined}
                      >
                        <item.icon className="w-4 h-4 shrink-0" />
                        {!collapsed && (
                          <span className="flex-1 text-left truncate">{t(item.labelKey)}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      <div className={cn('border-t border-gray-200 dark:border-gray-700 space-y-1', collapsed ? 'px-1 py-2' : 'px-2 py-3')}>
        <Link to="/" className={cn(
          'flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
          collapsed ? 'justify-center px-1 py-2' : 'px-3 py-1.5',
        )} title={t('common.home')}>
          <Home className="w-4 h-4 shrink-0" />
          {!collapsed && <span>{t('common.home')}</span>}
        </Link>
        <a href="/widget/demo" target="_blank" rel="noopener noreferrer" className={cn(
          'flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
          collapsed ? 'justify-center px-1 py-2' : 'px-3 py-1.5',
        )} title={t('nav.widgetPreview')}>
          <MessageCircle className="w-4 h-4 shrink-0" />
          {!collapsed && <span>{t('nav.widgetPreview')}</span>}
        </a>
      </div>
    </aside>
  )
}
