/** Cloud-only portal routes (imported by AppPortal / main-portal only). */
import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { isCloudEdition } from '@/lib/edition'
import { UserLayout } from './components/layout/UserLayout'
import { Spinner } from './components/ui/Spinner'

const lazyNamed = <T extends Record<string, React.ComponentType<any>>>(
  loader: () => Promise<T>,
  name: keyof T
) => lazy(() => loader().then(m => ({ default: m[name] })))

const RegisterPage = lazyNamed(() => import('./pages/RegisterPage'), 'RegisterPage')
const Auth9235CallbackPage = lazyNamed(
  () => import('./pages/Auth9235CallbackPage'),
  'Auth9235CallbackPage',
)
const PortalDashboard = lazyNamed(() => import('./pages/portal/DashboardPage'), 'DashboardPage')
const PortalTemplates = lazyNamed(() => import('./pages/portal/TemplatesPage'), 'TemplatesPage')
const PortalTemplateDetail = lazyNamed(
  () => import('./pages/portal/TemplateDetailPage'),
  'TemplateDetailPage',
)
const PortalMyChannels = lazyNamed(() => import('./pages/portal/MyChannelsPage'), 'MyChannelsPage')
const PortalChannelDetail = lazyNamed(
  () => import('./pages/portal/ChannelDetailPage'),
  'ChannelDetailPage',
)
const PortalGroupsPage = lazyNamed(
  () => import('./pages/portal/PortalGroupsPage'),
  'PortalGroupsPage',
)
const PortalChannelKnowledge = lazyNamed(
  () => import('./pages/portal/ChannelKnowledgePage'),
  'ChannelKnowledgePage',
)
const CheckoutPage = lazyNamed(() => import('./pages/portal/CheckoutPage'), 'CheckoutPage')
const OrdersPage = lazyNamed(() => import('./pages/portal/OrdersPage'), 'OrdersPage')
const OrderDetailPage = lazyNamed(
  () => import('./pages/portal/OrderDetailPage'),
  'OrderDetailPage',
)
const PortalAccountPage = lazyNamed(
  () => import('./pages/portal/PortalAccountPage'),
  'PortalAccountPage',
)
const WorkflowsPage = lazyNamed(() => import('./pages/WorkflowsPage'), 'WorkflowsPage')
const SkillSchedulesPage = lazyNamed(
  () => import('./pages/SkillSchedulesPage'),
  'SkillSchedulesPage',
)

function PageSuspense({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <Spinner size="lg" />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

export function PortalRoutes() {
  // Core edition: /register and /auth/9235 live in CoreRoutes only (avoid double RegisterPage).
  if (!isCloudEdition) {
    return null
  }
  return (
    <Routes>
      <Route path="/register" element={<PageSuspense><RegisterPage /></PageSuspense>} />
      <Route path="/auth/9235" element={<PageSuspense><Auth9235CallbackPage /></PageSuspense>} />
      <Route path="/portal" element={<UserLayout><PageSuspense><PortalDashboard /></PageSuspense></UserLayout>} />
      <Route
        path="/portal/dashboard"
        element={<UserLayout><PageSuspense><PortalDashboard /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/templates"
        element={<UserLayout><PageSuspense><PortalTemplates /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/templates/:id"
        element={<UserLayout><PageSuspense><PortalTemplateDetail /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/checkout"
        element={<UserLayout><PageSuspense><CheckoutPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/orders"
        element={<UserLayout><PageSuspense><OrdersPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/orders/:id"
        element={<UserLayout><PageSuspense><OrderDetailPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/channels"
        element={<UserLayout><PageSuspense><PortalMyChannels /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/groups"
        element={<UserLayout><PageSuspense><PortalGroupsPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/account"
        element={<UserLayout><PageSuspense><PortalAccountPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/channels/:id"
        element={<UserLayout><PageSuspense><PortalChannelDetail /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/channels/:id/knowledge"
        element={<UserLayout><PageSuspense><PortalChannelKnowledge /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/workflows"
        element={<UserLayout><PageSuspense><WorkflowsPage /></PageSuspense></UserLayout>}
      />
      <Route
        path="/portal/schedules"
        element={<UserLayout><PageSuspense><SkillSchedulesPage /></PageSuspense></UserLayout>}
      />
    </Routes>
  )
}
