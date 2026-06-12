import { isCloudEdition } from '@/lib/edition'

const ICP_URL = 'https://beian.miit.gov.cn/'
const ICP_NO = '沪ICP备09049145号-13'

export function SiteCopyrightFooter({ className = '' }: { className?: string }) {
  if (!isCloudEdition) return null

  return (
    <p className={`text-xs text-gray-400 dark:text-gray-500 ${className}`.trim()}>
      © 2025 上海笑溢网络科技有限公司. 版权所有{' '}
      <a
        href={ICP_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
      >
        {ICP_NO}
      </a>
    </p>
  )
}
