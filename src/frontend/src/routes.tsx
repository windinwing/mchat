import { Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { isCloudEdition, isSignupEnabled } from '@/lib/edition'
import { lazyNamed } from '@/lib/chunkLoadRecovery'
import { AdminLayout } from './components/layout/AdminLayout'
import { UserLayout } from './components/layout/UserLayout'
import { Spinner } from './components/ui/Spinner'
import { DocumentTitle } from './components/common/DocumentTitle'

const LandingPage = lazyNamed(() => import('./pages/LandingPage'), 'LandingPage')
const AdminLogin = lazyNamed(() => import('./pages/AdminLogin'), 'AdminLogin')
const AdminDashboard = lazyNamed(() => import('./pages/AdminDashboard'), 'AdminDashboard')
const ConversationsPage = lazyNamed(() => import('./pages/ConversationsPage'), 'ConversationsPage')
const KnowledgePage = lazyNamed(() => import('./pages/KnowledgePage'), 'KnowledgePage')
const SkillsPage = lazyNamed(() => import('./pages/SkillsPage'), 'SkillsPage')
const WorkflowsPage = lazyNamed(() => import('./pages/WorkflowsPage'), 'WorkflowsPage')
const WorkflowGraphPage = lazyNamed(() => import('./pages/WorkflowGraphPage'), 'WorkflowGraphPage')
const WorkflowCenterPage = lazyNamed(
  () => import('./pages/WorkflowCenterPage'),
  'WorkflowCenterPage',
)
const WorkspacePage = lazyNamed(() => import('./pages/WorkspacePage'), 'WorkspacePage')
const FilesPage = lazyNamed(() => import('./pages/FilesPage'), 'FilesPage')
const SkillSchedulesPage = lazyNamed(
  () => import('./pages/SkillSchedulesPage'),
  'SkillSchedulesPage',
)
const AgentsPage = lazyNamed(() => import('./pages/AgentsPage'), 'AgentsPage')
const CustomerAgentsPage = lazyNamed(() => import('./pages/CustomerAgentsPage'), 'CustomerAgentsPage')
const SettingsPage = lazyNamed(() => import('./pages/SettingsPage'), 'SettingsPage')
const ChannelsPage = lazyNamed(() => import('./pages/ChannelsPage'), 'ChannelsPage')
const PublishingAccountsPage = lazyNamed(() => import('./pages/PublishingAccountsPage'), 'PublishingAccountsPage')
const PortalSendRecords = lazyNamed(() => import('./pages/portal/SendRecordsPage'), 'SendRecordsPage')
const AdminSendRecords = lazyNamed(() => import('./pages/SendRecordsAdminPage'), 'SendRecordsAdminPage')
const ChatHomePage = lazyNamed(() => import('./pages/ChatHomePage'), 'ChatHomePage')
const ChatPage = lazyNamed(() => import('./pages/ChatPage'), 'ChatPage')
const WidgetDemo = lazyNamed(() => import('./pages/WidgetDemo'), 'WidgetDemo')
const WidgetPage = lazyNamed(() => import('./pages/WidgetPage'), 'WidgetPage')
const SkillShowcasePage = lazyNamed(() => import('./pages/SkillShowcasePage'), 'SkillShowcasePage')
const WxMiniPage = lazyNamed(() => import('./pages/WxMiniPage'), 'WxMiniPage')
const MpJump = lazyNamed(() => import('./pages/MpJump'), 'MpJump')
const HelpPage = lazyNamed(() => import('./pages/HelpPage'), 'HelpPage')
const UsersPage = lazyNamed(() => import('./pages/UsersPage'), 'UsersPage')
const RolesPage = lazyNamed(() => import('./pages/RolesPage'), 'RolesPage')
const GroupsPage = lazyNamed(() => import('./pages/GroupsPage'), 'GroupsPage')
const GroupMemoryPage = lazyNamed(() => import('./pages/GroupMemoryPage'), 'GroupMemoryPage')
const DevBridgePage = lazyNamed(() => import('./pages/DevBridgePage'), 'DevBridgePage')
const DevBridgeSettingsPage = lazyNamed(() => import('./pages/DevBridgeSettingsPage'), 'DevBridgeSettingsPage')
const TemplateManagerPage = lazyNamed(() => import('./pages/admin/TemplateManagerPage'), 'TemplateManagerPage')
const AdminOrdersPage = lazyNamed(() => import('./pages/admin/AdminOrdersPage'), 'AdminOrdersPage')
const AdminSubscriptionsPage = lazyNamed(
  () => import('./pages/admin/AdminSubscriptionsPage'),
  'AdminSubscriptionsPage',
)

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

export function PageSuspense({ children }: { children: React.ReactNode }) {
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

export function CoreRoutes() {
  return (
    <>
      <DocumentTitle />
      <Routes>
        <Route path="/" element={<PageSuspense><LandingPage /></PageSuspense>} />
        <Route path="/admin/login" element={<PageSuspense><AdminLogin /></PageSuspense>} />
        {!isCloudEdition && !isSignupEnabled && (
          <>
            <Route path="/register" element={<Navigate to="/admin/login" replace />} />
            <Route path="/auth/9235" element={<Navigate to="/admin/login" replace />} />
            <Route path="/portal/*" element={<Navigate to="/admin/login" replace />} />
          </>
        )}
        {!isCloudEdition && isSignupEnabled && (
          <>
            <Route path="/register" element={<PageSuspense><RegisterPage /></PageSuspense>} />
            <Route path="/auth/9235" element={<PageSuspense><Auth9235CallbackPage /></PageSuspense>} />
            <Route path="/portal/*" element={<Navigate to="/chat" replace />} />
          </>
        )}
        <Route path="/chat" element={<PageSuspense><ChatHomePage /></PageSuspense>} />
        <Route path="/admin" element={<AdminLayout><PageSuspense><AdminDashboard /></PageSuspense></AdminLayout>} />
        <Route path="/admin/conversations" element={<AdminLayout><PageSuspense><ConversationsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/knowledge" element={<AdminLayout><PageSuspense><KnowledgePage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/skills" element={<AdminLayout><PageSuspense><SkillsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/workflows" element={<AdminLayout><PageSuspense><WorkflowsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/workflows/:workflowId/graph" element={<PageSuspense><WorkflowGraphPage /></PageSuspense>} />
        <Route path="/admin/workflow-center" element={<AdminLayout><PageSuspense><WorkflowCenterPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/workspace" element={<AdminLayout><PageSuspense><WorkspacePage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/files" element={<AdminLayout><PageSuspense><FilesPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/schedules" element={<AdminLayout><PageSuspense><SkillSchedulesPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/agents" element={<AdminLayout><PageSuspense><AgentsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/customer-agents" element={<AdminLayout><PageSuspense><CustomerAgentsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/settings" element={<AdminLayout><PageSuspense><SettingsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/channels" element={<AdminLayout><PageSuspense><ChannelsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/publishing-accounts" element={<AdminLayout><PageSuspense><PublishingAccountsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/send-records" element={<AdminLayout><PageSuspense><AdminSendRecords /></PageSuspense></AdminLayout>} />
        <Route path="/admin/roles" element={<AdminLayout><PageSuspense><RolesPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/groups" element={<AdminLayout><PageSuspense><GroupsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/group-memory" element={<AdminLayout><PageSuspense><GroupMemoryPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/devbridge" element={<AdminLayout><PageSuspense><DevBridgePage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/devbridge/settings" element={<AdminLayout><PageSuspense><DevBridgeSettingsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/templates" element={<AdminLayout><PageSuspense><TemplateManagerPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/orders" element={<AdminLayout><PageSuspense><AdminOrdersPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/subscriptions" element={<AdminLayout><PageSuspense><AdminSubscriptionsPage /></PageSuspense></AdminLayout>} />
        <Route path="/admin/users" element={<AdminLayout><PageSuspense><UsersPage /></PageSuspense></AdminLayout>} />
        <Route path="/chat/:conversationId" element={<PageSuspense><ChatPage /></PageSuspense>} />
        <Route path="/widget/demo" element={<PageSuspense><WidgetDemo /></PageSuspense>} />
        <Route path="/widget" element={<PageSuspense><WidgetPage /></PageSuspense>} />
        <Route path="/wx-mini" element={<PageSuspense><WxMiniPage /></PageSuspense>} />
        <Route path="/mini-program" element={<PageSuspense><MpJump /></PageSuspense>} />
        <Route path="/help" element={<PageSuspense><HelpPage /></PageSuspense>} />
        <Route path="/showcase" element={<PageSuspense><SkillShowcasePage /></PageSuspense>} />
      </Routes>
    </>
  )
}

export function PortalRoutes() {
  if (!isCloudEdition) {
    return null
  }
  return (
    <Routes>
      <Route path="/register" element={<PageSuspense><RegisterPage /></PageSuspense>} />
      <Route path="/portal/chat" element={<Navigate to="/chat" replace />} />
      <Route path="/portal" element={<UserLayout><PageSuspense><PortalDashboard /></PageSuspense></UserLayout>} />
      <Route path="/portal/dashboard" element={<UserLayout><PageSuspense><PortalDashboard /></PageSuspense></UserLayout>} />
      <Route path="/portal/templates" element={<UserLayout><PageSuspense><PortalTemplates /></PageSuspense></UserLayout>} />
      <Route path="/portal/templates/:id" element={<UserLayout><PageSuspense><PortalTemplateDetail /></PageSuspense></UserLayout>} />
      <Route path="/portal/channels" element={<UserLayout><PageSuspense><PortalMyChannels /></PageSuspense></UserLayout>} />
      <Route path="/portal/channels/:id" element={<UserLayout><PageSuspense><PortalChannelDetail /></PageSuspense></UserLayout>} />
      <Route path="/portal/publishing-accounts" element={<UserLayout><PageSuspense><PublishingAccountsPage /></PageSuspense></UserLayout>} />
      <Route path="/portal/send-records" element={<UserLayout><PageSuspense><PortalSendRecords /></PageSuspense></UserLayout>} />
      <Route path="/portal/workflows" element={<UserLayout><PageSuspense><WorkflowsPage /></PageSuspense></UserLayout>} />
      <Route path="/portal/workflow-center" element={<UserLayout><PageSuspense><WorkflowCenterPage /></PageSuspense></UserLayout>} />
    </Routes>
  )
}
