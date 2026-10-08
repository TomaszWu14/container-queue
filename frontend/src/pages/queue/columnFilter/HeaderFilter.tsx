import { FunnelIcon } from 'lucide-react'
// Lejek w nagłówku kolumny + panel „jak w Excelu": Szukaj, (Zaznacz wszystko), unikalne wartości
// z licznikami, OK / Anuluj / Wyczyść filtr. Panel w portalu (position: fixed) — nie przycina go
// przewijany kontener tabeli ani przyklejony nagłówek. Lista liczona raz, przy otwarciu.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, RefObject } from 'react'
import { createPortal } from 'react-dom'
import { useT } from '../../../i18n'
import type { Container } from '../../../types'
import { applyColFilters, columnValues, EMPTY, initialChecked, toFilter } from './values'
import type { ColFilter, ColFilters } from './values'

export interface ColFilterCtx {
  rows: Container[]          // wiersze bieżącego zakresu PRZED filtrami kolumn
  filters: ColFilters
  set: (col: string, v: ColFilter | null) => void
  today: string
}

const LIST_LIMIT = 500   // ponytail: tyle checkboxów naraz; więcej → zawężenie wyszukiwaniem
type Pos = { top: number; left: number }

export default function HeaderFilter({ col, label, ctx }: { col: string; label: string; ctx: ColFilterCtx }) {
  const t = useT()
  const [pos, setPos] = useState<Pos | null>(null)
  const btn = useRef<HTMLButtonElement>(null)
  const active = !!ctx.filters[col]
  const close = useCallback((refocus: boolean) => { setPos(null); if (refocus) btn.current?.focus() }, [])
  return (
    <>
      <button ref={btn} type="button" className={`kq-hf-btn${active ? ' on' : ''}`}
              aria-label={`${t('cfFilterBy')}: ${label}`} title={`${t('cfFilterBy')}: ${label}`}
              aria-haspopup="dialog" aria-expanded={!!pos}
              onClick={e => {
                e.stopPropagation()   // klik w lejek nie sortuje
                if (pos) { setPos(null); return }
                const r = e.currentTarget.getBoundingClientRect()
                setPos({ top: r.bottom + 4, left: Math.max(8, Math.min(r.left, window.innerWidth - 296)) })
              }}>
        <FunnelIcon size={12} aria-hidden="true" fill={active ? 'currentColor' : 'none'} />
      </button>
      {pos && createPortal(<Panel col={col} label={label} ctx={ctx} pos={pos} close={close} anchor={btn} />, document.body)}
    </>
  )
}

