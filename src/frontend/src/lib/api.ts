const API_BASE = '/api'

interface RequestOptions extends RequestInit {
  params?: Record<string, string>
}

class ApiError extends Error {
  status: number
  data: any

  constructor(message: string, status: number, data?: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

function getToken(): string | null {
  return localStorage.getItem('mchat_token')
}

function setToken(token: string): void {
  localStorage.setItem('mchat_token', token)
}

function removeToken(): void {
  localStorage.removeItem('mchat_token')
}

async function request<T = any>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options

  let url = `${API_BASE}${endpoint}`
  if (params) {
    const searchParams = new URLSearchParams(params)
    url += `?${searchParams.toString()}`
  }

  const isFormData = options.body instanceof FormData
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
  }

  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  })

  if (!response.ok) {
    let errorData: any
    try {
      errorData = await response.json()
    } catch {
      errorData = { message: response.statusText }
    }

    if (response.status === 401) {
      const isLoginRequest =
        endpoint === '/auth/login' || endpoint === '/auth/sso/9235/callback'
      if (!isLoginRequest) {
        removeToken()
        const path = window.location.pathname
        const search = window.location.search || ''
        const current = encodeURIComponent(path + search)
        if (path.startsWith('/portal')) {
          if (path !== '/register') {
            window.location.href = `/register?redirect=${current}`
          }
        } else if (path !== '/admin/login') {
          window.location.href = `/admin/login?redirect=${current}`
        }
      }
    }

    const rawDetail =
      errorData.detail ??
      errorData.message ??
      errorData.error ??
      (typeof errorData === 'string' ? errorData : null)

    let message = '请求失败'
    if (typeof rawDetail === 'string') {
      message = rawDetail
    } else if (Array.isArray(rawDetail)) {
      message = rawDetail.map((d: { msg?: string }) => d.msg || String(d)).join('; ')
    } else if (rawDetail && typeof rawDetail === 'object' && 'message' in rawDetail) {
      const nested = (rawDetail as { message?: unknown }).message
      if (typeof nested === 'string' && nested.trim()) {
        message = nested
      }
    }

    throw new ApiError(message, response.status, errorData)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const api = {
  get: <T = any>(endpoint: string, params?: Record<string, string>) =>
    request<T>(endpoint, { method: 'GET', params }),

  post: <T = any>(endpoint: string, data?: any) =>
    request<T>(endpoint, { method: 'POST', body: JSON.stringify(data) }),

  put: <T = any>(endpoint: string, data?: any) =>
    request<T>(endpoint, { method: 'PUT', body: JSON.stringify(data) }),

  patch: <T = any>(endpoint: string, data?: any) =>
    request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(data) }),

  delete: <T = any>(endpoint: string, params?: Record<string, string>) =>
    request<T>(endpoint, { method: 'DELETE', params }),

  upload: <T = any>(endpoint: string, formData: FormData) =>
    request<T>(endpoint, {
      method: 'POST',
      body: formData,
    }),

  /** Download a file with Bearer auth (plain anchor href cannot send JWT). */
  download: async (endpoint: string, params?: Record<string, string>, filename?: string) => {
    let url = `${API_BASE}${endpoint}`
    if (params) {
      url += `?${new URLSearchParams(params).toString()}`
    }
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
    const response = await fetch(url, { headers })
    if (!response.ok) {
      let errorData: unknown
      try {
        errorData = await response.json()
      } catch {
        errorData = { message: response.statusText }
      }
      const detail =
        (errorData as { detail?: string })?.detail ??
        (errorData as { message?: string })?.message ??
        'Download failed'
      throw new ApiError(String(detail), response.status, errorData)
    }
    const blob = await response.blob()
    const name =
      filename ||
      (() => {
        try {
          const last = new URL(url, window.location.origin).pathname.split('/').pop()
          return last || 'download'
        } catch {
          return 'download'
        }
      })()
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(objectUrl)
  },
}

export { setToken, removeToken, getToken, ApiError }
export default api
