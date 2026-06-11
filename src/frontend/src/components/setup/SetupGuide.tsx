import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Bot, CheckCircle2, Circle, Headphones, MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { SetupStatus } from '@/lib/setupStatus'

type SetupGuideVariant = 'staff' | 'portal'

interface SetupGuideProps {
  status: SetupStatus
  variant?: SetupGuideVariant
  compact?: boolean
  className?: string
}

export function SetupGuide({
  status,
  variant = 'staff',
  compact = false,
  className,
}: SetupGuideProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const aiPath = variant === 'portal' ? '/portal/account' : '/admin/agents'
  const assistantPath =
    variant === 'portal' ? '/portal/templates' : '/admin/customer-agents'

  const steps = [
    {
      id: 'ai',
      done: status.ai_ready,
      icon: Bot,
      title: t('setup.stepAiTitle'),
      hint: t('setup.stepAiHint'),
      action: t('setup.stepAiAction'),
      path: aiPath,
    },
    {
      id: 'assistant',
      done: status.has_assistant,
      icon: Headphones,
      title: t('setup.stepAssistantTitle'),
      hint: t('setup.stepAssistantHint'),
      action: t('setup.stepAssistantAction'),
      path: assistantPath,
      optionalUntilAi: true,
    },
    {
      id: 'chat',
      done: status.ai_ready && status.has_assistant,
      icon: MessageSquare,
      title: t('setup.stepChatTitle'),
      hint: t('setup.stepChatHint'),
      action: t('setup.stepChatAction'),
      path: '/chat',
    },
  ]

  const envHint =
    !status.ai_ready &&
    status.env_key_providers.length > 0 &&
    t('setup.envKeyHint', {
      providers: status.env_key_providers.join(', '),
    })

  return (
    <div
      className={cn(
        'rounded-2xl border border-primary-200 dark:border-primary-800/60 bg-white dark:bg-gray-800 shadow-sm',
        compact ? 'p-4' : 'p-6 max-w-lg w-full',
        className,
      )}
    >
      {!compact && (
        <div className="mb-5">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('setup.title')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('setup.subtitle')}
          </p>
        </div>
      )}

      {compact && (
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
          {t('setup.bannerTitle')}
        </p>
      )}

      <ol className="space-y-3">
        {steps.map((step, index) => {
          const Icon = step.icon
          const locked = step.optionalUntilAi && !status.ai_ready
          const active = !step.done && !locked && (index === 0 || steps[index - 1]?.done)
          return (
            <li
              key={step.id}
              className={cn(
                'flex gap-3 rounded-xl border p-3 transition-colors',
                step.done
                  ? 'border-green-200 dark:border-green-900/50 bg-green-50/50 dark:bg-green-950/20'
                  : active
                    ? 'border-primary-200 dark:border-primary-800 bg-primary-50/40 dark:bg-primary-950/20'
                    : 'border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/30',
                locked && 'opacity-60',
              )}
            >
              <div className="shrink-0 pt-0.5">
                {step.done ? (
                  <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                ) : (
                  <Circle className="w-5 h-5 text-gray-300 dark:text-gray-600" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-gray-500 dark:text-gray-400 shrink-0" />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {step.title}
                  </span>
                </div>
                {!compact && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
                    {step.hint}
                  </p>
                )}
                {!step.done && !locked && (
                  <Button
                    size="sm"
                    variant={active ? 'primary' : 'outline'}
                    className="mt-2"
                    onClick={() => navigate(step.path)}
                  >
                    {step.action}
                  </Button>
                )}
              </div>
            </li>
          )
        })}
      </ol>

      {envHint && (
        <p className="text-xs text-amber-700 dark:text-amber-300/90 mt-4 leading-relaxed rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 px-3 py-2">
          {envHint}
        </p>
      )}
    </div>
  )
}
