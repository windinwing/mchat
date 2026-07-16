/** Per-provider default API base URL, default model, and preset model list. */

/** Local providers that run on the user's machine and never need an API key. */
export const LOCAL_PROVIDERS = ['ollama', 'lmstudio'] as const

export function isLocalProvider(provider: string | undefined | null): boolean {
  return LOCAL_PROVIDERS.includes((provider || '').trim().toLowerCase() as any)
}

export const PROVIDER_DEFAULT_BASE_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  google: 'https://generativelanguage.googleapis.com',
  deepseek: 'https://api.deepseek.com',
  ollama: 'http://localhost:11434/v1',
  lmstudio: 'http://localhost:1234/v1',
  groq: 'https://api.groq.com/openai/v1',
  zhipu: 'https://open.bigmodel.cn/api/paas/v4',
  'zhipu-coding': 'https://open.bigmodel.cn/api/coding/paas/v4',
  moonshot: 'https://api.moonshot.cn/v1',
  siliconflow: 'https://api.siliconflow.cn/v1',
  together: 'https://api.together.xyz/v1',
  'openai-compatible': '',
}

/** Default model id when user picks a provider. */
export const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
  google: 'gemini-2.0-flash',
  deepseek: 'deepseek-v4-flash',
  ollama: '',
  lmstudio: 'local-model',
  groq: 'llama-3.3-70b-versatile',
  zhipu: 'glm-4-flash',
  'zhipu-coding': 'glm-4.5-air',
  moonshot: 'moonshot-v1-8k',
  siliconflow: 'Qwen/Qwen2.5-7B-Instruct',
  together: 'meta-llama/Llama-3.3-70B-Instruct-Turbo',
  'openai-compatible': 'custom-model',
}

/** Legacy DeepSeek ids → current (2026). */
export const DEEPSEEK_MODEL_ALIASES: Record<string, string> = {
  'deepseek-chat': 'deepseek-v4-flash',
  'deepseek-reasoner': 'deepseek-v4-pro',
}

export function normalizeModelId(provider: string, model: string): string {
  if (provider === 'deepseek') {
    return DEEPSEEK_MODEL_ALIASES[model] ?? model
  }
  return model
}

export function getDefaultBaseUrl(provider: string): string {
  return PROVIDER_DEFAULT_BASE_URLS[provider] ?? ''
}

export function getDefaultModel(provider: string): string {
  return PROVIDER_DEFAULT_MODELS[provider] ?? ''
}

/** Apply provider switch: always reset base URL + default model. */
export function applyProviderDefaults<T extends { provider?: string; api_base?: string | null; model?: string }>(
  prev: T,
  provider: string,
): T {
  return {
    ...prev,
    provider,
    api_base: getDefaultBaseUrl(provider),
    model: getDefaultModel(provider),
  }
}

export const PROVIDER_MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  openai: [
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
    { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
    { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  ],
  anthropic: [
    { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
    { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku' },
    { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus' },
  ],
  google: [
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
    { value: 'gemini-2.0-pro', label: 'Gemini 2.0 Pro' },
  ],
  deepseek: [
    { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
    { value: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
    {
      value: 'deepseek-chat',
      label: 'deepseek-chat（2026/07/24 弃用 → v4-flash）',
    },
    {
      value: 'deepseek-reasoner',
      label: 'deepseek-reasoner（2026/07/24 弃用 → v4-pro）',
    },
  ],
  ollama: [
    // Ollama model ids are machine-specific (name:tag, e.g. "deepseek-r1:32b")
    // and the OpenAI-compatible API (/v1/chat/completions) does NOT fuzzy-match
    // — a wrong tag (e.g. ":latest" when only ":32b" exists) returns 404.
    // We intentionally leave NO static presets: always click "Fetch models" to
    // pull the real list from your local Ollama.
  ],
  lmstudio: [{ value: 'local-model', label: 'Local model' }],
  groq: [
    { value: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B' },
    { value: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B' },
    { value: 'mixtral-8x7b-32768', label: 'Mixtral 8x7B' },
  ],
  zhipu: [
    { value: 'glm-5.2', label: 'GLM-5.2' },
    { value: 'glm-5-turbo', label: 'GLM-5 Turbo' },
    { value: 'glm-5.1', label: 'GLM-5.1' },
    { value: 'glm-4.7', label: 'GLM-4.7' },
    { value: 'glm-4.5-air', label: 'GLM-4.5 Air' },
    { value: 'glm-4-plus', label: 'GLM-4 Plus' },
    { value: 'glm-4-flash', label: 'GLM-4 Flash' },
  ],
  'zhipu-coding': [
    { value: 'glm-5.2', label: 'GLM-5.2' },
    { value: 'glm-5-turbo', label: 'GLM-5 Turbo' },
    { value: 'glm-5.1', label: 'GLM-5.1' },
    { value: 'glm-4.7', label: 'GLM-4.7' },
    { value: 'glm-4.5-air', label: 'GLM-4.5 Air' },
  ],
  moonshot: [
    { value: 'moonshot-v1-8k', label: 'Moonshot V1 8K' },
    { value: 'moonshot-v1-32k', label: 'Moonshot V1 32K' },
  ],
  siliconflow: [
    { value: 'Qwen/Qwen2.5-7B-Instruct', label: 'Qwen 2.5 7B' },
    { value: 'deepseek-ai/DeepSeek-V3', label: 'DeepSeek V3' },
  ],
  together: [
    { value: 'meta-llama/Llama-3.3-70B-Instruct-Turbo', label: 'Llama 3.3 70B' },
    { value: 'mistralai/Mixtral-8x7B-Instruct-v0.1', label: 'Mixtral 8x7B' },
  ],
  'openai-compatible': [{ value: 'custom-model', label: 'Custom model' }],
}

/** Static model ids shown before remote fetch (and as API fallback). */
export const PROVIDER_STATIC_MODEL_IDS: Record<string, string[]> = {
  openai: PROVIDER_MODEL_OPTIONS.openai.map((o) => o.value),
  anthropic: PROVIDER_MODEL_OPTIONS.anthropic.map((o) => o.value),
  google: PROVIDER_MODEL_OPTIONS.google.map((o) => o.value),
  deepseek: [
    'deepseek-v4-flash',
    'deepseek-v4-pro',
    'deepseek-chat',
    'deepseek-reasoner',
  ],
  ollama: PROVIDER_MODEL_OPTIONS.ollama.map((o) => o.value),
  lmstudio: PROVIDER_MODEL_OPTIONS.lmstudio.map((o) => o.value),
  groq: PROVIDER_MODEL_OPTIONS.groq.map((o) => o.value),
  zhipu: PROVIDER_MODEL_OPTIONS.zhipu.map((o) => o.value),
  'zhipu-coding': PROVIDER_MODEL_OPTIONS['zhipu-coding'].map((o) => o.value),
  moonshot: PROVIDER_MODEL_OPTIONS.moonshot.map((o) => o.value),
  siliconflow: PROVIDER_MODEL_OPTIONS.siliconflow.map((o) => o.value),
  together: PROVIDER_MODEL_OPTIONS.together.map((o) => o.value),
  'openai-compatible': ['custom-model'],
}
