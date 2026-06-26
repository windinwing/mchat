import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Send, CheckCircle, XCircle, ExternalLink, Filter, BarChart3,
} from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { Dialog } from '@/components/ui/Dialog'
import { formatDate } from '@/lib/utils'

interface SendRecord {
  id: string
  provider: string
  user_id?: string
  title: string | null
  content_preview: string | null
  success: boolean
  remote_url: string | null
  error_message: string | null
  status: string
  media_type: string
  created_at: string | null
  sent_at: string | null
}

interface SendStats {
  days: number
  total: number
  success: number
  failed: number
  success_rate: number
  by_provider: Record<string, { total: number; success: number }>
}

const PROVIDER_LABELS: Record<string, string> = {
  feishu: '飞书', dingtalk: '钉钉', wecom: '企业微信', wechat_mp: '公众号',
  slack: 'Slack', discord: 'Discord', telegram_channel: 'Telegram',
  twitter_x: 'X/Twitter', facebook: 'Facebook', linkedin: 'LinkedIn',
  playwright_client: '客户机(小红书/抖音)',
}

export function SendRecordsAdminPage() {
  const { t } = useTranslation()
  const [records, setRecords] = useState<SendRecord[]>([])
  const [stats, setStats] = useState<SendStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [providerFilter, setProviderFilter] = useState('')
  const [days, setDays] = useState('7')
  const [detail, setDetail] = useState<SendRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const openDetail = async (record: SendRecord) => {
    setDetail(record)
    setDetailOpen(true)
    try {
      const full = await api.get<SendRecord>(`/portal/send-records/${record.id}`)
      if (full) setDetail(full)
    } catch { /* keep the list-level data */ }
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = { limit: '200' }
      if (providerFilter) params.provider = providerFilter
      // Admin endpoint — reuse the publish records via admin API
      const [recordsData, statsData] = await Promise.all([
        api.get<SendRecord[]>('/portal/send-records', params),
        api.get<SendStats>('/portal/send-records/stats', { days }),
      ])
      setRecords(recordsData || [])
      setStats(statsData)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [providerFilter, days])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('sendRecords.adminTitle', '发送汇总')}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t('sendRecords.adminSubtitle', '全平台发布记录与统计')}
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent className="p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm"><Send className="w-4 h-4" /> {t('sendRecords.total', '总发送')}</div>
            <div className="text-2xl font-bold mt-1">{stats.total}</div>
          </CardContent></Card>
          <Card><CardContent className="p-4">
            <div className="flex items-center gap-2 text-green-600 text-sm"><CheckCircle className="w-4 h-4" /> {t('sendRecords.success', '成功')}</div>
            <div className="text-2xl font-bold mt-1 text-green-600">{stats.success}</div>
          </CardContent></Card>
          <Card><CardContent className="p-4">
            <div className="flex items-center gap-2 text-red-600 text-sm"><XCircle className="w-4 h-4" /> {t('sendRecords.failed', '失败')}</div>
            <div className="text-2xl font-bold mt-1 text-red-600">{stats.failed}</div>
          </CardContent></Card>
          <Card><CardContent className="p-4">
            <div className="flex items-center gap-2 text-blue-600 text-sm"><BarChart3 className="w-4 h-4" /> {t('sendRecords.successRate', '成功率')}</div>
            <div className="text-2xl font-bold mt-1 text-blue-600">{stats.success_rate}%</div>
          </CardContent></Card>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <Select
          value={providerFilter}
          onChange={(e) => setProviderFilter((e.target as HTMLSelectElement).value)}
          options={[
            { value: '', label: t('sendRecords.allProviders', '全部渠道') },
            ...Object.entries(PROVIDER_LABELS).map(([v, l]) => ({ value: v, label: l })),
          ]}
        />
        <Select
          value={days}
          onChange={(e) => setDays((e.target as HTMLSelectElement).value)}
          options={[
            { value: '1', label: t('sendRecords.lastDay', '近1天') },
            { value: '7', label: t('sendRecords.last7Days', '近7天') },
            { value: '30', label: t('sendRecords.last30Days', '近30天') },
            { value: '90', label: t('sendRecords.last90Days', '近90天') },
          ]}
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : records.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-gray-500">
          {t('sendRecords.empty', '暂无发送记录')}
        </CardContent></Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 pr-4 text-left font-medium text-gray-500">{t('sendRecords.colStatus', '状态')}</th>
                  <th className="py-2 pr-4 text-left font-medium text-gray-500">{t('sendRecords.colProvider', '渠道')}</th>
                  <th className="py-2 pr-4 text-left font-medium text-gray-500">{t('sendRecords.colContent', '内容')}</th>
                  <th className="py-2 pr-4 text-left font-medium text-gray-500">{t('sendRecords.colTime', '时间')}</th>
                  <th className="py-2 pr-4 text-left font-medium text-gray-500">{t('sendRecords.colLink', '链接')}</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id} className="border-b border-gray-100 dark:border-gray-800 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50" onClick={() => openDetail(r)}>
                    <td className="py-2 pr-4">
                      {r.success ? (
                        <Badge variant="success"><CheckCircle className="w-3 h-3 inline mr-1" />{t('common.success', '成功')}</Badge>
                      ) : (
                        <Badge variant="danger"><XCircle className="w-3 h-3 inline mr-1" />{t('common.failed', '失败')}</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{PROVIDER_LABELS[r.provider] || r.provider}</td>
                    <td className="py-2 pr-4 max-w-xs truncate" title={r.title || r.error_message || ''}>
                      {r.success ? (r.title || r.content_preview || '-') : (
                        <span className="text-red-500">{r.error_message || '-'}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap text-gray-500">{r.sent_at ? formatDate(r.sent_at) : formatDate(r.created_at || '')}</td>
                    <td className="py-2 pr-4">
                      {r.remote_url ? (
                        <a href={r.remote_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline inline-flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" /> {t('sendRecords.view', '查看')}
                        </a>
                      ) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {stats && Object.keys(stats.by_provider).length > 0 && (
        <Card><CardContent className="p-4">
          <h3 className="font-medium mb-3">{t('sendRecords.byProvider', '按渠道统计')}</h3>
          <div className="space-y-2">
            {Object.entries(stats.by_provider).map(([prov, data]) => (
              <div key={prov} className="flex items-center justify-between">
                <span className="text-sm">{PROVIDER_LABELS[prov] || prov}</span>
                <div className="flex items-center gap-3">
                  <div className="w-32 bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                    <div className="bg-green-500 h-full" style={{ width: `${data.total > 0 ? (data.success / data.total * 100) : 0}%` }} />
                  </div>
                  <span className="text-sm text-gray-500 w-20 text-right">{data.success}/{data.total}</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent></Card>
      )}

      {/* Detail dialog */}
      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} title={t('sendRecords.detailTitle', '发送详情')} size="md">
        {detail && (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2">
              {detail.success ? (
                <Badge variant="success"><CheckCircle className="w-3 h-3 inline mr-1" />{t('common.success', '成功')}</Badge>
              ) : (
                <Badge variant="danger"><XCircle className="w-3 h-3 inline mr-1" />{t('common.failed', '失败')}</Badge>
              )}
              <span className="text-gray-500">{PROVIDER_LABELS[detail.provider] || detail.provider}</span>
              <span className="text-gray-400">· {detail.media_type}</span>
            </div>
            {detail.title && (
              <div>
                <span className="text-gray-500">{t('sendRecords.colContent', '标题')}:</span>
                <p className="font-medium mt-0.5">{detail.title}</p>
              </div>
            )}
            {detail.content_preview && (
              <div>
                <span className="text-gray-500">{t('sendRecords.detailContent', '正文')}:</span>
                <p className="mt-0.5 whitespace-pre-wrap bg-gray-50 dark:bg-gray-800 rounded p-2 max-h-40 overflow-y-auto">{detail.content_preview}</p>
              </div>
            )}
            {detail.error_message && (
              <div>
                <span className="text-red-500">{t('sendRecords.detailError', '错误信息')}:</span>
                <p className="mt-0.5 text-red-600 bg-red-50 dark:bg-red-900/20 rounded p-2">{detail.error_message}</p>
              </div>
            )}
            {detail.remote_url && (
              <div>
                <span className="text-gray-500">{t('sendRecords.colLink', '链接')}:</span>
                <a href={detail.remote_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline inline-flex items-center gap-1 mt-0.5">
                  <ExternalLink className="w-3 h-3" /> {detail.remote_url}
                </a>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
              <div><span className="text-gray-500">{t('sendRecords.colTime', '时间')}:</span> <span>{detail.sent_at ? formatDate(detail.sent_at) : formatDate(detail.created_at || '')}</span></div>
              <div><span className="text-gray-500">{t('sendRecords.detailStatus', '状态')}:</span> <span>{detail.status}</span></div>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  )
}
