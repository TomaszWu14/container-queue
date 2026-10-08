// Znacznik głównego transportu (morski / lotniczy / kolej; koła / inne ze starych danych) — jedna
// grafika w całej appce (kolejka, szuflada, karta kontenera, filtr, formularz). Styl z PR #630.
// Obrys w currentColor, kolor i tło daje klasa .tr-badge--<typ> (05-status-pages.css, tokeny --tr-*).
import type { ReactNode } from 'react'
import { useT } from './i18n'
import type { Container } from './types'

export type TransportType = NonNullable<Container['transport_type']>
export type OnCarriage = NonNullable<Container['on_carriage']>
export const TRANSPORT_TYPES: TransportType[] = ['morski', 'lotniczy', 'kolej', 'kola', 'inne']
/** Dowóz po odprawie (hub/port → magazyn) — ta sama pigułka, własne ikony. */
export const ON_CARRIAGE_TYPES: OnCarriage[] = ['drogowo', 'intermodal']

const TRUCK = <><rect x="1.5" y="5.5" width="13.5" height="9" rx=".6" /><path d="M5.5 5.5v9M9.5 5.5v9M15 8.5h3.6l3 3.5v3.5H15zM1.5 16.5h20" />
  <circle cx="5" cy="18.4" r="1.6" /><circle cx="9.6" cy="18.4" r="1.6" /><circle cx="18.5" cy="18.4" r="1.6" /></>

const TRANSPORT_ICON: Record<TransportType | OnCarriage, ReactNode> = {
  drogowo: TRUCK,
  // kontener + przeładunek w obie strony (kolej ⇄ drogowo)
  intermodal: <><rect x="3" y="3.5" width="18" height="8.5" rx=".6" /><path d="M8 3.5V12M12 3.5V12M16 3.5V12" />
    <path d="M4 15.5h15.5M17.3 13.3l2.4 2.2-2.4 2.2M20 20.5H4.5M6.7 18.3l-2.4 2.2 2.4 2.2" /></>,
  morski: <><path d="M2.5 13.5h19l-2.8 4.5H5.3z" /><rect x="5.5" y="9" width="4.5" height="4.5" /><rect x="10" y="9" width="4.5" height="4.5" />
    <path d="M17 13.5V7.5h2.5v6M1.5 21.3c1.7 0 1.7-1 3.4-1s1.7 1 3.4 1 1.7-1 3.4-1 1.7 1 3.4 1 1.7-1 3.4-1 1.7 1 3.4 1" /></>,
  lotniczy: <path d="M21 4.2c-.7-.7-2.3-.4-3.3.6L14.5 8 5.8 5.6 4 7.4l7 3.8-3.4 3.5-2.7-.3L3.5 15.8l3.3 1.4 1.4 3.3 1.4-1.4-.3-2.7 3.5-3.4 3.8 7 1.8-1.8L16 9.5l3.2-3.2c1-1 1.3-2.6.6-3.3z" />,
  kola: TRUCK,
  kolej: <><rect x="3" y="5.5" width="18" height="8.5" rx=".6" /><path d="M8 5.5v8.5M12 5.5v8.5M16 5.5v8.5M1.5 16h21M1.5 21.8h21" />
    <circle cx="6.5" cy="18.6" r="1.7" /><circle cx="17.5" cy="18.6" r="1.7" /></>,
  inne: <><rect x="2.5" y="6" width="19" height="11" rx=".8" /><path d="M7 6v11M12 6v11M17 6v11" strokeDasharray="1.6 2" /></>,
}

/** Pigułka: ikona + nazwa w kolorze trybu. `sm` = tabele (ikona 15px, jak w #630), `md` = karty (20px). */
export function TransportBadge({ type, size = 'sm' }: { type: TransportType | OnCarriage; size?: 'sm' | 'md' }) {
  const t = useT()
  const name = t(`transport_${type}`)
  const px = size === 'md' ? 20 : 15
  return (
    <span className={`tr-badge tr-badge--${type}${size === 'md' ? ' tr-badge--md' : ''}`}
          role="img" aria-label={name} title={name}>
      <svg viewBox="0 0 24 24" width={px} height={px} aria-hidden="true">{TRANSPORT_ICON[type]}</svg>
      {name}
    </span>
  )
}

/** Wybór trybu przyciskami z pigułką (natywny select nie pokaże ikon). Klik w wybrany = wyczyść (''). */
export function TransportPick({ value, onChange, label }: {
  value: string; onChange: (v: string) => void; label: string
}) {
  return (
    <div className="tr-pick" role="group" aria-label={label}>
      {TRANSPORT_TYPES.map(v => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(value === v ? '' : v)}>
          <TransportBadge type={v} />
        </button>
      ))}
    </div>
  )
}
