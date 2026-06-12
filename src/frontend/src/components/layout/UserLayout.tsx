import { useEffect, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  ShoppingBag,
  Receipt,
  MessageSquare,
  Users,
  LogOut,
  Menu,
  X,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Workflow,
  Clock3,
  LayoutTemplate,
} from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { Avatar } from '@/components/ui/Avatar'
import { Spinner } from '@/components/ui/Spinner'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { AppModeSwitch } from '@/components/common/AppModeSwitch'
import { SiteCopyrightFooter } from '@/components/common/SiteCopyrightFooter'
import { useState } from 'react'

const navItems = [
  { path: '/portal/dashboard', label: 'portal.dashboard', icon: LayoutDashboard },
  { path: '/portal/templates', label: 'portal.templates', icon: ShoppingBag },
  { path: '/portal/channels', label: 'portal.myChannels', icon: MessageSquare },
  { path: '/portal/workflows', label: 'portal.workflowsNav', icon: Workflow },
  { path: '/portal/workflow-center', label: 'portal.workflowCenterNav', icon: LayoutTemplate },
  { path: '/portal/schedules', label: 'portal.schedulesNav', icon: Clock3 },
  { path: '/portal/groups', label: 'portal.groups', icon: Users },
  { path: '/portal/orders', label: 'portal.orders', icon: Receipt },
  { path: '/portal/account', label: 'portal.account', icon: Settings },
]

export function UserLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { user, isAuthenticated, isLoading, checkAuth, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    checkAuth()
  }, [])

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/register', { replace: true })
    }
  }, [isAuthenticated, isLoading, navigate])

  if (isLoading || !isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spinner size="lg" />
      </div>
    )
  }

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <div className="h-screen overflow-hidden bg-gray-50 dark:bg-gray-900">
      {/* Mobile header */}
      <div className="lg:hidden flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-1 text-gray-500"
          aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
          title={sidebarOpen ? 'Close menu' : 'Open menu'}
        >
          <Menu className="w-5 h-5" />
        </button>
        <span className="font-semibold text-gray-900 dark:text-gray-100">
          MChat
        </span>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-64 bg-white dark:bg-gray-800 shadow-xl p-4">
            <div className="flex items-center justify-between mb-6">
              <span className="font-bold text-lg text-gray-900 dark:text-gray-100">MChat</span>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-1 text-gray-500"
                aria-label="Close menu"
                title="Close menu"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive(item.path)
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
                      : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  {t(item.label)}
                </Link>
              ))}
            </nav>
            <div className="mt-auto pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                <Avatar
                  src={user?.avatar_url || undefined}
                  name={user?.display_name || user?.username || 'User'}
                  size="sm"
                />
                <span className="truncate">{user?.display_name || user?.username}</span>
              </div>
              <div className="px-3 pb-2">
                <ThemeToggle className="w-full rounded-lg" />
              </div>
              <button
                onClick={() => { logout(); navigate('/register') }}
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 w-full transition-colors mt-1"
              >
                <LogOut className="w-4 h-4" />
                {t('common.logout')}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex h-full">
        {/* Desktop sidebar */}
        <aside className={`hidden lg:flex flex-col h-full bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transition-all duration-200 ${sidebarCollapsed ? 'w-16 p-2' : 'w-64 p-4'}`}>
          <div className={`flex items-center mb-6 ${sidebarCollapsed ? 'justify-center px-0' : 'justify-between px-2'}`}>
            {!sidebarCollapsed && (
              <Link to="/portal" className="text-xl font-bold text-gray-900 dark:text-gray-100">
                MChat
              </Link>
            )}
            {sidebarCollapsed && (
              <Link to="/portal" className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold text-sm">
                M
              </Link>
            )}
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              title={sidebarCollapsed ? 'Expand' : 'Collapse'}
            >
              {sidebarCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
            </button>
          </div>
          <nav className="flex-1 space-y-1 overflow-y-auto scrollbar-hide">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => {}}
                className={`flex items-center rounded-lg text-sm transition-colors ${
                  sidebarCollapsed ? 'justify-center px-2 py-2.5' : 'gap-3 px-3 py-2'
                } ${
                  isActive(item.path)
                    ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
                title={sidebarCollapsed ? t(item.label) : undefined}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                {!sidebarCollapsed && <span>{t(item.label)}</span>}
              </Link>
            ))}
          </nav>

          <div className="mt-auto pt-4 border-t border-gray-200 dark:border-gray-700">
            {!sidebarCollapsed && (
              <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                <Avatar
                  src={user?.avatar_url || undefined}
                  name={user?.display_name || user?.username || 'User'}
                  size="sm"
                />
                <span className="truncate">{user?.display_name || user?.username}</span>
              </div>
            )}
            <div className="px-3 pb-2">
              <ThemeToggle className={`w-full rounded-lg ${sidebarCollapsed ? 'p-1' : ''}`} />
            </div>
            <button
              onClick={() => { logout(); navigate('/register') }}
              className={`flex items-center rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 w-full transition-colors mt-1 ${
                sidebarCollapsed ? 'justify-center px-2 py-2' : 'gap-3 px-3 py-2'
              }`}
              title={sidebarCollapsed ? t('common.logout') : undefined}
            >
              <LogOut className="w-4 h-4 shrink-0" />
              {!sidebarCollapsed && <span>{t('common.logout')}</span>}
            </button>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 h-full flex flex-col overflow-hidden text-gray-900 dark:text-gray-200">
          <div className="hidden lg:flex items-center gap-3 px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <AppModeSwitch variant="portal" active="portal" />
          </div>
          <div className="flex-1 overflow-y-auto p-4 lg:p-6">
            {children}
            <SiteCopyrightFooter className="mt-8 pt-4 border-t border-gray-200 dark:border-gray-700 text-center" />
          </div>
        </main>
      </div>
    </div>
  )
}


