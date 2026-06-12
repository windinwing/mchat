import api from './api'

export interface ChannelTemplate {
  id: string
  name: string
  description: string | null
  category: string
  icon: string | null
  price_monthly_cents: number
  price_yearly_cents: number
  trial_days: number
  integration_schema?: Array<{
    skill: string
    fields?: Array<{ key: string; label: string; secret?: boolean }>
  }> | null
  default_theme: Record<string, any> | null
  default_welcome_message: string | null
  default_offline_message: string | null
  created_at: string
}

export interface MyChannel {
  id: string
  name: string
  short_code: string | null
  channel_category: string
  template_id: string | null
  plan: string
  trial_ends_at: string | null
  subscription_ends_at?: string | null
  subscription_active?: boolean
  active_order_id?: string | null
  skill_bindings?: Record<string, Record<string, unknown>> | null
  ai_config_id?: string | null
  ai_override?: boolean
  ai_provider?: string | null
  ai_model?: string | null
  template_default_ai_config_id?: string | null
  enabled: boolean
  welcome_message: string | null
  offline_message: string | null
  theme: Record<string, any> | null
  usage_messages_month: number
  usage_tokens_month: number
  usage_messages_limit: number
  usage_tokens_limit: number
  created_at: string
  updated_at: string
}

export interface EmbedCode {
  agent_id: string
  embed_script: string
  widget_url: string
}

export interface WorkflowEntitlements {
  plan: string
  max_workflows: number | null
  max_schedules: number | null
  max_runs_month: number | null
  dag_enabled: boolean
  channel_triggers_enabled: boolean
  workflow_count: number
  schedule_count: number
  runs_month: number
  can_create_workflow: boolean
  can_create_schedule: boolean
  can_run_workflow: boolean
  upgrade_required: boolean
  upgrade_template_id: string | null
  upgrade_channel_id: string | null
  plan_label: string
}

export interface PortalDashboardStats {
  total_channels: number
  active_channels: number
  total_conversations: number
  messages_today: number
  total_messages_month: number
  total_tokens_month: number
  plan: string | null
  trial_ends_at: string | null
}

export interface ChannelKnowledgeBase {
  id: string
  name: string
  description?: string | null
  document_count: number
  source: 'owned' | 'system'
  can_upload?: boolean
  can_delete?: boolean
}

export interface CheckoutResult {
  order_id: string
  order_no: string
  amount_cents: number
  subject: string
  payment_method: string
  qr_content: string
  status: string
}

export interface SkillIntegrationField {
  key: string
  label: string
  secret?: boolean
  placeholder?: string | null
  help?: string | null
}

export interface SkillIntegrationBlock {
  skill: string
  fields: SkillIntegrationField[]
  allow_channel_override?: boolean
  source?: string | null
}

export interface ChannelIntegrations {
  integrations: SkillIntegrationBlock[]
  skill_bindings: Record<string, { override?: boolean; secrets?: Record<string, string> }> | null
}

export interface PortalAiConfigOption {
  id: string
  name: string
  provider: string
  model: string
  is_default: boolean
  has_api_key?: boolean
}

export interface PortalOrder {
  id: string
  order_no: string
  template_id: string
  channel_id: string | null
  channel_name: string | null
  billing_period: string
  amount_cents: number
  subject: string
  status: string
  payment_method: string | null
  provider_trade_no?: string | null
  subscription_ends_at: string | null
  paid_at: string | null
  created_at: string
  updated_at?: string | null
}

export interface PortalOrderDetail extends PortalOrder {
  template_name?: string | null
  is_renewal?: boolean
}

export interface PortalInvoice {
  order_no: string
  status: string
  subject: string
  template_name: string | null
  channel_name: string | null
  billing_period: string
  amount_cents: number
  amount_yuan: string
  payment_method: string | null
  provider_trade_no: string | null
  paid_at: string | null
  subscription_ends_at: string | null
  created_at: string
  company_name: string
  company_tax_id: string | null
  support_email: string | null
  buyer_email: string | null
  buyer_phone: string | null
}

export interface OrderStatus {
  paid: boolean
  status: string
  channel_id?: string | null
}

export interface StudioMemory {
  memory_md: string
  daily_dates: string[]
}

export interface StudioDailyMemory {
  date: string
  content: string
}