function Panel({ col, label, ctx, pos, close, anchor }: {
  col: string; label: string; ctx: ColFilterCtx; pos: Pos; close: (refocus: boolean) => void
  anchor: RefObject<HTMLButtonElement | null>
}) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  // kaskada jak w Excelu: wartości z wierszy po POZOSTAŁYCH filtrach kolumn
  const [opts] = useState(() =>
    columnValues(col, applyColFilters(ctx.rows, ctx.filters, ctx.today, col), ctx.today, t))
  const [checked, setChecked] = useState(() => initialChecked(ctx.filters[col], opts))
  const [q, setQ] = useState('')
  const name = (label: string) => label || t('cfEmpty')
  const needle = q.trim().toLocaleLowerCase('pl')
  const matching = needle ? opts.filter(o => name(o.label).toLocaleLowerCase('pl').includes(needle)) : opts
  const allOn = matching.length > 0 && matching.every(o => checked.has(o.key))
  // z wyszukiwaniem (jak w Excelu) OK bierze tylko zaznaczone wyniki wyszukiwania
  const effective = needle ? new Set(matching.filter(o => checked.has(o.key)).map(o => o.key)) : checked

  useEffect(() => {
    // klik / przewinięcie poza panelem = Anuluj (przewijanie listy w panelu go nie zamyka;
    // klik w sam lejek obsługuje jego onClick — inaczej zamknięcie i od razu ponowne otwarcie)
    const outside = (e: Event) => {
      const target = e.target as Node
      if (!ref.current?.contains(target) && !anchor.current?.contains(target)) close(false)
    }
    document.addEventListener('pointerdown', outside, true)
    window.addEventListener('scroll', outside, true)
    window.addEventListener('resize', outside)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      window.removeEventListener('scroll', outside, true)
      window.removeEventListener('resize', outside)
    }
  }, [close, anchor])

  const toggle = (key: string) => setChecked(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key); else next.add(key)
    return next
  })
  const toggleAll = () => setChecked(prev => {
    const next = new Set(prev)
    matching.forEach(o => (allOn ? next.delete(o.key) : next.add(o.key)))
    return next
  })
  const apply = () => {
    if (effective.size === 0) return
    ctx.set(col, toFilter(effective, opts))
    close(true)
  }

  // Escape zamyka, Tab krąży w panelu (focus trap), strzałki chodzą po liście
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); return }
    const all = [...(ref.current?.querySelectorAll<HTMLElement>('input, button:not(:disabled)') ?? [])]
    if (e.key === 'Tab' && all.length) {
      const i = all.indexOf(document.activeElement as HTMLElement)
      const next = e.shiftKey ? (i <= 0 ? all.length - 1 : i - 1) : (i === all.length - 1 ? 0 : i + 1)
      e.preventDefault(); all[next].focus()
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const boxes = [...(ref.current?.querySelectorAll<HTMLElement>('.kq-hf-list input') ?? [])]
      const i = boxes.indexOf(document.activeElement as HTMLElement)
      if (i < 0 && e.key === 'ArrowUp') return
      e.preventDefault()
      boxes[Math.max(0, Math.min(boxes.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus()
    }
  }

  return (
    <div ref={ref} className="kq-hf-pop" role="dialog" aria-label={`${t('cfFilterBy')}: ${label}`}
         style={{ top: pos.top, left: pos.left, maxHeight: `calc(100vh - ${pos.top + 8}px)` }}
         onKeyDown={onKey} onClick={e => e.stopPropagation()}>
      <input type="search" className="kq-hf-search" aria-label={t('cfSearch')} placeholder={t('cfSearch')}
             autoFocus value={q} onChange={e => setQ(e.target.value)}
             onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); apply() } }} />
      <div className="kq-hf-list">
        {opts.length === 0 ? <p className="kq-hf-note">{t('cfNone')}</p> : (
          <label className="kq-hf-all">
            <input type="checkbox" checked={allOn} onChange={toggleAll}
                   ref={el => { if (el) el.indeterminate = !allOn && matching.some(o => checked.has(o.key)) }} />
            {t('cfSelectAll')}
          </label>
        )}
        {matching.slice(0, LIST_LIMIT).map(o => (
          <label key={o.key} className={o.key === EMPTY ? 'kq-hf-empty' : undefined}>
            <input type="checkbox" checked={checked.has(o.key)} onChange={() => toggle(o.key)} />
            <span className="kq-hf-val">{name(o.label)}</span>
            <small className="kq-hf-n mono">{o.count}</small>
          </label>
        ))}
        {matching.length > LIST_LIMIT && (
          <p className="kq-hf-note">{t('cfMore').replace('{n}', String(LIST_LIMIT)).replace('{m}', String(matching.length))}</p>
        )}
      </div>
      <div className="kq-hf-actions">
        <button type="button" className="btn small secondary" disabled={!ctx.filters[col]}
                onClick={() => { ctx.set(col, null); close(true) }}>{t('cfClear')}</button>
        <span className="spacer" />
        <button type="button" className="btn small secondary" onClick={() => close(true)}>{t('cfCancel')}</button>
        <button type="button" className="btn small" disabled={effective.size === 0} onClick={apply}>{t('cfOk')}</button>
      </div>
    </div>
  )
}
