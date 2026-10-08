import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useT } from '../../i18n'
import { formatDate, formatDateTime, parseServerTs } from '../../dates'
import { orderByStage } from './timelineOrder'

export type TimelineEntry = {
  kind: string; code: string; title: string; location: string
  at: string | null; estimated: boolean; source: string
}

const KEYED: Record<string, string> = {   // kody z tłumaczeniem w i18n
  ETD: 'etdCol', ETA: 'eta', ATD: 'atd', NOTIFY: 'notifyDate',
  DEMURRAGE: 'demurrageEnd',   // szczegóły (start +N d) niesie pole location
}

const DATE_ONLY = new Set(['planned', 'order'])
// A24: backend podaje okno wolnych dni neutralnie językowo („2026-07-23 +5d”) — na osi pokazujemy
// datę jak w całej aplikacji (dd.mm.rrrr) i odmienione dni („od 23.07.2026 + 5 dni”)
const FREE_DAYS = /^(\d{4}-\d{2}-\d{2}) \+(\d+)d$/

export default function ContainerTimeline({ containerId, refreshKey = 0, entries: given }:
    { containerId: number; refreshKey?: number; entries?: TimelineEntry[] }) {
  const t = useT()
  const [fetched, setFetched] = useState<TimelineEntry[]>([])
  useEffect(() => {
    if (given) return
    let alive = true
    api.get<TimelineEntry[]>(`/api/containers/${containerId}/timeline`)
      .then(e => { if (alive) setFetched(Array.isArray(e) ? e : []) }).catch(() => {})
    return () => { alive = false }
  }, [containerId, refreshKey, given])
  // oś czasu domyka minione wpisy względem „teraz” — bez tyknięcia strona otwarta
  // na stałe (dyspozytor trzyma ją cały dzień) zamraża „teraz” na moment wejścia.
  // ponytail: minuta wystarczy, wpisy mają rozdzielczość minutową.
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  const entries = orderByStage(given ?? fetched)
  if (entries.length === 0) return <p style={{ color: 'var(--muted)' }}>{t('noEvents')}</p>
  const sub = (en: TimelineEntry) => {
    const m = en.code === 'DEMURRAGE' ? en.location.match(FREE_DAYS) : null
    if (!m) return en.location
    const n = Number(m[2])   // pl/en/pt: liczba pojedyncza tylko dla 1 (1 dzień, 2/5/22 dni)
    return `${t('ctFreeFrom').replace('{date}', formatDate(m[1]))} ${
      t(n === 1 ? 'ctFreeDays_one' : 'ctFreeDays').replace('{n}', String(n))}`
  }
  const label = (en: TimelineEntry) => {
    if (en.kind === 'carrier') {
      const k = `ev_${en.code}`
      const tr = t(k)
      return tr === k ? en.title : tr
    }
    return KEYED[en.code] ? t(KEYED[en.code]) : en.title
  }
  return (
    <ol className="ctimeline">
      {entries.map((en, i) => {
        const done = !en.estimated && !!en.at && parseServerTs(en.at).getTime() <= nowMs
        return (
          <li key={i} className={`k-${en.kind} ${done ? 'done' : en.estimated ? 'est' : ''}`}>
            <span className="ct-dot" aria-hidden="true" />
            {/* terminy planowane/zamówień to same daty — godzina „02:00" była przesunięciem strefy północy */}
            <span className="ct-when mono">{!en.at ? '—' : DATE_ONLY.has(en.kind) ? formatDate(en.at) : formatDateTime(en.at)}</span>
            <span className="ct-label">
              {label(en)}
              {en.estimated && <span className="muted"> ({t('estimated')})</span>}
            </span>
            {en.location && <span className="ct-sub muted">{sub(en)}</span>}
          </li>
        )
      })}
    </ol>
  )
}
