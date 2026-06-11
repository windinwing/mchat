import React, { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  MessageSquare,
  BookOpen,
  Puzzle,
  Bot,
  Settings,
  Globe,
  X,
  MessageCircle,
  Headphones,
  Home,
  Users,
  Lock,
  Store,
  DollarSign,
  Clock3,
  Workflow,
  FolderOpen,
  Container,
  Code2,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { useAuthStore } from '@/stores/auth'

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

  const handleToggle = () => {
    const next = !collapsed
    setCollapsed(next)
    onCollapseChange?.(next)
  }

  const adminNav = [
    { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true as const },
    { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    { path: '/admin/knowledge', labelKey: 'nav.knowledge', icon: BookOpen },
    { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
    { path: '/admin/devbridge', labelKey: 'nav.devbridge', icon: Code2 },
    { path: '/admin/workflows', labelKey: 'nav.workflows', icon: Workflow, badgeKey: 'nav.workflowsBeta' },
    { path: '/admin/workspace', labelKey: 'nav.workspace', icon: Container },
    { path: '/admin/files', labelKey: 'nav.files', icon: FolderOpen },
    { path: '/admin/schedules', labelKey: 'nav.schedules', icon: Clock3 },
    { path: '/admin/agents', labelKey: 'nav.agents', icon: Bot },
    { path: '/admin/customer-agents', labelKey: 'nav.customerAgents', icon: Headphones },
    { path: '/admin/settings', labelKey: 'nav.settings', icon: Settings },
    { path: '/admin/channels', labelKey: 'nav.channels', icon: Globe },
    { path: '/admin/users', labelKey: 'nav.users', icon: Users },
    { path: '/admin/roles', labelKey: 'nav.roles', icon: Lock },
    { path: '/admin/groups', labelKey: 'nav.groups', icon: Users },
    { path: '/admin/templates', labelKey: 'nav.templates', icon: Store },
    { path: '/admin/orders', labelKey: 'nav.orders', icon: DollarSign },
  ]

  const agentNav = [
    { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true as const },
    { path: '/admin/agents', labelKey: 'nav.agents', icon: Bot },
    { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
    { path: '/admin/devbridge', labelKey: 'nav.devbridge', icon: Code2 },
    { path: '/admin/workflows', labelKey: 'nav.workflows', icon: Workflow, badgeKey: 'nav.workflowsBeta' },
    { path: '/admin/workspace', labelKey: 'nav.workspace', icon: Container },
    { path: '/admin/files', labelKey: 'nav.files', icon: FolderOpen },
    { path: '/admin/schedules', labelKey: 'nav.schedules', icon: Clock3 },
    { path: '/admin/customer-agents', labelKey: 'nav.customerAgents', icon: Headphones },
    { path: '/admin/knowledge', labelKey: 'nav.knowledge', icon: BookOpen },
  ]

  const navItems = user?.role === 'admin' ? adminNav : agentNav

  const isActive = (item: (typeof navItems)[number]) => {
    if ('exact' in item && item.exact) return location.pathname === item.path
    return location.pathname.startsWith(item.path)
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
        {collapsed && (
          <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0 cursor-pointer" onClick={() => navigate('/admin')}>
            <MessageCircle className="w-5 h-5 text-white" />
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

      {/* Nav items */}
      <nav className="flex-1 py-4 px-2 overflow-y-auto scrollbar-hide">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.path}>
              <button
                type="button"
                onClick={() => { navigate(item.path); onClose?.() }}
                className={cn(
                  'w-full flex items-center gap-3 rounded-lg text-sm font-medium transition-colors',
                  collapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5',
                  isActive(item)
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700',
                )}
                title={collapsed ? t(item.labelKey) : undefined}
              >
                <item.icon className="w-5 h-5 shrink-0" />
                {!collapsed && (
                  <>
                    <span className="flex-1 text-left truncate">{t(item.labelKey)}</span>
                    {'badgeKey' in item && item.badgeKey ? (
                      <Badge variant="warning" size="sm" className="shrink-0">{t(item.badgeKey)}</Badge>
                    ) : null}
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className={cn('border-t border-gray-200 dark:border-gray-700 space-y-2', collapsed ? 'px-1 py-3' : 'px-3 py-4')}>
        <Link to="/" className={cn(
          'flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
          collapsed ? 'justify-center px-1 py-2' : 'px-3 py-2',
        )} title={t('common.home')}>
          <Home className="w-4 h-4 shrink-0" />
          {!collapsed && <span>{t('common.home')}</span>}
        </Link>
        <a href="/widget/demo" target="_blank" rel="noopener noreferrer" className={cn(
          'flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
          collapsed ? 'justify-center px-1 py-2' : 'px-3 py-2',
        )} title={t('nav.widgetPreview')}>
          <MessageCircle className="w-4 h-4 shrink-0" />
          {!collapsed && <span>{t('nav.widgetPreview')}</span>}
        </a>
      </div>
    </aside>
  )
}
