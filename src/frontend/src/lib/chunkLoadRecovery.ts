import { lazy, type ComponentType, type LazyExoticComponent } from 'react'

const CHUNK_RELOAD_KEY = 'mchat:chunk-reload-at'
const CHUNK_RELOAD_COOLDOWN_MS = 30_000

export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  const msg = error.message.toLowerCase()
  return (
    msg.includes('dynamically imported module') ||
    msg.includes('failed to fetch dynamically imported module') ||
    msg.includes('importing a module script failed') ||
    msg.includes('loading chunk') ||
    msg.includes('chunkloaderror')
  )
}

/** Reload once when a stale lazy chunk is missing after deploy. */
export function reloadOnceOnChunkError(): boolean {
  try {
    const last = sessionStorage.getItem(CHUNK_RELOAD_KEY)
    const now = Date.now()
    if (last && now - Number(last) < CHUNK_RELOAD_COOLDOWN_MS) {
      return false
    }
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(now))
  } catch {
    /* sessionStorage may be unavailable */
  }
  window.location.reload()
  return true
}

async function loadNamedExport<T extends Record<string, ComponentType<any>>>(
  loader: () => Promise<T>,
  name: keyof T,
): Promise<{ default: ComponentType<any> }> {
  try {
    const mod = await loader()
    return { default: mod[name] }
  } catch (error) {
    if (isChunkLoadError(error)) {
      reloadOnceOnChunkError()
    }
    throw error
  }
}

export function lazyNamed<T extends Record<string, ComponentType<any>>>(
  loader: () => Promise<T>,
  name: keyof T,
): LazyExoticComponent<ComponentType<any>> {
  return lazy(() => loadNamedExport(loader, name))
}

export function installChunkLoadRecovery(): void {
  if (typeof window === 'undefined') return

  window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    reloadOnceOnChunkError()
  })

  window.addEventListener('unhandledrejection', (event) => {
    if (isChunkLoadError(event.reason)) {
      event.preventDefault()
      reloadOnceOnChunkError()
    }
  })
}