export const portalApi = {
  getTemplates: () => api.get<ChannelTemplate[]>('/templates'),
  getTemplate: (id: string) => api.get<ChannelTemplate>(`/templates/${id}`),

  rentChannel: (templateId: string, name?: string) =>
    api.post<MyChannel>('/portal/channels/rent', { template_id: templateId, name }),

  createCheckout: (data: {
    template_id: string
    billing_period: 'monthly' | 'yearly'
    channel_name?: string
    channel_id?: string
    payment_method: 'alipay' | 'wechat'
  }) => api.post<CheckoutResult>('/portal/checkout', data),

  getOrder: (orderId: string) => api.get<PortalOrderDetail>(`/portal/orders/${orderId}`),

  getOrderInvoice: (orderId: string) =>
    api.get<PortalInvoice>(`/portal/orders/${orderId}/invoice`),

  checkOrderStatus: (orderId: string) =>
    api.get<OrderStatus>(`/portal/orders/${orderId}/status`),

  getMyChannels: () => api.get<MyChannel[]>('/portal/channels'),
  getMyChannel: (id: string) => api.get<MyChannel>(`/portal/channels/${id}`),
  getChannelIntegrations: (id: string) =>
    api.get<ChannelIntegrations>(`/portal/channels/${id}/integrations`),
  listAiConfigs: () => api.get<PortalAiConfigOption[]>('/portal/ai-configs'),

  createAiConfig: (data: {
    name: string
    provider: string
    model: string
    api_key: string
    api_base?: string
    system_prompt?: string
  }) => api.post<PortalAiConfigOption>('/portal/ai-configs', data),

  updateAiConfig: (
    id: string,
    data: Partial<{
      name: string
      provider: string
      model: string
      api_key: string
      api_base: string
    }>,
  ) => api.put<PortalAiConfigOption>(`/portal/ai-configs/${id}`, data),
  updateMyChannel: (
    id: string,
    data: Partial<MyChannel> & {
      skill_bindings?: Record<string, { override?: boolean; secrets?: Record<string, string> }>
      ai_override?: boolean
    },
  ) => api.put<MyChannel>(`/portal/channels/${id}`, data),
  deleteMyChannel: (id: string) => api.delete(`/portal/channels/${id}`),

  getEmbedCode: (id: string) => api.get<EmbedCode>(`/portal/channels/${id}/embed`),

  /** Resume persistent portal chat for a channel (Markdown memory + same thread). */
  resumeChannelChat: (
    channelId: string,
    options?: { title?: string; forceNew?: boolean },
  ) =>
    api.post<{
      id: string
      title: string | null
      customer_id?: string | null
      messages?: Array<{
        id: string
        conversation_id: string
        role: string
        content: string
        created_at: string
      }>
      total_message_count?: number
    }>(`/portal/channels/${channelId}/chat/resume`, {
      title: options?.title,
      force_new: options?.forceNew ?? false,
    }),

  getDashboardStats: () => api.get<PortalDashboardStats>('/portal/dashboard'),

  getOrders: () => api.get<PortalOrder[]>('/portal/orders'),

  renewChannel: (
    channelId: string,
    templateId: string,
    billingPeriod: 'monthly' | 'yearly',
    paymentMethod: 'alipay' | 'wechat',
  ) =>
    api.post<CheckoutResult>('/portal/checkout', {
      template_id: templateId,
      channel_id: channelId,
      billing_period: billingPeriod,
      payment_method: paymentMethod,
    }),

  listChannelKnowledgeBases: (channelId: string) =>
    api.get<ChannelKnowledgeBase[]>(`/portal/channels/${channelId}/knowledge-bases`),

  createChannelKnowledgeBase: (channelId: string, data: { name: string; description?: string }) =>
    api.post<{ id: string; name: string }>(
      `/portal/channels/${channelId}/knowledge-bases`,
      data,
    ),

  removeChannelKnowledgeBase: (channelId: string, kbId: string) =>
    api.delete<{ ok: boolean; deleted: boolean }>(
      `/portal/channels/${channelId}/knowledge-bases/${kbId}`,
    ),

  uploadChannelDocument: (channelId: string, kbId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload(`/portal/channels/${channelId}/knowledge-bases/${kbId}/import-file`, form)
  },

  getChannelMemory: (channelId: string) =>
    api.get<StudioMemory>(`/portal/channels/${channelId}/memory`),
  updateChannelMemory: (channelId: string, content: string) =>
    api.put<StudioMemory>(`/portal/channels/${channelId}/memory`, { content }),
  getChannelDailyMemory: (channelId: string, date: string) =>
    api.get<StudioDailyMemory>(`/portal/channels/${channelId}/memory/daily/${date}`),

  getAutomationEntitlements: () =>
    api.get<WorkflowEntitlements>('/portal/automation/entitlements'),
}
