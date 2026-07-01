import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Send, CheckCircle, XCircle, ExternalLink, Filter, BarChart3,
} from 'lucide-react'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { formatDate } from '@/lib/utils'

interface SendRecord {
  id: string
  provider: string
  channel_id: string | null
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
  feishu: '飞书',
  dingtalk: '钉钉',
  wecom: '企业微信',
  slack: 'Slack',
  discord: 'Discord',
  telegram_channel: 'Telegram',
  playwright_client: '客户机',
}

export function SendRecordsPage() {
  const { t } = useTranslation()
  const [records, setRecords] = useState<SendRecord[]>([])
  const [stats, setStats] = useState<SendStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [providerFilter, setProviderFilter] = useState('')
  const [successFilter, setSuccessFilter] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = { limit: '100' }
      if (providerFilter) params.provider = providerFilter
      if (successFilter === 'success') params.success = 'true'
      if (successFilter === 'failed') params.success = 'false'
      const [recordsData, statsData] = await Promise.all([
        api.get<SendRecord[]>('/portal/send-records', params),
        api.get<SendStats>('/portal/send-records/stats', { days: '7' }),
      ])
      setRecords(recordsData || [])
      setStats(statsData)
    } catch (e: any) {
      toast(t('sendRecords.loadFailed', '加载失败'), { type: 'error', message: e?.message })
    } finally {
      setLoading(false)
    }
  }, [providerFilter, successFilter, t])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('sendRecords.pageTitle', '发送记录')}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t('sendRecords.pageSubtitle', '查看所有发布记录与统计')}
        </p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-gray-500 text-sm">
                <Send className="w-4 h-4" /> {t('sendRecords.total', '总发送')}
              </div>
              <div className="text-2xl font-bold mt-1">{stats.total}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-green-600 text-sm">
                <CheckCircle className="w-4 h-4" /> {t('sendRecords.success', '成功')}
              </div>
              <div className="text-2xl font-bold mt-1 text-green-600">{stats.success}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-red-600 text-sm">
                <XCircle className="w-4 h-4" /> {t('sendRecords.failed', '失败')}
              </div>
              <div className="text-2xl font-bold mt-1 text-red-600">{stats.failed}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-blue-600 text-sm">
                <BarChart3 className="w-4 h-4" /> {t('sendRecords.successRate', '成功率')}
              </div>
              <div className="text-2xl font-bold mt-1 text-blue-600">{stats.success_rate}%</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
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
          value={successFilter}
          onChange={(e) => setSuccessFilter((e.target as HTMLSelectElement).value)}
          options={[
            { value: '', label: t('sendRecords.allStatus', '全部状态') },
            { value: 'success', label: t('sendRecords.success', '成功') },
            { value: 'failed', label: t('sendRecords.failed', '失败') },
          ]}
        />
      </div>

      {/* Records list */}
      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : records.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            {t('sendRecords.empty', '暂无发送记录')}
          </CardContent>
        </Card>
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
                  <tr key={r.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 pr-4">
                      {r.success ? (
                        <Badge variant="success"><CheckCircle className="w-3 h-3 inline mr-1" />{t('common.success', '成功')}</Badge>
                      ) : (
                        <Badge variant="danger"><XCircle className="w-3 h-3 inline mr-1" />{t('common.failed', '失败')}</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{PROVIDER_LABELS[r.provider] || r.provider}</td>
                    <td className="py-2 pr-4 max-w-xs">
                      {r.success ? (() => {
                        const url = r.content_preview || r.remote_url || ''
                        const absUrl = url.startsWith('http') ? url : (url.startsWith('/') ? `${window.location.origin}${url}` : '')
                        if (absUrl && /\.(mp4|webm|mov)($|\?)/i.test(absUrl)) {
                          return <div className="flex items-center gap-2"><video src={absUrl} className="h-12 w-16 object-cover rounded" /><span className="text-xs text-gray-400 truncate">{r.title || '视频'}</span></div>
                        }
                        if (absUrl && /\.(jpg|jpeg|png|gif|webp)($|\?)/i.test(absUrl)) {
                          return <div className="flex items-center gap-2"><img src={absUrl} className="h-12 w-12 object-cover rounded" alt="" /><span className="text-xs text-gray-400 truncate">{r.title || '图片'}</span></div>
                        }
                        return <span className="truncate block" title={r.title || ''}>{r.title || r.content_preview || '-'}</span>
                      })() : (
                        <span className="text-red-500 text-xs">{r.error_message || t('sendRecords.unknownError', '未知错误')}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap text-gray-500 text-xs">{r.sent_at ? formatDate(r.sent_at) : formatDate(r.created_at || '')}</td>
                    <td className="py-2 pr-4">
                      {r.remote_url ? (
                        <a href={r.remote_url.startsWith('http') ? r.remote_url : `${window.location.origin}${r.remote_url}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline inline-flex items-center gap-1 text-xs">
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

      {/* By provider breakdown */}
      {stats && Object.keys(stats.by_provider).length > 0 && (
        <Card>
          <CardContent className="p-4">
            <h3 className="font-medium mb-3">{t('sendRecords.byProvider', '按渠道统计')}</h3>
            <div className="space-y-2">
              {Object.entries(stats.by_provider).map(([prov, data]) => (
                <div key={prov} className="flex items-center justify-between">
                  <span className="text-sm">{PROVIDER_LABELS[prov] || prov}</span>
                  <span className="text-sm text-gray-500">
                    {data.success}/{data.total} {t('sendRecords.success', '成功')}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
