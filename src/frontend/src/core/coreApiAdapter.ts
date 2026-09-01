import api from '@/lib/api'

interface CoreChannel {
  id: string
  name: string
  enabled?: boolean
}

interface ResumeChannelOptions {
  title?: string
  forceNew?: boolean
}

/**
 * Core implementation for the shared chat calls. It talks only to Core
 * endpoints, so no Portal client or endpoint is emitted into the artifact.
 */
export const coreChatApi = {
  getMyChannels: () => api.get<CoreChannel[]>('/agents/customer-configs'),

  resumeChannelChat: (channelId: string, options: ResumeChannelOptions = {}) =>
    api.post<{ id: string }>('/chat/conversations/resume', {
      customer_id: channelId,
      title: options.title,
      force_new: options.forceNew ?? false,
    }),
}
