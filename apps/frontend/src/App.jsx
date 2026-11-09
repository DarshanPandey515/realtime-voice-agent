import { useState, useEffect, useRef } from 'react'
import { Mic, MicOff, Square, Zap, Sun, Moon, Activity, Radio, Trash2 } from 'lucide-react'

const BAR_COUNT = 48

function Visualizer({ active, level }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d')
    let raf
    const bars = new Array(BAR_COUNT).fill(0)
    const draw = () => {
      const w = canvas.width, h = canvas.height
      ctx.clearRect(0, 0, w, h)
      const bw = w / BAR_COUNT
      for (let i = 0; i < BAR_COUNT; i++) {
        const target = active ? level * (0.4 + 0.6 * Math.abs(Math.sin(i * 0.7 + Date.now() / 300))) : 0.04
        bars[i] += (target - bars[i]) * 0.25
        const bh = bars[i] * h * 0.9
        const g = ctx.createLinearGradient(0, h, 0, h - bh)
        g.addColorStop(0, '#22d3ee'); g.addColorStop(1, '#a78bfa')
        ctx.fillStyle = g
        ctx.fillRect(i * bw + 1, h - bh, bw - 2, bh)
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [active, level])
  return <canvas ref={ref} width={480} height={64} className="w-full h-16" />
}

export default function App() {
  const [dark, setDark] = useState(true)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('offline')
  const [transcript, setTranscript] = useState([])
  const [level, setLevel] = useState(0)
  const wsRef = useRef(null)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/audio')
    wsRef.current = ws
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      if (e.data instanceof Blob) return
      try {
        const d = JSON.parse(e.data)
        if (d.type === 'status') setStatus(d.state)
        else if (d.type === 'transcript') setTranscript(t => [...t, { text: d.text, final: d.is_final }])
        else if (d.type === 'session_started') setStatus('ready')
        else if (d.type === 'error') setStatus('error: ' + d.message)
      } catch {}
    }
    return () => ws.close()
  }, [])

  // Fake level animation when speaking
  useEffect(() => {
    const id = setInterval(() => setLevel(status === 'speaking' ? 0.5 + Math.random() * 0.5 : 0.05), 120)
    return () => clearInterval(id)
  }, [status])

  const send = (obj) => wsRef.current?.readyState === 1 && wsRef.current.send(JSON.stringify(obj))

  const accent = 'cyan'
  return (
    <div className={`min-h-screen font-sans transition-colors ${dark ? 'bg-[#05070f] text-slate-200' : 'bg-slate-100 text-slate-800'}`}>
      <div className="grid-bg absolute inset-0 pointer-events-none opacity-60" />
      <div className="relative max-w-3xl mx-auto p-6">
        {/* Header */}
        <header className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg ${dark ? 'bg-cyan-500/10 text-cyan-400' : 'bg-cyan-600/10 text-cyan-700'}`}>
              <Radio size={22} strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-xl font-extrabold tracking-widest uppercase">Voice Agent</h1>
              <p className="text-[11px] tracking-[0.3em] uppercase opacity-60">Realtime Interface</p>
            </div>
          </div>
          <button onClick={() => setDark(!dark)} className={`p-2.5 rounded-lg border transition-colors ${dark ? 'border-cyan-500/30 text-amber-300 hover:bg-cyan-500/10' : 'border-slate-300 text-slate-600 hover:bg-slate-200'}`}>
            {dark ? <Sun size={18} strokeWidth={2.5} /> : <Moon size={18} strokeWidth={2.5} />}
          </button>
        </header>

        {/* Status deck */}
        <section className={`relative rounded-2xl border p-5 mb-6 scanlines overflow-hidden ${dark ? 'border-cyan-500/20 bg-slate-900/70 backdrop-blur' : 'border-slate-300 bg-white'}`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span className={`relative flex h-3 w-3`}>
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${connected ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                <span className={`relative inline-flex rounded-full h-3 w-3 ${connected ? 'bg-emerald-400' : 'bg-rose-400'}`} />
              </span>
              <span className="text-xs font-semibold tracking-widest uppercase">{connected ? 'Link Active' : 'Link Down'}</span>
            </div>
            <span className={`text-xs font-bold tracking-widest uppercase px-3 py-1 rounded-full border ${status === 'speaking' ? 'border-violet-400/50 text-violet-300' : status === 'listening' ? 'border-cyan-400/50 text-cyan-300' : 'border-slate-500/40 opacity-70'}`}>
              {status}
            </span>
          </div>
          <Visualizer active={status === 'speaking' || status === 'listening'} level={level} />
          <div className="flex items-center gap-2 mt-3 text-[10px] tracking-[0.25em] uppercase opacity-50">
            <Activity size={12} /> 16kHz · PCM · Barge-in enabled
          </div>
        </section>

        {/* Controls */}
        <section className="grid grid-cols-3 gap-3 mb-6">
          <button onClick={() => send({ type: 'session_start' })} disabled={!connected}
            className="flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-sm tracking-wide uppercase transition-all disabled:opacity-40 bg-emerald-500 text-emerald-950 hover:brightness-110 glow-cyan">
            <Mic size={17} strokeWidth={2.6} /> Start
          </button>
          <button onClick={() => send({ type: 'session_stop' })} disabled={!connected}
            className="flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-sm tracking-wide uppercase transition-all disabled:opacity-40 bg-rose-500 text-rose-50 hover:brightness-110">
            <Square size={15} strokeWidth={2.6} /> Stop
          </button>
          <button onClick={() => send({ type: 'interrupt' })} disabled={!connected}
            className="flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-sm tracking-wide uppercase transition-all disabled:opacity-40 bg-amber-400 text-amber-950 hover:brightness-110 glow-amber">
            <Zap size={16} strokeWidth={2.6} /> Cut
          </button>
        </section>

        {/* Transcript */}
        <section className={`rounded-2xl border p-5 ${dark ? 'border-cyan-500/20 bg-slate-900/70 backdrop-blur' : 'border-slate-300 bg-white'}`}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold tracking-[0.3em] uppercase opacity-70">Transcript</h2>
            <button onClick={() => setTranscript([])} className="p-1.5 rounded-md opacity-50 hover:opacity-100 transition-opacity">
              <Trash2 size={14} strokeWidth={2.5} />
            </button>
          </div>
          <div className="h-64 overflow-y-auto space-y-2 pr-1">
            {transcript.length === 0 && <p className="text-sm opacity-40 italic">Awaiting transmission…</p>}
            {transcript.map((t, i) => (
              <div key={i} className={`text-sm px-3 py-2 rounded-lg border-l-2 ${t.final ? 'opacity-100' : 'opacity-50'}`}>
                {t.text}
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
