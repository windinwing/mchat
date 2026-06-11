import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { setPreferredStaffMode } from '@/lib/appPreferences'

type AgentMode = 'chat' | 'admin'
type PortalMode = 'chat' | 'portal'

interface AgentSwitchProps {
  variant: 'agent'
  active: AgentMode
}

interface PortalSwitchProps {
  variant: 'portal'
  active: PortalMode
}

type AppModeSwitchProps = AgentSwitchProps | PortalSwitchProps

export function AppModeSwitch(props: AppModeSwitchProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const items =
    props.variant === 'agent'
      ? [
          { id: 'chat' as const, label: t('modeSwitch.chat'), path: '/chat' },
          { id: 'admin' as const, label: t('modeSwitch.admin'), path: '/admin' },
        ]
      : [
          { id: 'chat' as const, label: t('modeSwitch.chat'), path: '/chat' },
          { id: 'portal' as const, label: t('modeSwitch.portal'), path: '/portal/dashboard' },
        ]

  const active = props.active

  return (
    <div
      className="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-100/80 dark:bg-gray-900/50 p-0.5 shrink-0"
      aria-label={t('modeSwitch.label')}
    >
      {items.map((item) => {
        const isActive = item.id === active
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              if (props.variant === 'agent' && (item.id === 'chat' || item.id === 'admin')) {
                setPreferredStaffMode(item.id)
              }
              if (!isActive) navigate(item.path)
            }}
            className={cn(
              'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
              isActive
                ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200',
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
