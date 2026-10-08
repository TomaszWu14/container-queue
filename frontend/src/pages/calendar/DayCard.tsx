// Karta dnia kalendarza awizacji: pierścień obłożenia (n / pojemność), wiersz per magazyn
// z kropkami slotów (zajęty / wolny / ponad limit), opóźnienia, wolne sloty, odprawy, statki.
import { useT } from '../../i18n'
import { type DayStat, tone } from './calModel'

export function Donut({ n, cap, size = 52 }: { n: number; cap: number; size?: number }) {
  const r = size / 2 - 5
  const len = 2 * Math.PI * r
  const p = cap ? Math.min(1, n / cap) : n ? 1 : 0
  return (
    <svg className={`cal2-donut t-${tone(n, cap)}`} width={size} height={size} viewBox={`0 0 ${size} ${size}`}
         role="img" aria-label={`${n} / ${cap}`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="trk" />
      <circle cx={size / 2} cy={size / 2} r={r} className="val" strokeDasharray={`${p * len} ${len}`}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="47%" className="n">{n}</text>
      <text x="50%" y="70%" className="c">/{cap}</text>
    </svg>
  )
}

export function Dots({ n, limit, wh }: { n: number; limit: number; wh: string }) {
  const cells = Math.max(n, limit)
  return (
    <span className="cal2-dots" aria-hidden="true">
      {Array.from({ length: cells }, (_, i) => (
        <i key={i} className={i >= limit ? 'over' : i < n ? `on wh-${wh.toLowerCase()}` : ''} />
      ))}
    </span>
  )
}

const WEEKDAY_KEYS = ['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su']

export default function DayCard({ iso, s, holiday, selected, today, onSelect }: {
  iso: string; s: DayStat; holiday: string | null; selected: boolean; today: boolean
  onSelect: (iso: string) => void
}) {
  const t = useT()
  const day = Number(iso.slice(8, 10))
  // dzień tygodnia — widoczny tylko na telefonie, gdzie siatka jest listą bez wiersza PN…ND
  const dow = WEEKDAY_KEYS[(new Date(`${iso}T00:00:00`).getDay() + 6) % 7]
  const cls = `cal2-day${s.closed ? ' closed' : ''}${selected ? ' sel' : ''}${today ? ' today' : ''}`
  return (
    <div className={cls} role="button" tabIndex={0} aria-pressed={selected} aria-label={iso}
         onClick={() => onSelect(iso)}
         onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(iso) } }}>
      <div className="cal2-top">
        <span className="mono cal2-num">{day}</span>
        <span className="cal2-dow">{t(dow)}</span>
        {s.closed ? <span className="cal2-tag">{holiday ?? t('calWeekend')}</span>
          : s.late > 0 && <span className="cal2-late">{s.late} {t('calLate')}</span>}
      </div>
      {s.closed ? (
        <div className="cal2-closed-note">{t('calClosedWh')}</div>
      ) : (
        <div className="cal2-body">
          <Donut n={s.total} cap={s.cap} />
          <div className="cal2-whs">
            {s.byWh.map(w => (
              <div key={w.key} className="cal2-wh">
                <span className="cal2-wh-name">{w.key} <b className="mono">{w.n}/{w.limit}</b></span>
                <Dots n={w.n} limit={w.limit} wh={w.key} />
              </div>
            ))}
          </div>
        </div>
      )}
      {!s.closed && (s.over > 0
        ? <span className="cal2-chip over">+{s.over} {t('calOver')}</span>
        : s.free > 0 && <span className="cal2-chip free">{t('calFreeShort')} {s.free}</span>)}
      <div className="cal2-foot mono">
        {!s.closed && <span>{t('calCustoms')} <b>{s.customsOpen}</b></span>}
        {!s.closed && s.revision > 0 && <span className="rev">{t('calRevision')} <b>{s.revision}</b></span>}
        {s.vessels > 0 && <span>{t('calVessels')} <b>{s.vessels}</b></span>}
        {s.closed && s.toPort > 0 && <span>{t('calToPort')} <b>{s.toPort}</b></span>}
      </div>
    </div>
  )
}
