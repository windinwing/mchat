import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Terminal as TerminalIcon, X } from 'lucide-react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { getToken } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'

interface ContainerTerminalProps {
  /** Managed sidecar container name to exec into. */
  containerName: string
  /** Shell to launch (default: bash). Backend falls back to sh if missing. */
  shell?: string
  onClose: () => void
}

type ConnState = 'connecting' | 'connected' | 'closed'

/**
 * Full-screen overlay terminal (xterm.js) backed by the admin-only
 * `/ws/exec` WebSocket. Binary frames carry stdin/stdout; small JSON
 * frames carry resize/ping/exit/control. Mirrors a k8s console exec.
 */
export function ContainerTerminal({ containerName, shell = 'bash', onClose }: ContainerTerminalProps) {
  const { t } = useTranslation()
  const termRef = useRef<HTMLDivElement | null>(null)
  const termInstanceRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<ConnState>('connecting')
  // Bumped by the Reconnect button to force the connect effect to tear down
  // and re-run (new Terminal + new WebSocket), since containerName/shell are
  // unchanged on reconnect.
  const [attempt, setAttempt] = useState(0)

  // ESC closes the overlay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (!termRef.current) return
    let disposed = false
    setState('connecting')

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      theme: {
        background: '#1e1e2e',
        foreground: '#cdd6f4',
        cursor: '#f5e0dc',
        selectionBackground: '#585b7066',
      },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(termRef.current)
    fit.fit()
    termInstanceRef.current = term
    fitRef.current = fit

    const encoder = new TextEncoder()

    // Build the ws URL (wss when served over https).
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const params = new URLSearchParams({
      token: getToken() || '',
      container: containerName,
      shell,
      cols: String(term.cols),
      rows: String(term.rows),
    })
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/exec?${params}`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    const sendResize = () => {
      if (ws.readyState !== WebSocket.OPEN) return
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }

    const sendStdin = (data: string) => {
      if (ws.readyState !== WebSocket.OPEN) return
      ws.send(encoder.encode(data))
    }

    // xterm user input → container stdin (binary frame)
    const inputDisp = term.onData(sendStdin)
    // resize → notify backend so stty stays in sync
    const resizeDisp = term.onResize(sendResize)
    // window resize → refit + notify
    const onWinResize = () => {
      try {
        fit.fit()
      } catch {
        /* ignore before attach */
      }
    }
    window.addEventListener('resize', onWinResize)

    ws.onopen = () => {
      if (disposed) return
      setState('connected')
      sendResize()
      term.focus()
    }
    ws.onmessage = (ev) => {
      if (disposed) return
      if (typeof ev.data === 'string') {
        // control frame
        try {
          const ctrl = JSON.parse(ev.data)
          if (ctrl.type === 'exit') {
            term.write(`\r\n\x1b[33m[process exited ${ctrl.code}]\x1b[0m\r\n`)
            setState('closed')
          } else if (ctrl.type === 'error') {
            term.write(`\r\n\x1b[31m[error: ${ctrl.message}]\x1b[0m\r\n`)
            toast(`${ctrl.message}`, { type: 'error' })
          }
        } catch {
          /* ignore malformed control */
        }
      } else if (ev.data instanceof ArrayBuffer) {
        // binary stdout frame
        term.write(new Uint8Array(ev.data))
      }
    }
    ws.onerror = () => {
      if (disposed) return
      toast(t('workspace.shellConnectFailed'), { type: 'error' })
    }
    ws.onclose = () => {
      if (disposed) return
      setState((s) => (s === 'connected' ? 'closed' : s))
    }

    return () => {
      disposed = true
      inputDisp.dispose()
      resizeDisp.dispose()
      window.removeEventListener('resize', onWinResize)
      try {
        ws.close()
      } catch {
        /* noop */
      }
      term.dispose()
      termInstanceRef.current = null
      fitRef.current = null
      wsRef.current = null
    }
  }, [containerName, shell, t, attempt])

  const handleReconnect = () => {
    setState('connecting')
    setAttempt((n) => n + 1)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex w-full max-w-5xl flex-col overflow-hidden rounded-lg bg-[#1e1e2e] shadow-2xl ring-1 ring-black/40">
        {/* Title bar */}
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
          <div className="flex items-center gap-2 text-sm text-gray-200">
            <TerminalIcon className="h-4 w-4" />
            <span className="font-medium">{t('workspace.shellTitle', { container: containerName })}</span>
            <span className="ml-2 text-xs text-gray-400">
              {state === 'connecting' && `· ${t('workspace.shellConnecting')}`}
              {state === 'connected' && `· ${t('workspace.shellConnected')}`}
              {state === 'closed' && `· ${t('workspace.shellDisconnected')}`}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {state === 'closed' && (
              <Button size="sm" variant="outline" onClick={handleReconnect}>
                {t('workspace.shellReconnect')}
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={onClose} className="text-gray-300 hover:text-white">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {/* Terminal surface */}
        <div ref={termRef} className="h-[70vh] w-full bg-[#1e1e2e] p-2" />
        <div className="border-t border-white/10 px-4 py-1.5 text-right text-[11px] text-gray-500">
          {t('workspace.shellHint')}
        </div>
      </div>
    </div>
  )
}
