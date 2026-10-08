// Widok roku kalendarza awizacji: 12 kafelków miesięcy z liczbą kontenerów (łącznie + per
// magazyn, kolory magazynów jak w kolejce) i mini-kalendarzem z intensywnością wg liczby
// kontenerów dnia (skala względna do maksimum roku). Dane: jeden agregat /api/calendar/year.
import { useContext } from 'react'
import { holidayName } from '../../holidays'
import { LangContext, localeFor, useT } from '../../i18n'
import { monthWeeks } from './calModel'

export type YearAgg = { year: number; today: string; days: { day: string; warehouse: string | null; count: number }[] }

const NONE = ''   // klucz „Bez magazynu"

// dzień → magazyn → liczba (po filtrze magazynu; '' w filtrze = wszystkie)
export function yearIndex(agg: YearAgg | null, filter = ''): Map<string, Map<string, number>> {
  const out = new Map<string, Map<string, number>>()
  for (const r of agg?.days ?? []) {
    const key = (r.warehouse ?? NONE).toUpperCase()
    if (filter && key !== filter) continue
    const m = out.get(r.day) ?? new Map<string, number>()
    m.set(key, (m.get(key) ?? 0) + r.count)
    out.set(r.day, m)
  }
  return out
}

const sum = (m?: Map<string, number>) => [...(m?.values() ?? [])].reduce((s, n) => s + n, 0)
// poziom intensywności 0–4 względem maksimum roku
export const heat = (n: number, max: number) => (n && max ? Math.max(1, Math.ceil((n / max) * 4)) : 0)

export default function YearView({ year, agg, filter, onYear, onOpen }: {
  year: number; agg: YearAgg | null; filter: string
  onYear: (delta: number) => void; onOpen: (month: number, iso?: string) => void
}) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const weekdays = [t('mo'), t('tu'), t('we'), t('th'), t('fr'), t('sa'), t('su')]
  const idx = yearIndex(agg, filter)
  const max = Math.max(0, ...[...idx.values()].map(sum))
  const today = agg?.today ?? ''
  return (
    <>
      <div className="cal2-bar cal2-bar-year">
        <button onClick={() => onYear(-1)} aria-label={t('prevYear')}>‹</button>
        <div className="cal2-bar-name mono">{year}</div>
        <button onClick={() => onYear(1)} aria-label={t('nextYear')}>›</button>
      </div>
      <div className="cal2-legend muted">
        <span>{t('calContainersLbl')}: {t('calHeatLess')}</span>
        {[1, 2, 3, 4].map(h => <i key={h} className={`cal2-ym-day lg-heat h-${h}`} />)}
        <span>{t('calHeatMore')} (max {max})</span>
      </div>
      <div className="cal2-year">
        {Array.from({ length: 12 }, (_, m) => {
          const cells = monthWeeks(year, m).flat()
          const byWh = new Map<string, number>()
          for (const iso of cells) if (iso) for (const [k, n] of idx.get(iso) ?? []) byWh.set(k, (byWh.get(k) ?? 0) + n)
          const total = sum(byWh)
          const keys = [...byWh.keys()].filter(k => k !== NONE).sort().reverse()
          if (byWh.has(NONE)) keys.push(NONE)
          const name = new Date(Date.UTC(year, m, 1)).toLocaleDateString(localeFor(lang), { month: 'long', timeZone: 'UTC' })
          const current = today.slice(0, 7) === `${year}-${String(m + 1).padStart(2, '0')}`
          return (
            <div key={m} className={`cal2-ym${current ? ' current' : ''}`} aria-current={current ? 'date' : undefined}>
              <button type="button" className="cal2-ym-head" onClick={() => onOpen(m)}>
                <b className="cal2-ym-name">{name} <span className="mono muted">{year}</span></b>
                <span className="cal2-ym-total"><b className="mono">{total}</b> {t('calContainersLbl')}</span>
              </button>
              <div className="cal2-ym-whs">
                {keys.map(k => (
                  <span key={k || 'none'} className={`cal2-ym-wh ${k ? `wh-${k.toLowerCase()}` : 'none'}`}>
                    {k || t('calNoWarehouse')} <b className="mono">{byWh.get(k)}</b>
                  </span>
                ))}
              </div>
              <div className="cal2-ym-grid">
                {weekdays.map(w => <span key={w} className="cal2-ym-wd">{w}</span>)}
                {cells.map((iso, i) => {
                  if (!iso) return <span key={i} />
                  const n = sum(idx.get(iso))
                  const hol = holidayName(iso)
                  return (
                    <button key={iso} type="button" title={`${iso} — ${t('calContainersLbl')}: ${n}${hol ? ` (${hol})` : ''}`}
                            className={`cal2-ym-day mono h-${heat(n, max)}${hol ? ' hol' : ''}${iso === today ? ' today' : ''}`}
                            onClick={() => onOpen(m, iso)}>
                      {Number(iso.slice(8, 10))}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
