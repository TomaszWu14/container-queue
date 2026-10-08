// Wyszukiwarka kolejki z podpowiedziami (2026-09-24): /api/search/suggest od 2 znaków,
// debounce 250 ms + anulowanie poprzedniego żądania, max 50 znaków (wklejka normalizowana
// i przycinana + komunikat), klawiatura ↑↓/Enter/Esc, ARIA combobox/listbox.
import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../../api'
import { formatDate } from '../../dates'
import { useT } from '../../i18n'
import { Anchor, Container, Factory, Hash, type LucideIcon } from 'lucide-react'

export type Suggestion = {
  type: 'container' | 'po' | 'vessel' | 'supplier'; label: string; container_id: number
  container_no: string; notify_date: string | null; warehouse: string | null; vessel: string | null
  supplier_id: number | null
}

export const MAX_Q = 50
const MIN_Q = 2
const TYPE_KEY: Record<Suggestion['type'], string> = {
  container: 'sugContainer', po: 'sugPo', vessel: 'sugVessel', supplier: 'sugSupplier',
}
const TYPE_ICON: Record<Suggestion['type'], LucideIcon> = { container: Container, po: Hash, vessel: Anchor, supplier: Factory }

// wklejka: nowe linie/tabulatory → spacja, wielokrotne spacje → jedna, trim
export const normalizeQuery = (s: string) => s.replace(/\s+/g, ' ').trim()

// pogrubienie pasującego fragmentu — dzielenie stringu, bez regexu z danych i bez innerHTML
function Mark({ text, q }: { text: string; q: string }) {
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (!q || i < 0) return <>{text}</>
  return <>{text.slice(0, i)}<b>{text.slice(i, i + q.length)}</b>{text.slice(i + q.length)}</>
}

export default function SearchSuggest({ value, onChange, onPick, placeholder, completed }: {
  value: string
  onChange: (v: string) => void
  onPick: (s: Suggestion) => void
  placeholder: string
  completed?: boolean   // kolejka = false, archiwum = true (jak lista kontenerów)
}) {
  const t = useT()
  const listId = useId()
  const [items, setItems] = useState<Suggestion[] | null>(null)   // null = lista zamknięta
  const [sel, setSel] = useState(0)
  const [trimmed, setTrimmed] = useState(false)
  const q = normalizeQuery(value)
  // wybór podpowiedzi wpisuje etykietę/numer do pola — ta zmiana nie otwiera listy ponownie
  const quiet = useRef<string[]>([])

  useEffect(() => {
    if (q.length < MIN_Q || quiet.current.includes(q)) { quiet.current = []; setItems(null); return }
    quiet.current = []
    const ctrl = new AbortController()
    const params = new URLSearchParams({ q })
    if (completed !== undefined) params.set('completed', String(completed))
    const id = setTimeout(() => {
      api.get<Suggestion[]>(`/api/search/suggest?${params}`, ctrl.signal)
        .then(r => { setItems(r); setSel(0) })
        .catch(() => { if (!ctrl.signal.aborted) setItems(null) })
    }, 250)
    // nowy znak = stare żądanie anulowane (spóźniona odpowiedź nie nadpisze listy)
    return () => { clearTimeout(id); ctrl.abort() }
  }, [q, completed])

  useEffect(() => {
    if (!trimmed) return
    const id = setTimeout(() => setTrimmed(false), 3000)
    return () => clearTimeout(id)
  }, [trimmed])

  const pick = (s: Suggestion) => {
    quiet.current = [normalizeQuery(s.label), s.container_no]
    setItems(null)
    onPick(s)
  }
  const optId = (i: number) => `${listId}-o${i}`

  return (
    <div className="qsearch-wrap">
      <input type="text" className="qsearch" aria-label={placeholder} placeholder={placeholder} value={value} maxLength={MAX_Q}
             role="combobox" aria-expanded={!!items} aria-controls={listId} aria-autocomplete="list"
             aria-activedescendant={items?.[sel] ? optId(sel) : undefined}
             onChange={e => { quiet.current = []; onChange(e.target.value) }}
             onPaste={e => {
               const raw = e.clipboardData.getData('text')
               const clean = normalizeQuery(raw)
               const el = e.currentTarget
               const start = el.selectionStart ?? value.length
               const end = el.selectionEnd ?? value.length
               const room = MAX_Q - (value.length - (end - start))
               if (clean === raw && raw.length <= room) return   // zwykła wklejka — przeglądarka
               e.preventDefault()
               quiet.current = []
               onChange((value.slice(0, start) + clean.slice(0, Math.max(room, 0)) + value.slice(end)).slice(0, MAX_Q))
               setTrimmed(clean.length > room)
             }}
             onBlur={() => setTimeout(() => setItems(null), 150)}   // klik w podpowiedź zdąży przed zamknięciem
             onKeyDown={e => {
               if (!items) return
               if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)) }
               else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
               else if (e.key === 'Enter' && items[sel]) { e.preventDefault(); pick(items[sel]) }
               else if (e.key === 'Escape') { e.stopPropagation(); setItems(null) }
             }} />
      {trimmed && (
        <span className="qsearch-note" role="status">{t('searchTrimmed').replace('{n}', String(MAX_Q))}</span>
      )}
      {items && (
        <ul className={`qsuggest${trimmed ? ' below-note' : ''}`} id={listId} role="listbox" aria-label={placeholder}>
          {items.length === 0 && <li className="qsuggest-empty">{t('sugNone').replace('{q}', q)}</li>}
          {items.map((s, i) => (
            <li key={`${s.type}-${s.container_id}-${s.label}`} id={optId(i)} role="option" aria-selected={i === sel}
                className={i === sel ? 'sel' : ''}
                onMouseDown={e => { e.preventDefault(); pick(s) }} onMouseEnter={() => setSel(i)}>
              <span className={`qsuggest-type t-${s.type}`}>
                {(() => { const I = TYPE_ICON[s.type]; return <I size={16} aria-hidden="true" /> })()} {t(TYPE_KEY[s.type])}
              </span>
              <span className="qsuggest-label mono"><Mark text={s.label} q={q} /></span>
              <span className="qsuggest-meta muted">
                {s.type !== 'container' && `${s.container_no} · `}
                {s.notify_date ? formatDate(s.notify_date) : '—'}{s.warehouse && ` · ${s.warehouse}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
