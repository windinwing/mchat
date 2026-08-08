import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { automationCheckoutPath, type AutomationLimitDetail } from '@/lib/automationLimit'

interface Props {
  /** 当前 402 权益详情；为 null 时不显示。 */
  limit: AutomationLimitDetail | null
  /** 关闭弹窗（清空 limit）。 */
  onClose: () => void
  /** 是否在 portal（决定是否提供"前往开通"跳转）。 */
  isPortal?: boolean
  /** 自定义跳转目标（覆盖 automationCheckoutPath 的默认计算）。 */
  checkoutPath?: string
}

/**
 * 权益不足确认弹窗：显示友好提示 + 「前往开通」/「取消」按钮。
 * 用户点「前往开通」才跳转，避免无声跳走或 toast 被忽略。
 */
export function EntitlementConfirmDialog({ limit, onClose, isPortal, checkoutPath }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  if (!limit) return null

  // 优先用 message_key（i18n），兜底用后端 message
  const message =
    (limit.message_key && t(limit.message_key, { defaultValue: '' })) || limit.message || ''

  const target = checkoutPath ?? automationCheckoutPath(limit)

  const handleUpgrade = () => {
    onClose()
    if (isPortal) navigate(target)
  }

  return (
    <Dialog open={!!limit} onClose={onClose} title={t('workflowEntitlement.dialogTitle', { defaultValue: '权益不足' })} size="sm">
      <div className="space-y-4">
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel', { defaultValue: '取消' })}
          </Button>
          {isPortal ? (
            <Button onClick={handleUpgrade}>
              {t('workflowEntitlement.goUpgrade', { defaultValue: '前往开通' })}
            </Button>
          ) : null}
        </div>
      </div>
    </Dialog>
  )
}
