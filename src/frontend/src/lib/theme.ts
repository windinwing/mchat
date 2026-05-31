export type AppTheme = 'light' | 'dark'

const STORAGE_KEY = 'mchat_theme'

function prefersDark(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function getStoredTheme(): AppTheme | null {
  if (typeof window === 'undefined') return null
  const value = window.localStorage.getItem(STORAGE_KEY)
  return value === 'light' || value === 'dark' ? value : null
}

export function getInitialTheme(): AppTheme {
  return getStoredTheme() ?? (prefersDark() ? 'dark' : 'light')
}

export function applyTheme(theme: AppTheme): void {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

export function setTheme(theme: AppTheme): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, theme)
  }
  applyTheme(theme)
}

export function initTheme(): AppTheme {
  const theme = getInitialTheme()
  applyTheme(theme)
  return theme
}
