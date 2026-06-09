import React from 'react'
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { Badge } from '@/components/ui/Badge'
import { useAuthStore } from '@/stores/auth'

interface SidebarProps {
  onClose?: () => void
}

export function Sidebar({ onClose }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)

  const adminNav = [
    { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true as const },
    { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    { path: '/admin/knowledge', labelKey: 'nav.knowledge', icon: BookOpen },
    { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
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
    { path: '/admin/templates', labelKey: 'nav.templates', icon: Store },
    { path: '/admin/orders', labelKey: 'nav.orders', icon: DollarSign },
  ]

  const agentNav = [
    { path: '/admin', labelKey: 'nav.dashboard', icon: LayoutDashboard, exact: true as const },
    { path: '/admin/agents', labelKey: 'nav.agents', icon: Bot },
    { path: '/admin/conversations', labelKey: 'nav.conversations', icon: MessageSquare },
    { path: '/admin/skills', labelKey: 'nav.skills', icon: Puzzle },
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
    <aside className="h-full bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
      <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 dark:border-gray-700 shrink-0">
        <div
          className="flex items-center gap-2 cursor-pointer"
          onClick={() => navigate('/admin')}
        >
          <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
            <MessageCircle className="w-5 h-5 text-white" />
          </div>
          <span className="text-lg font-bold text-gray-900 dark:text-gray-100">
            MChat
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            title={t('common.close')}
            className="lg:hidden p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      <nav className="flex-1 py-4 px-3 overflow-y-auto">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.path}>
              <button
                type="button"
                onClick={() => {
                  navigate(item.path)
                  onClose?.()
                }}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive(item)
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700',
                )}
              >
                <item.icon className="w-5 h-5 shrink-0" />
                <span className="flex-1 text-left">{t(item.labelKey)}</span>
                {'badgeKey' in item && item.badgeKey ? (
                  <Badge variant="warning" size="sm" className="shrink-0">
                    {t(item.badgeKey)}
                  </Badge>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="px-3 py-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
        <LanguageSwitcher className="w-full justify-center" />
        <Link
          to="/"
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <Home className="w-4 h-4" />
          <span>{t('common.home')}</span>
        </Link>
        <a
          href="/widget/demo"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <MessageCircle className="w-4 h-4" />
          <span>{t('nav.widgetPreview')}</span>
        </a>
      </div>
    </aside>
  )
}
