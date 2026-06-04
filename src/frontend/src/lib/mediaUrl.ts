import type { Message } from '@/stores/chat'

/** Storage keys written by MChat upload workflows. */
const UPLOAD_KEY_PREFIXES = [
  'chat/',
  'knowledge/',
  'disclosure/',
  'embedding_models/',
  'workflow_reports/',
]

function isUploadStorageKey(key: string): boolean {
  return UPLOAD_KEY_PREFIXES.some((prefix) => key.startsWith(prefix))
}

function isLikelyObjectStorageHost(parsed: URL): boolean {
  const host = parsed.hostname.toLowerCase()
  if (host === 'localhost' || host === '127.0.0.1') return true
  if (parsed.port === '9000') return true
  if (host.includes('minio')) return true
  if (host.includes('amazonaws.com')) return true
  return false
}

/**
 * Map legacy MinIO/S3 object URLs (internal endpoint) to same-origin /uploads proxy.
 * Path-style: http://host:9000/bucket/chat/abc.png → /uploads/chat/abc.png
 * Only rewrites URLs that look like our object storage, not arbitrary CDNs.
 */
export function rewriteObjectStorageUrl(url: string): string | null {
  try {
    const parsed = new URL(url)
    if (!isLikelyObjectStorageHost(parsed)) return null

    const parts = parsed.pathname.split('/').filter(Boolean)
    if (parts.length >= 2) {
      const key = parts.slice(1).join('/')
      if (!key || !isUploadStorageKey(key)) return null
      const proxied = `/uploads/${key}`
      return parsed.search ? `${proxied}${parsed.search}` : proxied
    }
    if (parts.length === 1 && isUploadStorageKey(parts[0])) {
      const proxied = `/uploads/${parts[0]}`
      return parsed.search ? `${proxied}${parsed.search}` : proxied
    }
  } catch {
    /* ignore */
  }
  return null
}

/** Turn API attachment paths into browser-loadable URLs (same origin or dev proxy). */
export function resolveUploadUrl(url?: string): string | undefined {
  if (!url) return undefined
  if (url.startsWith('blob:') || url.startsWith('data:')) return url
  if (url.startsWith('http://') || url.startsWith('https://')) {
    const proxied = rewriteObjectStorageUrl(url)
    if (proxied) return proxied
    return url
  }
  if (url.startsWith('/uploads/')) return url
  if (url.startsWith('/')) return url
  return `/uploads/${url}`
}

type AttachmentMeta = { url?: string; name?: string; mime?: string; pending?: boolean }
type OutboundAssetMeta = {
  url?: string
  name?: string
  mime?: string
  type?: string
  title?: string
  source?: string
}

export function normalizeMessageMedia(message: Message): Message {
  const attachments = message.extra_data?.attachments as AttachmentMeta[] | undefined
  const outboundAssets = message.extra_data?.outbound_assets as OutboundAssetMeta[] | undefined
  if (!attachments?.length && !outboundAssets?.length) return message

  return {
    ...message,
    extra_data: {
      ...message.extra_data,
      attachments: attachments?.map((att) => ({
        ...att,
        url: resolveUploadUrl(att.url),
      })),
      outbound_assets: outboundAssets?.map((asset) => ({
        ...asset,
        url: resolveUploadUrl(asset.url),
      })),
    },
  }
}
