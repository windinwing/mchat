import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, RefreshCw } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate } from '@/lib/utils'

export interface SkillCacheEntry {
  skill_id: string
  name: string
  db_path?: string | null
  canonical_path?: string | null
  prompt_body_stale: boolean
  path_stale: boolean
  disk_missing: boolean
  cached_chars: number
  disk_chars: number
  disk_modified_at?: string | null
}

interface Props {
  open: boolean
  onClose: () => void
  onRefreshed?: () => void
}

function isStale(entry: SkillCacheEntry): boolean {
  return entry.prompt_body_stale || entry.path_stale || entry.disk_missing
}

export function SkillCachePanel({ open, onClose, onRefreshed }: Props) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [items, setItems] = useState<SkillCacheEntry[]>([])
  const [staleCount, setStaleCount] = useState(0)

  const loadStatus = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<{ items: SkillCacheEntry[]; stale_count: number }>(
        '/skills/cache-status',
      )
      setItems(data.items || [])
      setStaleCount(data.stale_count ?? 0)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      toast(t('skills.cacheLoadFailed'), { type: 'error', message })
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (open) void loadStatus()
  }, [open, loadStatus])

  const refreshOne = async (skillId: string) => {
    setRefreshingId(skillId)
    try {
      await api.post(`/skills/${skillId}/refresh-cache`)
      toast(t('skills.cacheRefreshOneDone'), { type: 'success' })
      await loadStatus()
      onRefreshed?.()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      toast(t('skills.cacheRefreshFailed'), { type: 'error', message })
    } finally {
      setRefreshingId(null)
    }
  }

  const refreshAllStale = async () => {
    setRefreshingAll(true)
    try {
      const res = await api.post<{ refreshed: number; message: string }>(
        '/skills/cache/refresh-stale',
      )
      toast(res.message || t('skills.cacheRefreshAllDone', { count: res.refreshed }), {
        type: 'success',
      })
      await loadStatus()
      onRefreshed?.()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      toast(t('skills.cacheRefreshFailed'), { type: 'error', message })
    } finally {
      setRefreshingAll(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('skills.cacheDialogTitle')} size="lg">
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('skills.cacheHint')}</p>
      {loading ? (
        <div className="flex justify-center py-10">
          <Spinner size="md" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-center text-gray-400 py-8">{t('skills.emptySkills')}</p>
      ) : (
        <div className="max-h-[420px] overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/80 sticky top-0">
              <tr>
                <th className="text-left py-2 px-3 font-medium">{t('skills.cacheColSkill')}</th>
                <th className="text-left py-2 px-3 font-medium">{t('skills.cacheColStatus')}</th>
                <th className="text-left py-2 px-3 font-medium hidden md:table-cell">
                  {t('skills.cacheColPath')}
                </th>
                <th className="text-right py-2 px-3 font-medium">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {items.map((entry) => (
                <tr key={entry.skill_id} className="align-top">
                  <td className="py-2 px-3 font-medium text-gray-900 dark:text-gray-100">
                    {entry.name}
                  </td>
                  <td className="py-2 px-3">
                    <div className="flex flex-wrap gap-1">
                      {!isStale(entry) && (
                        <Badge variant="success" size="sm">
                          {t('skills.cacheSynced')}
                        </Badge>
                      )}
                      {entry.prompt_body_stale && (
                        <Badge variant="warning" size="sm">
                          {t('skills.cacheStaleBody')}
                        </Badge>
                      )}
                      {entry.path_stale && (
                        <Badge variant="warning" size="sm">
                          {t('skills.cacheStalePath')}
                        </Badge>
                      )}
                      {entry.disk_missing && (
                        <Badge variant="default" size="sm">
                          {t('skills.cacheDiskMissing')}
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      {t('skills.cacheChars', {
                        cached: entry.cached_chars,
                        disk: entry.disk_chars,
                      })}
                      {entry.disk_modified_at
                        ? ` · ${formatDate(entry.disk_modified_at)}`
                        : ''}
                    </div>
                  </td>
                  <td className="py-2 px-3 hidden md:table-cell text-xs text-gray-500 dark:text-gray-400 max-w-[220px] truncate">
                    {entry.canonical_path || entry.db_path || '—'}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={entry.disk_missing || refreshingId === entry.skill_id}
                      isLoading={refreshingId === entry.skill_id}
                      onClick={() => void refreshOne(entry.skill_id)}
                    >
                      {t('skills.cacheRefreshOne')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {t('skills.cacheStaleSummary', { count: staleCount })}
        </span>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => void loadStatus()} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-1" />
            {t('common.refresh')}
          </Button>
          <Button
            size="sm"
            disabled={staleCount === 0 || refreshingAll}
            isLoading={refreshingAll}
            onClick={() => void refreshAllStale()}
          >
            <Database className="w-4 h-4 mr-1" />
            {t('skills.cacheRefreshAllStale')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
