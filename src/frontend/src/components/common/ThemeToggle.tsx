import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AppTheme, getInitialTheme, setTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'

interface ThemeToggleProps {
  className?: string
}

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { t } = useTranslation()
  const [theme, setThemeState] = useState<AppTheme>('light')

  useEffect(() => {
    setThemeState(getInitialTheme())
  }, [])

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }

  const isDark = theme === 'dark'
  const label = isDark ? t('common.lightMode') : t('common.darkMode')

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={label}
      aria-label={label}
      className={cn(
        'inline-flex items-center justify-center rounded-full border border-gray-200 dark:border-gray-600 bg-gray-100/80 dark:bg-gray-800/80 p-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-300 transition-colors',
        className,
      )}
    >
      {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  )
}
