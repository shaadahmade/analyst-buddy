import { useState } from 'react'
import Icon from './Icon.jsx'

const KEY = 'analyst-theme'

function currentTheme() {
  const set = document.documentElement.dataset.theme
  if (set === 'light' || set === 'dark') return set
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(currentTheme)
  const next = theme === 'dark' ? 'light' : 'dark'

  function flip() {
    document.documentElement.dataset.theme = next
    try { localStorage.setItem(KEY, next) } catch {}
    setTheme(next)
  }

  return (
    <button type="button" className={`theme-toggle ${className}`} onClick={flip} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
    </button>
  )
}
