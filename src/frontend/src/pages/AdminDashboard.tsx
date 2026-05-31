import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  MessageSquare,
  Bot,
  BookOpen,
  Puzzle,
  TrendingUp,
  Clock,
  ArrowUp,
  ArrowDown,
  BarChart3,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate } from '@/lib/utils'

interface DashboardStats {
  total_conversations: number
  active_conversations: number
  total_agents: number
  total_documents: number
  total_skills: number
  messages_today: number
  avg_response_time: number
  satisfaction_rate: number
  trends: {
    conversations: number
    messages: number
    documents: number
  }
}

interface RecentActivity {
  id: string
  type: 'conversation' | 'message' | 'document' | 'skill'
  description: string
  timestamp: string
}

interface TrendDatapoint {
  date: string
  count: number
}

interface TrendsResponse {
  metric: string
  days: number
  data: TrendDatapoint[]
}

interface OverviewStats {
  total_conversations: number
  active_conversations: number
  closed_conversations: number
  total_messages: number
  messages_today: number
  total_agents: number
  total_documents: number
  total_skills: number
  first_response_time_avg_seconds: number | null
  avg_response_time_seconds: number | null
  resolution_rate: number
}

interface AgentStats {
  customer_id: string
  customer_name: string
  total_conversations: number
  active_conversations: number
  messages_today: number
  avg_response_time_seconds: number | null
}

interface RetrievalStats {
  period_days: number
  total_searches: number
  zero_result_count: number
  zero_result_rate: number
  avg_duration_ms: number
  top_zero_result_queries: Array<{ query: string; count: number }>
}

const PERIOD_OPTIONS = [
  { value: '7', labelKey: 'dashboard.period7d' },
  { value: '30', labelKey: 'dashboard.period30d' },
  { value: '90', labelKey: 'dashboard.period90d' },
] as const

