import { Mic, Square, Zap } from 'lucide-react'

export default function Controls({ disabled, onStart, onStop, onInterrupt }) {
  return (
    <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <button onClick={onStart} disabled={disabled} className="btn btn-primary">
        <Mic size={16} strokeWidth={2.6} /> Start
      </button>
      <button onClick={onStop} disabled={disabled} className="btn btn-outline">
        <Square size={14} strokeWidth={2.6} /> Stop
      </button>
      <button onClick={onInterrupt} disabled={disabled} className="btn btn-outline">
        <Zap size={15} strokeWidth={2.6} /> Interrupt
      </button>
    </section>
  )
}