/** Mobile / in-app browser detection for widget UX. */

export function isWeChatBrowser(): boolean {
  if (typeof navigator === 'undefined') return false
  return /MicroMessenger/i.test(navigator.userAgent)
}

export function isHarmonyOS(): boolean {
  if (typeof navigator === 'undefined') return false
  return /HarmonyOS|OpenHarmony|ArkWeb/i.test(navigator.userAgent)
}

export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false
  return /iPhone|iPad|iPod/i.test(navigator.userAgent)
}

export function isTouchMobile(): boolean {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia('(pointer: coarse)').matches ||
    /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)
  )
}

export function isMediaRecorderSupported(): boolean {
  return typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined'
}

/** Best-effort MIME for MediaRecorder across WeChat / iOS / Android. */
export function pickRecorderMimeType(): string | undefined {
  if (!isMediaRecorderSupported()) return undefined
  const preferMp4First = isWeChatBrowser() || isIOS()
  const candidates = preferMp4First
    ? ['audio/mp4', 'audio/aac', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/ogg;codecs=opus']
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return undefined
}

export function recorderFileExtension(mimeType: string | undefined): string {
  if (!mimeType) return 'webm'
  if (mimeType.includes('mp4')) return 'm4a'
  if (mimeType.includes('aac')) return 'aac'
  if (mimeType.includes('ogg')) return 'ogg'
  return 'webm'
}

/** CSS value for bottom safe area (browser chrome / home indicator). */
export const safeAreaBottom = 'env(safe-area-inset-bottom, 0px)'
