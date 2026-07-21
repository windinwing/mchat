import { useMemo } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

interface PaginationProps {
  /** Current page (1-based). */
  page: number
  /** Total item count across all pages. */
  total: number
  /** Items per page. */
  pageSize: number
  /** Called with the new 1-based page number. */
  onPageChange: (page: number) => void
  /** Optional page-size selector. When provided, renders a <select>. */
  onPageSizeChange?: (size: number) => void
  pageSizeOptions?: number[]
  className?: string
}

/**
 * Lightweight pagination control: prev / page numbers / next, plus an optional
 * page-size selector and a "总数 N" hint. Page numbers are windowed so very
 * large totals don't render hundreds of buttons.
 */
export function Pagination({
  page,
  total,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50],
  className,
}: PaginationProps) {
  const { t } = useTranslation()
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // Windowed page list: show up to 5 numbers around the current page.
  const pages = useMemo(() => {
    const out: number[] = []
    const start = Math.max(1, page - 2)
    const end = Math.min(totalPages, start + 4)
    for (let p = Math.max(1, end - 4); p <= end; p++) out.push(p)
    return out
  }, [page, totalPages])

  if (total === 0) return null

  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)

  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-3 px-6 py-3 text-sm', className)}>
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {t('common.paginationRange', { from, to, total, defaultValue: `${from}-${to} / ${total}` })}
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          aria-label={t('common.prevPage', { defaultValue: '上一页' })}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        {pages[0] > 1 && (
          <>
            <PageButton n={1} active={page === 1} onClick={onPageChange} />
            {pages[0] > 2 && <span className="px-1 text-gray-400">…</span>}
          </>
        )}
        {pages.map((p) => (
          <PageButton key={p} n={p} active={page === p} onClick={onPageChange} />
        ))}
        {pages[pages.length - 1] < totalPages && (
          <>
            {pages[pages.length - 1] < totalPages - 1 && <span className="px-1 text-gray-400">…</span>}
            <PageButton n={totalPages} active={page === totalPages} onClick={onPageChange} />
          </>
        )}
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          aria-label={t('common.nextPage', { defaultValue: '下一页' })}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        {onPageSizeChange && (
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="ml-2 h-8 rounded-md border border-gray-200 bg-white px-2 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
            aria-label={t('common.pageSize', { defaultValue: '每页条数' })}
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>
                {n}/{t('common.page', { defaultValue: '页' })}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  )
}

function PageButton({ n, active, onClick }: { n: number; active: boolean; onClick: (n: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onClick(n)}
      className={cn(
        'inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border px-2 text-xs font-medium transition-colors',
        active
          ? 'border-primary-600 bg-primary-600 text-white'
          : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800',
      )}
    >
      {n}
    </button>
  )
}
