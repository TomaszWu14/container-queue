import { useEffect, useState } from 'react'

// Zegar trzech stref w jednej linii: Radom (Europe/Warsaw), Chiny/Szanghaj (Asia/Shanghai)
// i Iberia (Europe/Lisbon) — „RAD 08:29 · SHA 14:29 · POR 07:29" (górny pasek 48 px).
const ZONES: [string, string][] = [
  ['RAD', 'Europe/Warsaw'], ['SHA', 'Asia/Shanghai'], ['POR', 'Europe/Lisbon'],
]

const hhmm = (tz: string, at: Date) =>
  new Intl.DateTimeFormat('pl-PL', { timeZone: tz, hour: '2-digit', minute: '2-digit' }).format(at)

export default function WorldClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="worldclock" title="Radom · Chiny (Szanghaj) · Iberia (Lizbona)">
      {ZONES.map(([label, tz], i) => (
        <span key={label} className="wc-zone">
          {i > 0 && <span className="wc-sep" aria-hidden="true">·</span>}
          <span className="wc-label">{label}</span> <span className="wc-time">{hhmm(tz, now)}</span>
        </span>
      ))}
    </div>
  )
}
