// Pełny ekran z górnego paska (prośba 2026-09-30): włącz / wyłącz. Stan z przeglądarki (fullscreenchange),
// więc F11/Esc też odświeżają ikonę. Brak Fullscreen API (np. osadzona ramka) → przycisku nie ma.
import { useEffect, useState } from 'react'
import { Maximize, Minimize } from 'lucide-react'
import { useT } from './i18n'

export default function FullscreenToggle() {
  const t = useT()
  const [on, setOn] = useState(() => !!document.fullscreenElement)
  useEffect(() => {
    const sync = () => setOn(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  if (!document.fullscreenEnabled) return null
  const label = t(on ? 'fsExit' : 'fsEnter')
  const toggle = () => {
    const done = on ? document.exitFullscreen() : document.documentElement.requestFullscreen()
    done.catch(() => { /* przeglądarka odmówiła (np. bez gestu) — stan zostaje */ })
  }
  return (
    <button type="button" className="tn-icon-btn tn-fullscreen" onClick={toggle}
            title={label} aria-label={label} aria-pressed={on}>
      {on ? <Minimize size={16} aria-hidden="true" /> : <Maximize size={16} aria-hidden="true" />}
    </button>
  )
}
