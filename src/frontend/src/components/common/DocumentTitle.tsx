import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, matchPath } from 'react-router-dom'

const ROUTE_TITLE_KEYS: Array<{ pattern: string; key: string }> = [
  { pattern: '/', key: 'meta.titleLanding' },
  { pattern: '/admin/login', key: 'meta.titleLogin' },
  { pattern: '/admin', key: 'meta.titleDashboard' },
  { pattern: '/admin/conversations', key: 'meta.titleConversations' },
  { pattern: '/admin/knowledge', key: 'meta.titleKnowledge' },
  { pattern: '/admin/skills', key: 'meta.titleSkills' },
  { pattern: '/admin/workflows', key: 'meta.titleWorkflows' },
  { pattern: '/admin/schedules', key: 'meta.titleSchedules' },
  { pattern: '/admin/agents', key: 'meta.titleAgents' },
  { pattern: '/admin/customer-agents', key: 'meta.titleCustomerAgents' },
  { pattern: '/admin/users', key: 'meta.titleUsers' },
  { pattern: '/admin/settings', key: 'meta.titleSettings' },
  { pattern: '/admin/channels', key: 'meta.titleChannels' },
  { pattern: '/chat/:conversationId', key: 'meta.titleChat' },
  { pattern: '/widget/demo', key: 'meta.titleWidgetDemo' },
  { pattern: '/widget', key: 'meta.titleWidget' },
]

export function DocumentTitle() {
  const { t, i18n } = useTranslation()
  const location = useLocation()

  useEffect(() => {
    let key = 'meta.titleDefault'
    for (const route of ROUTE_TITLE_KEYS) {
      if (matchPath({ path: route.pattern, end: route.pattern === '/' }, location.pathname)) {
        key = route.key
        break
      }
    }
    document.title = t(key)
  }, [location.pathname, t, i18n.language])

  return null
}
