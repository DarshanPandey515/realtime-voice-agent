import { useState, useEffect, useRef, useCallback } from 'react'
import { Mic, Square, Zap, Sun, Moon, Radio, AudioLines, Trash2, Bot, User } from 'lucide-react'

const BAR_COUNT = 56

function Visualizer({ level }) {
  const ref = useRef(null)
  const levelRef = useRef(level)
  levelRef.current = level
  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d')
    let raf
    const bars = new Float32Array(BAR_COUNT)
    const draw = () => {
      const w = canvas.width, h = canvas.height
      ctx.clearRect(0, 0, w, h)
      const bw = w / BAR_COUNT
      const t = Date.now() / 1000
      for (let i = 0; i < BAR_COUNT; i++) {
        const wave = Math.abs(Math.sin(i * 0.45 + t * 2.2)) * Math.abs(Math.sin(i * 0.13 - t * 1.4))
        const target = 0.05 + levelRef.current * wave
        bars[i] += (target - bars[i]) * 0.22
        const bh = Math.max(3, bars[i] * h * 0.92)
        const g = ctx.createLinearGradient(0, h, 0, h - bh)
        g.addColorStop(0, '#0891b2'); g.addColorStop(0.6, '#22d3ee'); g.addColorStop(1, '#34d399')
        ctx.fillStyle = g
        ctx.fillRect(i * bw + 1.5, h - bh, bw - 3, bh)
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])
  return <canvas ref={ref} width={640} height={72} className="w-full h-[72px] block" />
}

const STATUS_META = {
  offline:  { label: 'Offline',    cls: '' },
  ready:    { label: 'Ready',      cls: 'live' },
  listening:{ label: 'Listening',  cls: 'listening' },
  thinking: { label: 'Thinking',   cls: '' },
  speaking: { label: 'Speaking',   cls: 'speaking' },
}

