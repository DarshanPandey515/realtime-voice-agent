import { Sun, Moon } from 'lucide-react'

export default function ThemeToggle({ dark, onToggle }) {
  return (
    <button onClick={onToggle} aria-label="Toggle theme" className="btn-icon">
      {dark ? <Sun size={17} strokeWidth={2.4} /> : <Moon size={17} strokeWidth={2.4} />}
    </button>
  )
}