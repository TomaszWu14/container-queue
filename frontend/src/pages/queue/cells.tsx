// Drobne komórki i helpery wiersza kolejki (wyniesione z QueuePage.tsx).
import { formatDate } from '../../dates'
import { useT } from '../../i18n'
import { CopyButton } from '../../clipboard'
import type { Container } from '../../types'
import { splitMulti } from '../queueSummary'
import { ChevronDownIcon, ChevronRightIcon, Lock, LockOpen } from 'lucide-react'

// Q29: dopóki brak numeru kontenera, pokazujemy placeholder = ID transportu (np. TT-2026-0001)
export const idLabel = (c: Container) => c.container_no || c.transport_id || '—'

// ETA/ATD w jednej kolumnie (§10.2): dopóki nie ma ATD widać plan (ETA); po dostawie
// na wierzchu jest data rzeczywista, a ETA schodzi do drugiej linii jako odniesienie.
/** Pasek postępu rejsu: pozycja dzisiejszej daty między ETD (wypłynięcie z trackingu)
    a ETA portu. Rysowany tylko, gdy oba końce znane i rejs trwa/przed nami. */
function VoyageProgress({ c }: { c: Container }) {
  const t = useT()
  if (!c.etd || !c.eta || c.atd) return null
  const start = Date.parse(c.etd), end = Date.parse(c.eta)
  if (!(end > start)) return null
  const pct = Math.max(0, Math.min(100,
    Math.round(((Date.now() - start) / (end - start)) * 100)))
  // kolor wg postępu (design system / makieta): dobił ≥100 zielony, w drodze ≥70 niebieski, wcześnie szary
  const barColor = pct >= 100 ? '#2f7d54' : pct >= 70 ? '#0b5fff' : '#b9c7dc'
  return (
    <span className="voyage" title={`${t('etdCol')} ${formatDate(c.etd)} → ${t('eta')} ${formatDate(c.eta)} · ${pct}%`}>
      <span className="voyage-bar"><i style={{ width: `${pct}%`, background: barColor }} /></span>
      <small className="muted">{pct}%</small>
    </span>
  )
}

export function EtaCell({ c }: { c: Container }) {
  const t = useT()
  if (!c.atd && !c.eta && c.eta_estimate) {
    // D12: brak ETA z trackingu — szacunek z transit time, wyraźnie oznaczony
    return (
      <span className="nowrap eta-cell" title={t('etaEstimateHint')}>
        <span className="muted">~{formatDate(c.eta_estimate)}</span>
        <small className="muted">{t('etaEstimate')}</small>
      </span>
    )
  }
  if (!c.atd) {
    return (
      <span className="nowrap eta-cell">
        {formatDate(c.eta)}
        <VoyageProgress c={c} />
      </span>
    )
  }
  return (
    <span className="nowrap eta-cell" title={`${t('atd')} · ${t('eta')} ${formatDate(c.eta)}`}>
      <b className="atd-val">{formatDate(c.atd)}</b>
      <small className="muted">{t('eta')} {formatDate(c.eta)}</small>
    </span>
  )
}


export function LockIcon({ open }: { open: boolean }) {
  const I = open ? LockOpen : Lock
  return <I size={16} strokeWidth={2.2} aria-hidden="true" />
}



// 4a — komórka wielowartościowa. Klik w licznik nie może zaznaczyć wiersza (stopPropagation).
/** Unikalne numery w kolejności z danych (import bywa zdublowany — licznik liczy różne). */
export const uniqueMulti = (raw: string | null) => [...new Set(splitMulti(raw))]

/** Komórka wielu numerów (PO, nr dostaw). Numer zawsze od lewej krawędzi (równo z wierszami
 *  jednego numeru), licznik „› N” przyklejony do prawej; zwinięta pokazuje numer z filtra kolumny
 *  (`hits`), inaczej pierwszy. Rozwinięta: pełne numery, ⧉ przy każdym zawsze widoczne,
 *  „kopiuj wszystkie” (po jednym w linii) pod listą (2026-10-01). */
export function MultiCell({ raw, open, onToggle, copyable = false, hits }: {
  raw: string | null
  open: boolean
  onToggle: () => void
  copyable?: boolean
  hits?: readonly string[]   // wartości zaznaczone w filtrze kolumny
}) {
  const t = useT()
  const values = uniqueMulti(raw)
  if (values.length === 0) return <span className="muted">—</span>
  const hitSet = new Set(hits ?? [])
  const shown = open ? values : [values.find(v => hitSet.has(v)) ?? values[0]]
  return (
    <span className={`multi-cell${open ? ' open' : ''}`}>
      <span className="multi-values mono">
        {shown.map(v => (
          <span key={v} className={hitSet.has(v) ? 'multi-hit' : undefined}>
            {v}{copyable && <CopyButton text={v} />}
          </span>
        ))}
        {copyable && open && values.length > 1 && (
          <span className="multi-all"><CopyButton text={values.join('\n')} title={t('copyAll')} /> {t('copyAll')}</span>
        )}
      </span>
      {values.length > 1 && (
        <button type="button" className="multi-more" aria-expanded={open}
                title={open ? t('collapseValues') : t('expandValues')}
                onClick={e => { e.stopPropagation(); onToggle() }}>
          {open ? <ChevronDownIcon size={11} aria-hidden="true" /> : <ChevronRightIcon size={11} aria-hidden="true" />}
          {values.length}
        </button>
      )}
    </span>
  )
}