export default function App() {
  const [dark, setDark] = useState(true)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('offline')
  const [messages, setMessages] = useState([])
  const [level, setLevel] = useState(0)
  const wsRef = useRef(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/audio`)
    wsRef.current = ws
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => setConnected(true)
    ws.onclose = () => { setConnected(false); setStatus('offline') }
    ws.onerror = () => setStatus('error')
    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer || e.data instanceof Blob) return // TTS PCM, handled by audio pipeline later
      try {
        const d = JSON.parse(e.data)
        if (d.type === 'status') setStatus(d.state || d.status || 'ready')
        else if (d.type === 'transcript') {
          setMessages(m => {
            const next = [...m]
            if (d.is_final) next.push({ role: d.speaker === 'agent' ? 'agent' : 'user', text: d.text })
            else {
              const last = next[next.length - 1]
              if (last && last.partial) next[next.length - 1] = { ...last, text: d.text }
              else next.push({ role: d.speaker === 'agent' ? 'agent' : 'user', text: d.text, partial: true })
            }
            return next.slice(-100)
          })
        }
        else if (d.type === 'session_started') setStatus('ready')
        else if (d.type === 'session_ended') setStatus('offline')
        else if (d.type === 'error') setStatus('error')
      } catch {}
    }
    return () => ws.close()
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      const speaking = status === 'speaking' || status === 'listening'
      setLevel(speaking ? 0.35 + Math.random() * 0.6 : 0.03)
    }, 110)
    return () => clearInterval(id)
  }, [status])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = useCallback((obj) => {
    if (wsRef.current?.readyState === 1) wsRef.current.send(JSON.stringify(obj))
  }, [])

  const meta = STATUS_META[status] || STATUS_META.offline
  const dotColor = connected ? '#34d399' : '#f43f5e'

  return (
    <div className="min-h-screen relative overflow-hidden">
      <div className="grid-bg absolute inset-0 pointer-events-none" />
      <div className="absolute inset-x-0 top-0 h-72 pointer-events-none" style={{ background: 'radial-gradient(ellipse 60% 100% at 50% -20%, color-mix(in srgb, var(--accent) 14%, transparent), transparent)' }} />

      <div className="relative max-w-3xl mx-auto px-5 py-8 sm:py-10">
        {/* Header */}
        <header className="rise flex items-center justify-between mb-8">
          <div className="flex items-center gap-3.5">
            <div className="panel-inset p-3" style={{ color: 'var(--accent)' }}>
              <AudioLines size={22} strokeWidth={2.2} />
            </div>
            <div>
              <h1 className="text-lg font-extrabold tracking-[0.18em] uppercase leading-none">Voice Agent</h1>
              <p className="text-[10px] font-semibold tracking-[0.32em] uppercase mt-1" style={{ color: 'var(--ink-dim)' }}>Realtime Console</p>
            </div>
          </div>
          <button
            onClick={() => setDark(!dark)}
            className="btn btn-ghost !p-3 !rounded-xl"
            aria-label="Toggle theme"
          >
            {dark ? <Sun size={17} strokeWidth={2.4} /> : <Moon size={17} strokeWidth={2.4} />}
          </button>
        </header>

        {/* Hero / status panel */}
        <section className="panel rise rise-1 p-6 sm:p-7 mb-5 relative overflow-hidden">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <div className="flex items-center gap-2.5 mb-2">
                <span className="dot" style={{ background: dotColor, color: dotColor }} />
                <span className="text-xs font-bold tracking-[0.22em] uppercase" style={{ color: connected ? '#34d399' : '#f43f5e' }}>
                  {connected ? 'Link Active' : 'Link Down'}
                </span>
              </div>
              <p className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                {status === 'speaking' ? <span className="text-glow" style={{ color: '#fbbf24' }}>Agent is speaking</span>
                 : status === 'listening' ? <span style={{ color: 'var(--accent)' }}>Listening…</span>
                 : status === 'thinking' ? 'Processing'
                 : status === 'ready' ? 'Standing by'
                 : 'Voice Agent'}
              </p>
            </div>
            <span className={`chip ${meta.cls}`}>{meta.label}</span>
          </div>

          <Visualizer level={level} />

          <div className="flex items-center gap-2 mt-4 text-[10px] font-semibold tracking-[0.25em] uppercase" style={{ color: 'var(--ink-dim)' }}>
            <Radio size={12} strokeWidth={2.5} />
            16 kHz · PCM · Deepgram → Groq → ElevenLabs
          </div>
        </section>

        {/* Controls */}
        <section className="rise rise-2 grid grid-cols-3 gap-3 mb-5">
          <button onClick={() => send({ type: 'session_start' })} disabled={!connected} className="btn btn-primary">
            <Mic size={16} strokeWidth={2.6} /> Start
          </button>
          <button onClick={() => send({ type: 'session_stop' })} disabled={!connected} className="btn btn-danger">
            <Square size={14} strokeWidth={2.6} /> Stop
          </button>
          <button onClick={() => send({ type: 'interrupt' })} disabled={!connected} className="btn btn-warn">
            <Zap size={15} strokeWidth={2.6} /> Interrupt
          </button>
        </section>

        {/* Transcript */}
        <section className="panel rise rise-3 p-5 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-extrabold tracking-[0.3em] uppercase" style={{ color: 'var(--ink-dim)' }}>Transcript</h2>
            <button onClick={() => setMessages([])} className="p-2 rounded-lg transition-colors hover:bg-[var(--surface-2)]" style={{ color: 'var(--ink-dim)' }} aria-label="Clear transcript">
              <Trash2 size={15} strokeWidth={2.4} />
            </button>
          </div>
          <div ref={scrollRef} className="scroll h-72 overflow-y-auto space-y-2.5 pr-1">
            {messages.length === 0 && (
              <p className="text-sm italic" style={{ color: 'var(--ink-dim)' }}>Awaiting transmission…</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg flex gap-2.5 ${m.role === 'agent' ? 'msg-agent' : 'msg-user'} ${m.partial ? 'msg-partial' : ''}`}>
                <span className="mt-0.5 flex-none" style={{ color: m.role === 'agent' ? '#34d399' : 'var(--accent)' }}>
                  {m.role === 'agent' ? <Bot size={15} strokeWidth={2.4} /> : <User size={15} strokeWidth={2.4} />}
                </span>
                <span>{m.text}</span>
              </div>
            ))}
          </div>
        </section>

        <footer className="rise rise-4 mt-8 text-center text-[10px] font-semibold tracking-[0.3em] uppercase" style={{ color: 'var(--ink-dim)' }}>
          Voice Agent Orchestrator · Realtime Pipeline
        </footer>
      </div>
    </div>
  )
}
