import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type HermesChatConfigResponse } from '../lib/api'
import { useI18n } from '../lib/i18n'

type ConnectionState = 'idle' | 'connecting' | 'connected' | 'closed' | 'error'

function channelId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `opc-chat-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`
}

function wsUrl(config: HermesChatConfigResponse, resume: string | null, channel: string) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const qs = new URLSearchParams({ token: config.token, channel })
  if (resume) qs.set('resume', resume)
  return `${proto}//${window.location.host}${config.pty_path}?${qs.toString()}`
}

const terminalTheme = {
  background: '#071516',
  foreground: '#e7edf0',
  cursor: '#67e8f9',
  cursorAccent: '#071516',
  selectionBackground: '#3b82f655',
  black: '#0f172a',
  red: '#f87171',
  green: '#34d399',
  yellow: '#facc15',
  blue: '#60a5fa',
  magenta: '#c084fc',
  cyan: '#22d3ee',
  white: '#e5e7eb',
}

export default function HermesChat() {
  const { lang } = useI18n()
  const [searchParams] = useSearchParams()
  const resume = searchParams.get('resume')
  const hostRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [config, setConfig] = useState<HermesChatConfigResponse | null>(null)
  const [state, setState] = useState<ConnectionState>('idle')
  const [error, setError] = useState('')
  const [instance, setInstance] = useState(0)
  const channel = useMemo(() => channelId(), [instance, resume])

  const fit = useCallback(() => {
    const fitAddon = fitRef.current
    const terminal = terminalRef.current
    const ws = wsRef.current
    if (!fitAddon || !terminal) return
    try {
      fitAddon.fit()
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(`\x1b[RESIZE:${terminal.cols};${terminal.rows}]`)
      }
    } catch {
      /* Layout may not be ready yet. */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api.hermesChatConfig()
      .then((next) => {
        if (cancelled) return
        setConfig(next)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e.message)
        setState('error')
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!config || !hostRef.current) return
    if (!config.enabled || !config.token) {
      setError(lang === 'zh' ? 'Hermes Chat 未启用或缺少 WS token。' : 'Hermes Chat is not enabled or the WS token is missing.')
      setState('error')
      return
    }

    setState('connecting')
    setError('')
    hostRef.current.innerHTML = ''

    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.12,
      scrollback: 8000,
      theme: terminalTheme,
      allowProposedApi: false,
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(hostRef.current)
    terminal.focus()
    terminal.writeln('\x1b[90mConnecting to Hermes PTY...\x1b[0m')

    terminalRef.current = terminal
    fitRef.current = fitAddon

    let raf1 = requestAnimationFrame(() => {
      raf1 = 0
      fit()
    })

    const socket = new WebSocket(wsUrl(config, resume, channel))
    socket.binaryType = 'arraybuffer'
    wsRef.current = socket

    socket.onopen = () => {
      setState('connected')
      fit()
    }

    socket.onmessage = (event) => {
      if (typeof event.data === 'string') {
        terminal.write(event.data)
      } else {
        terminal.write(new Uint8Array(event.data as ArrayBuffer))
      }
    }

    socket.onerror = () => {
      setState('error')
      setError(lang === 'zh' ? 'WebSocket 连接失败。' : 'WebSocket connection failed.')
    }

    socket.onclose = (event) => {
      wsRef.current = null
      if (event.code === 4401) {
        setState('error')
        setError(lang === 'zh' ? 'Chat WebSocket 认证失败。' : 'Chat WebSocket auth failed.')
        return
      }
      if (event.code === 4403) {
        setState('error')
        setError(lang === 'zh' ? 'Chat 只允许本机访问。' : 'Chat is only available from localhost.')
        return
      }
      if (event.code !== 1000 && event.code !== 1005 && event.code !== 1011) {
        setState('error')
        setError(`WebSocket closed: ${event.code}`)
        return
      }
      setState('closed')
      terminal.writeln('\r\n\x1b[90m[session ended]\x1b[0m')
    }

    // eslint-disable-next-line no-control-regex
    const sgrMouse = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/
    const inputDisposable = terminal.onData((data) => {
      if (sgrMouse.test(data)) return
      if (socket.readyState === WebSocket.OPEN) socket.send(data)
    })
    const resizeDisposable = terminal.onResize(({ cols, rows }) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(`\x1b[RESIZE:${cols};${rows}]`)
    })

    const resizeObserver = new ResizeObserver(() => fit())
    resizeObserver.observe(hostRef.current)
    window.addEventListener('resize', fit)

    return () => {
      if (raf1) cancelAnimationFrame(raf1)
      inputDisposable.dispose()
      resizeDisposable.dispose()
      resizeObserver.disconnect()
      window.removeEventListener('resize', fit)
      socket.close()
      terminal.dispose()
      if (wsRef.current === socket) wsRef.current = null
      if (terminalRef.current === terminal) terminalRef.current = null
      if (fitRef.current === fitAddon) fitRef.current = null
    }
  }, [channel, config, fit, lang, resume])

  const reconnect = () => setInstance((value) => value + 1)

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold">{lang === 'zh' ? 'Hermes Chat' : 'Hermes Chat'}</h2>
          <p className="mt-1 max-w-3xl text-sm text-opc-text-2">
            {resume
              ? (lang === 'zh' ? `恢复会话：${resume}` : `Resuming session: ${resume}`)
              : (lang === 'zh' ? '原生 Hermes TUI，经 PTY/WebSocket 嵌入 OPC-Hermes。' : 'Native Hermes TUI embedded through PTY/WebSocket.')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={state === 'connected' ? 'badge-success' : state === 'error' ? 'badge-error' : 'badge-info'}>{state}</span>
          <button className="btn-secondary text-xs" onClick={reconnect}>{lang === 'zh' ? '重连' : 'Reconnect'}</button>
          <Link className="btn-secondary text-xs" to="/sessions">{lang === 'zh' ? '会话列表' : 'Sessions'}</Link>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 rounded-lg border border-opc-border bg-[#071516] p-2 shadow-inner">
        <div ref={hostRef} className="h-[calc(100vh-13rem)] min-h-[520px] overflow-hidden rounded bg-[#071516]" />
      </div>
    </div>
  )
}
