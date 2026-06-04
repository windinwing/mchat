import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  initWechatOpenTags,
  resolveMiniprogramScheme,
} from '@/lib/wechatJssdk'
import {
  isWechatBrowser,
  isWeixinMiniProgramScheme,
  parseWeixinBusinessScheme,
} from '@/lib/wechatMiniProgram'

function getParams(): { url: string; name: string } {
  const p = new URLSearchParams(window.location.search)
  return {
    url: p.get('url') || '',
    name: p.get('name') || '',
  }
}

function isUrlLink(href: string): boolean {
  return (
    href.startsWith('https://wxaurl.cn/')
    || href.startsWith('https://wxurl.cn/')
  )
}

function buildLaunchPath(scheme: ReturnType<typeof parseWeixinBusinessScheme>): string {
  const path = (scheme.path || 'pages/index/index').replace(/^\//, '')
  if (scheme.query) return `${path}?${scheme.query}`
  return path
}

export function MpJump() {
  const { url: rawUrl, name } = useMemo(() => getParams(), [])
  const [targetUrl, setTargetUrl] = useState(rawUrl)
  const [status, setStatus] = useState<'loading' | 'ready' | 'redirecting' | 'failed'>('loading')
  const [jssdkReady, setJssdkReady] = useState(false)
  const [errorHint, setErrorHint] = useState('')
  const launchRef = useRef<HTMLDivElement>(null)
  const isWechat = isWechatBrowser()

  const scheme = useMemo(
    () => (isWeixinMiniProgramScheme(targetUrl) ? parseWeixinBusinessScheme(targetUrl) : {}),
    [targetUrl],
  )

  const displayName = name || '微信小程序'

  const redirect = useCallback((href: string) => {
    setStatus('redirecting')
    window.location.href = href
    window.setTimeout(() => setStatus('failed'), 2200)
  }, [])

  useEffect(() => {
    if (!rawUrl) {
      setStatus('failed')
      return
    }

    let cancelled = false

    async function bootstrap() {
      if (isUrlLink(rawUrl)) {
        redirect(rawUrl)
        return
      }

      if (isWeixinMiniProgramScheme(rawUrl)) {
        const resolved = await resolveMiniprogramScheme(rawUrl)
        if (cancelled) return
        if (resolved?.is_url_link && resolved.click_url) {
          redirect(resolved.click_url)
          return
        }
      }

      if (!cancelled) {
        setTargetUrl(rawUrl)
        setStatus('ready')
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [rawUrl, redirect])

  useEffect(() => {
    if (!isWechat || !scheme.appid || status !== 'ready') return

    let cancelled = false
    setErrorHint('')

    void initWechatOpenTags(window.location.href)
      .then(() => {
        if (!cancelled) setJssdkReady(true)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setJssdkReady(false)
        const msg = err instanceof Error ? err.message : String(err)
        if (/40164|not in whitelist|ip.*whitelist/i.test(msg)) {
          setErrorHint(
            '服务器 IP 未加入微信公众号白名单，请在公众平台 → 设置与开发 → 基本配置 → IP白名单 中添加服务器出口 IP（联系运维获取）。',
          )
          return
        }
        setErrorHint(
          msg || '微信 JS-SDK 初始化失败，请确认 mchat.9235.net 已加入 JS 接口安全域名，且公众号已关联目标小程序。',
        )
      })

    return () => {
      cancelled = true
    }
  }, [isWechat, scheme.appid, status])

  useEffect(() => {
    const container = launchRef.current
    if (!container || !jssdkReady || !scheme.appid) return

    container.innerHTML = ''
    const tag = document.createElement('wx-open-launch-weapp')
    tag.setAttribute('appid', scheme.appid)
    tag.setAttribute('path', buildLaunchPath(scheme))
    if (scheme.env_version && scheme.env_version !== 'release') {
      tag.setAttribute('env-version', scheme.env_version)
    }

    const template = document.createElement('script')
    template.type = 'text/wxtag-template'
    template.innerHTML = `
      <button style="
        display:inline-block;
        padding:12px 28px;
        background:#07c160;
        color:#fff;
        border:none;
        border-radius:8px;
        font-size:15px;
        font-weight:600;
        cursor:pointer;
        width:100%;
      ">打开${displayName.replace(/[<>&"']/g, '')}</button>
    `
    tag.appendChild(template)
    container.appendChild(tag)
  }, [jssdkReady, scheme, displayName])

  if (!rawUrl) {
    return (
      <div style={{ display:'flex',alignItems:'center',justifyContent:'center',height:'100dvh',fontFamily:'system-ui,sans-serif',color:'#666',textAlign:'center',padding:24 }}>
        <div>缺少 <code>?url=</code> 参数</div>
      </div>
    )
  }

  return (
    <div style={{ display:'flex',alignItems:'center',justifyContent:'center',height:'100dvh',fontFamily:'system-ui,sans-serif',textAlign:'center',padding:24,background:'#f5f5f5' }}>
      <div style={{ maxWidth:360,width:'100%' }}>
        <div style={{ fontSize:40,marginBottom:12 }}>📱</div>
        <div style={{ fontWeight:700,fontSize:16,color:'#333',marginBottom:8 }}>
          {status === 'redirecting' || status === 'loading'
            ? `正在打开${displayName}…`
            : `打开${displayName}`}
        </div>
        {scheme.appid && (
          <div style={{ fontSize:12,color:'#888',marginBottom:12,wordBreak:'break-all' }}>
            {buildLaunchPath(scheme)}
          </div>
        )}
        <div style={{ fontSize:14,color:'#666',marginBottom:20 }}>
          {isWechat
            ? jssdkReady
              ? '请点击下方绿色按钮打开小程序（微信要求手动点击）。'
              : errorHint || '正在加载微信开放标签…'
            : '请在微信中打开此链接，再跳转小程序。'}
        </div>

        {isWechat && jssdkReady && scheme.appid ? (
          <div ref={launchRef} style={{ minHeight:48 }} />
        ) : (
          !isWechat && (
            <p style={{ fontSize:12,color:'#999',marginTop:8 }}>
              复制当前页面链接，发送到微信后再打开。
            </p>
          )
        )}

        {status === 'failed' && isWechat && (
          <p style={{ fontSize:12,color:'#c00',marginTop:16 }}>
            未能自动跳转。若按钮无效，请确认公众号与小程序已关联，且本域名已加入 JS 接口安全域名。
          </p>
        )}
      </div>
    </div>
  )
}
