import Header from './components/Header'
import Hero from './components/Hero'
import Controls from './components/Controls'
import Transcript from './components/Transcript'
import { useTheme } from './hooks/useTheme'
import { useVoiceAgent } from './hooks/useVoiceAgent'

export default function App() {
  const { dark, toggle } = useTheme()
  const { connected, status, messages, level, send, clear } = useVoiceAgent()

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg)', color: 'var(--ink)' }}>
      <div className="page">
        <Header dark={dark} connected={connected} onToggleTheme={toggle} />
        <main className="space-y-6 pb-16">
          <Hero status={status} level={level} dark={dark} />
          <Controls
            disabled={!connected}
            onStart={() => send({ type: 'session_start' })}
            onStop={() => send({ type: 'session_stop' })}
            onInterrupt={() => send({ type: 'interrupt' })}
          />
          <Transcript messages={messages} onClear={clear} />
        </main>
      </div>
    </div>
  )
}