export function AdminDashboard() {
  const { t } = useTranslation()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [overview, setOverview] = useState<OverviewStats | null>(null)
  const [trends, setTrends] = useState<TrendsResponse | null>(null)
  const [agentStats, setAgentStats] = useState<AgentStats[] | null>(null)
  const [retrievalStats, setRetrievalStats] = useState<RetrievalStats | null>(null)
  const [activities, setActivities] = useState<RecentActivity[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [period, setPeriod] = useState('30')

  const loadStats = useCallback(async () => {
    try {
      const data = await api.get<DashboardStats>('/dashboard/stats')
      setStats(data)
      setLoadError(null)
    } catch (err) {
      console.error('Failed to load stats:', err)
      setLoadError(t('dashboard.loadError'))
      setStats({
        total_conversations: 0, active_conversations: 0,
        total_agents: 0, total_documents: 0, total_skills: 0,
        messages_today: 0, avg_response_time: 0, satisfaction_rate: 0,
        trends: { conversations: 0, messages: 0, documents: 0 },
      })
    }
  }, [t])

  const loadOverview = useCallback(async (p: string) => {
    try {
      const data = await api.get<OverviewStats>('/dashboard/overview', { period: p })
      setOverview(data)
    } catch (err) {
      console.error('Failed to load overview:', err)
    }
  }, [])

  const loadTrends = useCallback(async (p: string) => {
    try {
      const data = await api.get<TrendsResponse>('/dashboard/trends', { metric: 'messages', days: p })
      setTrends(data)
    } catch (err) {
      console.error('Failed to load trends:', err)
    }
  }, [])

  const loadAgentStats = useCallback(async () => {
    try {
      const data = await api.get<{ agents: AgentStats[] }>('/dashboard/agents')
      setAgentStats(data.agents)
    } catch (err) {
      console.error('Failed to load agent stats:', err)
    }
  }, [])

  const loadRetrievalStats = useCallback(async (p: string) => {
    try {
      const data = await api.get<RetrievalStats>('/dashboard/retrieval-stats', { days: p })
      setRetrievalStats(data)
    } catch (err) {
      console.error('Failed to load retrieval stats:', err)
    }
  }, [])

  const loadActivities = useCallback(async () => {
    try {
      const data = await api.get<RecentActivity[]>('/dashboard/activities')
      setActivities(data)
    } catch (err) {
      console.error('Failed to load activities:', err)
    }
  }, [])

  useEffect(() => {
    Promise.all([
      loadStats(),
      loadOverview(period),
      loadTrends(period),
      loadAgentStats(),
      loadRetrievalStats(period),
      loadActivities(),
    ]).finally(() => setLoading(false))
  }, [])

  const handlePeriodChange = (p: string) => {
    setPeriod(p)
    loadOverview(p)
    loadTrends(p)
    loadRetrievalStats(p)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="text-center py-20 text-gray-500">
        {loadError || t('dashboard.noData')}
      </div>
    )
  }

  const formatSeconds = (seconds: number | null | undefined): string => {
    if (seconds == null) return '--'
    if (seconds < 60) return `${Math.round(seconds)}s`
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`
    return `${(seconds / 3600).toFixed(1)}h`
  }

  const s = stats
  const resolutionRatePercent = overview
    ? Math.max(
        0,
        Math.min(
          overview.resolution_rate <= 1
            ? overview.resolution_rate * 100
            : overview.resolution_rate,
          100,
        ),
      )
    : 0
  const statCards = [
    { labelKey: 'dashboard.totalConversations', value: s.total_conversations, icon: MessageSquare, color: 'text-blue-600 bg-blue-100 dark:bg-blue-900/30', trend: s.trends.conversations },
    { labelKey: 'dashboard.activeConversations', value: s.active_conversations, icon: Clock, color: 'text-green-600 bg-green-100 dark:bg-green-900/30', trend: 0 },
    { labelKey: 'dashboard.totalAgents', value: s.total_agents, icon: Bot, color: 'text-purple-600 bg-purple-100 dark:bg-purple-900/30', trend: 0 },
    { labelKey: 'dashboard.totalDocuments', value: s.total_documents, icon: BookOpen, color: 'text-orange-600 bg-orange-100 dark:bg-orange-900/30', trend: s.trends.documents },
    { labelKey: 'dashboard.totalSkills', value: s.total_skills, icon: Puzzle, color: 'text-teal-600 bg-teal-100 dark:bg-teal-900/30', trend: 0 },
    { labelKey: 'dashboard.messagesToday', value: s.messages_today, icon: TrendingUp, color: 'text-pink-600 bg-pink-100 dark:bg-pink-900/30', trend: s.trends.messages },
  ] as const

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t('dashboard.title')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
          {PERIOD_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={period === opt.value ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handlePeriodChange(opt.value)}
            >
              {t(opt.labelKey)}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {statCards.map((card) => (
          <Card key={card.labelKey}>
            <CardContent className="py-4">
              <div className="flex items-center justify-between mb-3">
                <div className={`p-2 rounded-lg ${card.color}`}>
                  <card.icon className="w-5 h-5" />
                </div>
                {card.trend !== 0 && (
                  <Badge variant={card.trend > 0 ? 'success' : 'danger'} size="sm">
                    <span className="flex items-center gap-0.5">
                      {card.trend > 0 ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                      {Math.abs(card.trend)}%
                    </span>
                  </Badge>
                )}
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {card.value.toLocaleString()}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {t(card.labelKey)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* KPI overview row */}
      {overview && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="py-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.frtLabel')}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {formatSeconds(overview.first_response_time_avg_seconds)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.artLabel')}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {formatSeconds(overview.avg_response_time_seconds)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.resolutionRate')}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {resolutionRatePercent.toFixed(1)}%
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {retrievalStats && (
        <Card>
          <CardContent className="py-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">
              知识库检索（近 {retrievalStats.period_days} 天）
            </h3>
            <div className="grid gap-4 sm:grid-cols-3 text-sm">
              <div>
                <p className="text-gray-500 dark:text-gray-400">检索次数</p>
                <p className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  {retrievalStats.total_searches}
                </p>
              </div>
              <div>
                <p className="text-gray-500 dark:text-gray-400">零结果率</p>
                <p className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  {(retrievalStats.zero_result_rate * 100).toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-gray-500 dark:text-gray-400">平均耗时</p>
                <p className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  {retrievalStats.avg_duration_ms} ms
                </p>
              </div>
            </div>
            {retrievalStats.top_zero_result_queries.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-500 mb-2">高频零结果查询</p>
                <ul className="text-xs text-gray-700 dark:text-gray-300 space-y-1">
                  {retrievalStats.top_zero_result_queries.slice(0, 5).map((item) => (
                    <li key={item.query} className="truncate">
                      {item.query} ({item.count})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Trend chart */}
        <Card className="lg:col-span-3">
          <CardContent className="py-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
              {t('dashboard.trendsTitle')}
            </h3>
            {trends && trends.data.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={trends.data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: unknown) => String(v).slice(5)}
                    stroke="#9ca3af"
                  />
                  <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-400 text-center py-10">{t('dashboard.noData')}</p>
            )}
          </CardContent>
        </Card>

        {/* Activity sidebar */}
        <Card className="lg:col-span-2 self-start">
          <CardContent className="py-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
              {t('dashboard.recentActivity')}
            </h3>
            {activities.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">
                {t('dashboard.noActivity')}
              </p>
            ) : (
              <div className="space-y-3">
                {activities.slice(0, 5).map((activity) => (
                  <div key={activity.id} className="flex items-center gap-3 text-sm">
                    <div className="w-2 h-2 rounded-full bg-primary-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-700 dark:text-gray-300 truncate">
                        {activity.description}
                      </p>
                      <p className="text-xs text-gray-400">
                        {formatDate(activity.timestamp)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Agent performance table */}
      {agentStats && agentStats.length > 0 && (
        <Card>
          <CardContent className="py-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-primary-600" />
              {t('dashboard.agentPerformance')}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
                    <th className="py-2 pr-4">{t('dashboard.agentName')}</th>
                    <th className="py-2 pr-4">{t('dashboard.totalConversations')}</th>
                    <th className="py-2 pr-4">{t('dashboard.activeConversations')}</th>
                    <th className="py-2 pr-4">{t('dashboard.messagesToday')}</th>
                    <th className="py-2 pr-4">{t('dashboard.artLabel')}</th>
                  </tr>
                </thead>
                <tbody>
                  {agentStats.map((agent) => (
                    <tr key={agent.customer_id} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-3 pr-4 font-medium text-gray-900 dark:text-gray-100">
                        {agent.customer_name}
                      </td>
                      <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                        {agent.total_conversations}
                      </td>
                      <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                        {agent.active_conversations}
                      </td>
                      <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                        {agent.messages_today}
                      </td>
                      <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                        {formatSeconds(agent.avg_response_time_seconds)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
