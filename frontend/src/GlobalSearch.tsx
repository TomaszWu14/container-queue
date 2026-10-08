import { ShipIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import { useT } from './i18n'
import type { Container } from './types'

/** Paleta Ctrl+K: kontener / PO / statek z dowolnego ekranu → skok do celu.
    Reużywa /api/containers?q= (ILIKE po numerze, PO, statku, uwagach). */
export default function GlobalSearch() {
  const t = useT()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Container[]>([])
  const [sel, setSel] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const seq = useRef(0)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) { setQ(''); setResults([]); setSel(0); setTimeout(() => inputRef.current?.focus(), 0) }
  }, [open])

  const search = useCallback((term: string) => {
    const my = ++seq.current
    if (term.trim().length < 2) { setResults([]); return }
    api.get<Container[]>(`/api/containers?q=${encodeURIComponent(term.trim())}&limit=8`)
      // seq odrzuca spóźnione odpowiedzi wcześniejszych zapytań (race przy szybkim pisaniu)
      .then(r => { if (my === seq.current) { setResults(r); setSel(0) } })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const id = setTimeout(() => search(q), 250)   // debounce
    return () => clearTimeout(id)
  }, [q, search])

  const go = (c: Container) => { setOpen(false); navigate(`/kontenery/${c.id}`) }

  if (!open) return null
  return (
    <div className="gs-backdrop" onClick={() => setOpen(false)}>
      <div className="gs-panel" role="dialog" aria-label={t('globalSearch')}
           onClick={e => e.stopPropagation()}>
        <input ref={inputRef} className="gs-input" value={q}
               aria-label={t('globalSearchHint')} placeholder={t('globalSearchHint')}
               onChange={e => setQ(e.target.value)}
               onKeyDown={e => {
                 if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, results.length - 1)) }
                 if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
                 if (e.key === 'Enter' && results[sel]) go(results[sel])
               }} />
        {results.length > 0 && (
          <ul className="gs-results">
            {results.map((c, i) => (
              <li key={c.id} className={i === sel ? 'active' : ''}
                  onMouseEnter={() => setSel(i)} onClick={() => go(c)}>
                <b className="mono">{c.container_no}</b>
                <span className="muted"> · {c.supplier_name || '—'}
                  {c.vessel && <> · <ShipIcon size={12} /> {c.vessel}</>}</span>
                <span className={`badge st-${c.status}`}>{t(`st_${c.status}`)}</span>
              </li>
            ))}
          </ul>
        )}
        {q.trim().length >= 2 && results.length === 0 && (
          <div className="gs-empty muted">{t('globalSearchEmpty')}</div>
        )}
        <div className="gs-hint muted">↑↓ · Enter · Esc</div>
      </div>
    </div>
  )
}
