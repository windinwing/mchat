import React, { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { useAuthStore } from '@/stores/auth'
import { ToastContainer } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'

interface AdminLayoutProps {
  children: React.ReactNode
}

export function AdminLayout({ children }: AdminLayoutProps) {
  const { t } = useTranslation()
  const { isAuthenticated, isLoading, checkAuth, user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/admin/login', { state: { from: location.pathname } })
    }
  }, [isLoading, isAuthenticated, navigate, location.pathname])

  useEffect(() => {
    // Wait until user profile is loaded; otherwise refresh can briefly redirect to /admin.
    if (isLoading || !isAuthenticated || !user || user.role === 'admin') return

    const adminOnlyPrefixes = [
      '/admin/knowledge',
      '/admin/skills',
      '/admin/workflows',
      '/admin/schedules',
      '/admin/agents',
      '/admin/customer-agents',
      '/admin/settings',
      '/admin/channels',
      '/admin/users',
      '/admin/roles',
    ]

    const blocked = adminOnlyPrefixes.some(
      (prefix) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`),
    )

    if (blocked) {
      navigate('/admin', { replace: true })
    }
  }, [isLoading, isAuthenticated, user?.role, location.pathname, navigate])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <Spinner size="lg" />
          <p className="text-sm text-gray-500">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) return null

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out lg:relative lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top header */}
        <header className="h-16 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-4 lg:px-6 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Menu"
            title="Menu"
            className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex-1" />

          <div className="flex items-center gap-3">
            <LanguageSwitcher className="shrink-0" />
            <ThemeToggle className="shrink-0" />
            <div className="px-4 py-1.5 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50/80 dark:bg-gray-900/50 text-sm text-right">
              <p className="font-medium text-gray-900 dark:text-gray-100 leading-tight">
                {user?.display_name || user?.username || t('common.admin')}
              </p>
            </div>
            <button
              onClick={logout}
              className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              {t('common.logout')}
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4 lg:p-6">
          {children}
        </main>
      </div>

      <ToastContainer />
    </div>
  )
}
