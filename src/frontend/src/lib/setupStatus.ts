import api from '@/lib/api'

export interface SetupStatus {
  ai_ready: boolean
  has_assistant: boolean
  ai_config_count: number
  env_key_providers: string[]
}

export async function fetchSetupStatus(): Promise<SetupStatus> {
  return api.get<SetupStatus>('/auth/setup-status')
}
