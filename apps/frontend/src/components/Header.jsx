import { AudioLines } from 'lucide-react'
import ThemeToggle from './ThemeToggle'

export default function Header({ dark, connected, onToggleTheme }) {
  return (
    <header className="flex items-center justify-between py-5">
      <div className="flex items-center gap-2.5">
        <AudioLines size={20} strokeWidth={2.2} style={{ color: 'var(--ink)' }} />
        <span className="text-sm font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--ink)' }}>
          Voice Agent
        </span>
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: connected ? 'var(--ink)' : 'var(--muted)' }}
        />
      </div>
      <ThemeToggle dark={dark} onToggle={onToggleTheme} />
    </header>
  )
}