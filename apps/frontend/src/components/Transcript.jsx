import { useEffect, useRef } from 'react'
import { Trash2, Bot, User } from 'lucide-react'

export default function Transcript({ messages, onClear }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages])

  return (
    <section className="panel">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="heading">Transcript</h2>
        <button onClick={onClear} aria-label="Clear transcript" className="btn-icon">
          <Trash2 size={15} strokeWidth={2.4} />
        </button>
      </div>
      <div ref={ref} className="scroll h-72 space-y-2 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <p className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>
            Awaiting transmission
          </p>
        ) : (
          messages.map((message, index) => (
            <div key={index} className={`msg ${message.partial ? 'msg-partial' : ''}`}>
              <span className="msg-icon">
                {message.role === 'agent' ? (
                  <Bot size={15} strokeWidth={2.4} />
                ) : (
                  <User size={15} strokeWidth={2.4} />
                )}
              </span>
              <span className="text-pretty">{message.text}</span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}