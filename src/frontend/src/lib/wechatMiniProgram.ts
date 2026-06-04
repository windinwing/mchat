/** Helpers for WeChat mini program URL Scheme → in-app H5 bridge. */

export function isWeixinMiniProgramScheme(url: string | undefined | null): boolean {
  if (!url) return false
  return url.startsWith('weixin://dl/business/')
}

export function isMiniProgramBridgeHref(href: string | undefined | null): boolean {
  if (!href) return false
  return href.includes('/mini-program?') || isWeixinMiniProgramScheme(href)
}

export function buildMiniProgramBridgeHref(
  schemeUrl: string,
  name = '微信小程序',
): string {
  const params = new URLSearchParams({
    url: schemeUrl,
    name,
  })
  return `/mini-program?${params.toString()}`
}

function absoluteMiniProgramBridgeHref(schemeUrl: string, name = '微信小程序'): string {
  const bridge = buildMiniProgramBridgeHref(schemeUrl, name)
  if (bridge.startsWith('http://') || bridge.startsWith('https://')) {
    return bridge
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}${bridge}`
  }
  return bridge
}

const _WEIXIN_MD_LINK_RE =
  /\[([^\]]+)\]\((weixin:\/\/dl\/business\/[^)\s]+)\)/gi
const _WEIXIN_SCHEME_RE =
  /weixin:\/\/dl\/business\/\?[^\s\])<>\"']+/gi

/** Rewrite weixin:// before ReactMarkdown (defaultUrlTransform strips unknown protocols). */
export function rewriteMiniProgramLinksInMarkdown(text: string): string {
  if (!text || !text.includes('weixin://dl/business/')) {
    return text
  }
  let updated = text.replace(_WEIXIN_MD_LINK_RE, (_match, label, url) => {
    const resolved = absoluteMiniProgramBridgeHref(String(url).trim(), String(label))
    return `[${label}](${resolved})`
  })
  if (!updated.includes('weixin://dl/business/')) {
    return updated
  }
  updated = updated.replace(_WEIXIN_SCHEME_RE, (url) =>
    absoluteMiniProgramBridgeHref(url),
  )
  return updated
}

export function normalizeMiniProgramHref(
  href: string,
  linkLabel?: string,
): { href: string; isMp: boolean } {
  if (href.startsWith('#小程序://') || href.includes('/mini-program?')) {
    return { href, isMp: true }
  }
  if (isWeixinMiniProgramScheme(href)) {
    return {
      href: buildMiniProgramBridgeHref(href, linkLabel || '微信小程序'),
      isMp: true,
    }
  }
  return { href, isMp: false }
}

export function parseWeixinBusinessScheme(url: string): {
  appid?: string
  path?: string
  query?: string
  env_version?: string
} {
  const raw = (url || '').trim()
  if (!raw.startsWith('weixin://dl/business/')) return {}
  try {
    const parsed = new URL(raw.replace(/^weixin:\/\//, 'https://'))
    return {
      appid: parsed.searchParams.get('appid') || undefined,
      path: parsed.searchParams.get('path') || undefined,
      query: parsed.searchParams.get('query') || undefined,
      env_version: parsed.searchParams.get('env_version') || undefined,
    }
  } catch {
    return {}
  }
}

export function isWechatBrowser(): boolean {
  return /MicroMessenger/i.test(navigator.userAgent)
}
