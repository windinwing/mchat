/** Load WeChat JS-SDK and sign for wx-open-launch-weapp. */

export interface WechatJssdkConfig {
  appId: string
  nonceStr: string
  timestamp: number
  signature: string
}

type WechatJssdkWx = {
  config: (opts: Record<string, unknown>) => void
  ready: (cb: () => void) => void
  error: (cb: (err: unknown) => void) => void
}

function getWx(): WechatJssdkWx | undefined {
  return (window as Window & { wx?: WechatJssdkWx }).wx
}

let jssdkPromise: Promise<void> | null = null

export function loadWechatJssdkScript(): Promise<void> {
  if (getWx()?.config) return Promise.resolve()
  if (jssdkPromise) return jssdkPromise
  jssdkPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-wechat-jssdk]')
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('jssdk load failed')))
      return
    }
    const script = document.createElement('script')
    script.src = 'https://res.wx.qq.com/open/js/jweixin-1.6.0.js'
    script.async = true
    script.dataset.wechatJssdk = '1'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('jssdk load failed'))
    document.head.appendChild(script)
  })
  return jssdkPromise
}

export async function fetchWechatJssdkConfig(pageUrl: string): Promise<WechatJssdkConfig> {
  const signUrl = pageUrl.split('#')[0]
  const resp = await fetch(
    `/api/wechat/jssdk-config?url=${encodeURIComponent(signUrl)}`,
  )
  if (!resp.ok) {
    const detail = await resp.text()
    throw new Error(detail || `jssdk-config ${resp.status}`)
  }
  return resp.json()
}

export async function initWechatOpenTags(pageUrl: string): Promise<void> {
  await loadWechatJssdkScript()
  const config = await fetchWechatJssdkConfig(pageUrl)
  await new Promise<void>((resolve, reject) => {
    const wx = getWx()
    if (!wx?.config) {
      reject(new Error('wx missing after script load'))
      return
    }
    wx.config({
      debug: false,
      appId: config.appId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.signature,
      jsApiList: [],
      openTagList: ['wx-open-launch-weapp'],
    })
    wx.ready(() => resolve())
    wx.error((err: unknown) => reject(err instanceof Error ? err : new Error(String(err))))
  })
}

export interface MiniprogramResolveResult {
  parsed: {
    appid: string
    path: string
    query?: string
    env_version?: string
  }
  click_url: string
  is_url_link: boolean
}

export async function resolveMiniprogramScheme(
  schemeUrl: string,
): Promise<MiniprogramResolveResult | null> {
  const resp = await fetch(
    `/api/wechat/miniprogram-resolve?scheme=${encodeURIComponent(schemeUrl)}`,
  )
  if (!resp.ok) return null
  return resp.json()
}
