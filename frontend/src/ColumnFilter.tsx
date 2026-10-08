// #5 — jeden komponent filtra kolumny (list / text / range), reużywalny (m.in. #17 Spedycja).
// Wartość trzymana przez rodzica w URL (useQueryParam) — komponent jest prezentacyjny.
import { useEffect, useRef, useState } from 'react'
import { CalendarDays } from 'lucide-react'

// Zamknięcie menu/popovera: Escape / klik poza / scroll. Jeden hook zamiast
// powielania tego samego efektu w każdym miejscu z menu kontekstowym (QueuePage,
// filtr zakresu dat). closeRef trzyma najświeższy callback, więc subskrybujemy
// tylko przy zmianie open (nie co render).
export function useDismiss(open: boolean, close: () => void) {
  const closeRef = useRef(close)
  closeRef.current = close
  useEffect(() => {
    if (!open) return
    const onClose = () => closeRef.current()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current() }
    window.addEventListener('click', onClose)
    window.addEventListener('scroll', onClose, true)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', onClose)
      window.removeEventListener('scroll', onClose, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])
}

export type FilterOption = { value: string; label: string }

type ListProps = {
  variant: 'list'; value: string; onChange: (v: string) => void; label: string
  options: FilterOption[]; allowEmpty?: boolean; emptyLabel?: string
}
type TextProps = { variant: 'text'; value: string; onChange: (v: string) => void; label: string }
type RangeProps = {
  variant: 'range'; from: string; to: string
  onFrom: (v: string) => void; onTo: (v: string) => void; label: string
}

export function ColumnFilter(props: ListProps | TextProps | RangeProps) {
  if (props.variant === 'list') {
    const { value, onChange, label, options, allowEmpty, emptyLabel } = props
    return (
      <span className="hdr-filter-wrap">
        {/* decyzja 14 — placeholder-as-label gubi kontekst, gdy wybrana wartość go zastępuje */}
        {value && <span className="hdr-filter-lbl">{label}</span>}
        <select className={`hdr-filter${value ? ' set' : ''}`} value={value} title={label}
                onChange={e => onChange(e.target.value)} onClick={e => e.stopPropagation()}>
          <option value="">{label}</option>
          {allowEmpty && <option value="empty">{emptyLabel}</option>}
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </span>
    )
  }
  if (props.variant === 'text') return <TextFilter {...props} />
  return <RangeFilter {...props} />
}

// tekst z debounce — nie strzelamy zapytaniem na każdy znak
function TextFilter({ value, onChange, label }: TextProps) {
  const [local, setLocal] = useState(value)
  useEffect(() => setLocal(value), [value])   // reset z zewnątrz (np. „wyczyść filtry")
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const push = (v: string) => {
    setLocal(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onChange(v), 350)
  }
  return (
    <span className="hdr-filter-wrap">
      {value && <span className="hdr-filter-lbl">{label}</span>}
      <input className={`hdr-filter${value ? ' set' : ''}`} value={local} placeholder={label}
             title={label} onChange={e => push(e.target.value)} onClick={e => e.stopPropagation()} />
    </span>
  )
}

// decyzja 7 — jeden przycisk „📅 od–do", pola dat rozwijane po kliknięciu (popover
// zamykany jak inne menu w kolejce: Escape / klik poza / scroll).
function RangeFilter({ from, to, onFrom, onTo, label }: RangeProps) {
  const [open, setOpen] = useState(false)
  useDismiss(open, () => setOpen(false))
  return (
    <span className={`hdr-range${from || to ? ' set' : ''}`} onClick={e => e.stopPropagation()}>
      <button type="button" className={`hdr-filter hdr-range-btn${from || to ? ' set' : ''}`}
              title={label} onClick={() => setOpen(v => !v)}>
        <CalendarDays size={16} aria-hidden="true" /> {from || '…'}–{to || '…'}
      </button>
      {open && (
        <span className="hdr-range-pop">
          <input type="date" className="hdr-filter" value={from} aria-label={`${label} od`}
                 onChange={e => onFrom(e.target.value)} />
          <input type="date" className="hdr-filter" value={to} aria-label={`${label} do`}
                 onChange={e => onTo(e.target.value)} />
        </span>
      )}
    </span>
  )
}
