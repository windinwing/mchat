import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, Workflow } from 'lucide-react'
import { landingScreenshot, type LandingPreviewCard } from '@/lib/landingImages'

type Props = {
  cards: readonly LandingPreviewCard[]
  locale: string
  labelPrefix?: 'landing' | 'landingCloud'
  showWorkflowHighlight?: boolean
}

export function LandingPreviewCarousel({
  cards,
  locale,
  labelPrefix = 'landing',
  showWorkflowHighlight = false,
}: Props) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const count = cards.length

  const go = useCallback(
    (next: number) => {
      setIndex(((next % count) + count) % count)
    },
    [count],
  )

  useEffect(() => {
    if (count <= 1) return
    const id = window.setInterval(() => go(index + 1), 5000)
    return () => window.clearInterval(id)
  }, [count, go, index])

  if (count === 0) return null

  const current = cards[index]

  return (
    <div className="space-y-4">
      <div className="relative rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden bg-white dark:bg-gray-900 shadow-lg">
        <div
          className="flex transition-transform duration-500 ease-out"
          style={{ transform: `translateX(-${index * 100}%)` }}
        >
          {cards.map(({ key, image, highlight }) => (
            <figure key={key} className="min-w-full shrink-0">
              <div className="relative">
                <img
                  src={landingScreenshot(image, locale)}
                  alt={t(`${labelPrefix}.${key}`)}
                  className="w-full h-auto max-h-[420px] object-cover object-top bg-gray-50 dark:bg-gray-800"
                  loading="lazy"
                />
                {highlight && (
                  <span className="absolute top-3 left-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary-600 text-white text-xs font-medium shadow-md">
                    <Workflow className="w-3.5 h-3.5" />
                    {t('landingCloud.previewWorkflowBadge')}
                  </span>
                )}
              </div>
              <figcaption className="px-4 py-3 text-sm font-medium text-gray-800 dark:text-gray-200 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-3">
                <span>{t(`${labelPrefix}.${key}`)}</span>
                <span className="text-xs text-gray-400 tabular-nums">
                  {cards.findIndex((c) => c.key === key) + 1}/{count}
                </span>
              </figcaption>
            </figure>
          ))}
        </div>

        {count > 1 && (
          <>
            <button
              type="button"
              onClick={() => go(index - 1)}
              className="absolute left-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/90 dark:bg-gray-900/90 border border-gray-200 dark:border-gray-600 shadow flex items-center justify-center text-gray-600 hover:text-primary-600 transition-colors"
              aria-label={t('landingCloud.carouselPrev')}
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={() => go(index + 1)}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/90 dark:bg-gray-900/90 border border-gray-200 dark:border-gray-600 shadow flex items-center justify-center text-gray-600 hover:text-primary-600 transition-colors"
              aria-label={t('landingCloud.carouselNext')}
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </>
        )}
      </div>

      {count > 1 && (
        <div className="flex justify-center gap-2">
          {cards.map((card, i) => (
            <button
              key={card.key}
              type="button"
              onClick={() => setIndex(i)}
              className={`h-2 rounded-full transition-all ${
                i === index
                  ? 'w-6 bg-primary-600'
                  : 'w-2 bg-gray-300 dark:bg-gray-600 hover:bg-primary-400'
              }`}
              aria-label={t(`${labelPrefix}.${card.key}`)}
            />
          ))}
        </div>
      )}

      {current?.highlight && showWorkflowHighlight && (
        <p className="text-center text-sm text-primary-700 dark:text-primary-300 font-medium">
          {t('landingCloud.previewWorkflowCaption')}
        </p>
      )}
    </div>
  )
}
