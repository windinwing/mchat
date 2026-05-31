import { useEffect, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  ShoppingBag,
  Receipt,
  MessageSquare,
  LogOut,
  Menu,
  X,
  Settings,
} from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { Spinner } from '@/components/ui/Spinner'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { useState } from 'react'

const navItems = [
  { path: '/portal/dashboard', label: 'portal.dashboard', icon: LayoutDashboard },
  { path: '/portal/templates', label: 'portal.templates', icon: ShoppingBag },
  { path: '/portal/channels', label: 'portal.myChannels', icon: MessageSquare },
  { path: '/portal/orders', label: 'portal.orders', icon: Receipt },
  { path: '/portal/account', label: 'portal.account', icon: Settings },
]

export function UserLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { user, isAuthenticated, isLoading, checkAuth, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
      <div className="flex items-center justify-center min-h-screen">
        <Spinner size="lg" />
      </div>
    )
  }

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Mobile header */}
      <div className="lg:hidden flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-1 text-gray-500"
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
              <button onClick={() => setSidebarOpen(false)} className="p-1 text-gray-500">
                <X className="w-5 h-5" />
              </button>
            </div>
            <SidebarContent
              t={t}
              user={user}
              isActive={isActive}
              onNav={() => setSidebarOpen(false)}
              onLogout={() => { logout(); navigate('/register') }}
            />
          </div>
        </div>
      )}

      <div className="flex">
        {/* Desktop sidebar */}
        <aside className="hidden lg:flex flex-col w-64 min-h-screen bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 p-4">
          <div className="mb-6 px-2">
            <Link to="/portal" className="text-xl font-bold text-gray-900 dark:text-gray-100">
              MChat
            </Link>
          </div>
          <SidebarContent
            t={t}
            user={user}
            isActive={isActive}
            onNav={() => {}}
            onLogout={() => { logout(); navigate('/register') }}
          />
        </aside>

        {/* Main content */}
        <main className="flex-1 min-h-screen p-4 lg:p-6 text-gray-900 dark:text-gray-200">
          {children}
        </main>
      </div>
    </div>
  )
}

function SidebarContent({
  t,
  user,
  isActive,
  onNav,
  onLogout,
}: {
  t: (key: string) => string
  user: any
  isActive: (path: string) => boolean
  onNav: () => void
  onLogout: () => void
}) {
  return (
    <>
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            onClick={onNav}
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
          <Settings className="w-4 h-4" />
          {user?.display_name || user?.username}
        </div>
        <div className="px-3 pb-2">
          <ThemeToggle className="w-full rounded-lg" />
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 w-full transition-colors mt-1"
        >
          <LogOut className="w-4 h-4" />
          {t('common.logout')}
        </button>
      </div>
    </>
  )
}
