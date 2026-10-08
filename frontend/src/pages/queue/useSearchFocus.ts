// Wybór podpowiedzi wyszukiwarki → pokaż rekord w kolejce (2026-09-25).
// Kontener: rozwiń jego grupę dnia i sekcję planowania, rozwiń wiersz, przewiń i podświetl;
// gdy nie ma go w bieżącym widoku — zawęź kolejkę do numeru (cały zakres, bez filtrów),
// a jeśli i wtedy go nie ma (np. archiwum) — karta kontenera.
// PO / statek / dostawca: filtr pokazujący wszystkie pasujące kontenery, przewinięcie do pierwszego.
import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react'
import type { NavigateFunction } from 'react-router-dom'
import type { Container } from '../../types'
import { splitByPlanning } from '../queueRows'
import type { RowGroup } from './enterprise'
import type { Suggestion } from './SearchSuggest'
import { NO_FILTERS } from './useQueueFilters'
import { scrollBehavior } from '../../motion'

type Pending = { id: number | null; wait: Container[] | null }   // wait = czekaj na nową listę

export function useSearchFocus(p: {
  containers: Container[]; loading: boolean; groups: RowGroup[]
  collapsed: Set<string>; setCollapsed: Dispatch<SetStateAction<Set<string>>>
  collapsedPlanning: string[]; togglePlanSection: (status: string) => void
  searchParams: URLSearchParams; patchParams: (patch: Record<string, string>) => void
  setExpandedId: (id: number | null) => void; navigate: NavigateFunction
}) {
  const pending = useRef<Pending | null>(null)
  const latest = useRef(p)
  latest.current = p

  // rozwija zwiniętą grupę/sekcję z kontenerem; false = kontenera nie ma w widoku
  const reveal = (id: number) => {
    const { groups, collapsed, setCollapsed, collapsedPlanning, togglePlanSection } = latest.current
    const g = groups.find(x => x.items.some(c => c.id === id))
    if (!g) return false
    if (collapsed.has(g.key)) setCollapsed(prev => { const n = new Set(prev); n.delete(g.key); return n })
    const sec = splitByPlanning(g.items).find(s => s.items.some(c => c.id === id))
    if (sec && collapsedPlanning.includes(sec.status)) togglePlanSection(sec.status)
    return true
  }

  // opóźnione przewinięcie/podświetlenie; odmontowanie kolejki (np. przejście na kartę) je kasuje,
  // żeby nie sięgać do DOM strony, która już zniknęła
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>())
  useEffect(() => {
    const pendingTimers = timers.current
    return () => { pendingTimers.forEach(clearTimeout); pendingTimers.clear() }
  }, [])
  const later = (fn: () => void, ms: number) => {
    const t = setTimeout(() => { timers.current.delete(t); fn() }, ms)
    timers.current.add(t)
  }

  // przewinięcie po wyrenderowaniu rozwiniętej grupy (id null = pierwszy wiersz listy)
  const scrollTo = (id: number | null) => later(() => {
    const el = document.querySelector(id == null ? '.kq-row[data-cid]' : `[data-cid="${id}"]`)
    if (!el) return
    el.scrollIntoView({ block: 'center', behavior: scrollBehavior() })
    el.classList.add('flash')
    later(() => el.classList.remove('flash'), 2000)
  }, 60)

  const focusNow = (id: number | null) => {
    if (id == null) { scrollTo(null); return true }
    if (!reveal(id)) return false
    latest.current.setExpandedId(id)
    scrollTo(id)
    return true
  }

  // zmiana filtrów = nowe pobranie listy; fokus dopiero na nowych danych
  const filterAndFocus = (patch: Record<string, string>, id: number | null) => {
    const { searchParams, patchParams, containers } = latest.current
    const full = { ...NO_FILTERS, widok: '', moje: '', 'pod-klienta': '', okres: 'all', ...patch }
    const changed = Object.entries(full).some(([k, v]) => (searchParams.get(k) ?? '') !== v)
    if (!changed) { if (!focusNow(id) && id != null) latest.current.navigate(`/kontenery/${id}`); return }
    pending.current = { id, wait: containers }
    patchParams(full)
  }

  useEffect(() => {
    const cur = pending.current
    if (!cur || p.loading || cur.wait === p.containers) return
    pending.current = null
    if (!focusNow(cur.id) && cur.id != null) p.navigate(`/kontenery/${cur.id}`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.containers, p.loading])

  return (s: Suggestion) => {
    if (s.type === 'container') {
      if (!focusNow(s.container_id)) filterAndFocus({ szukaj: s.container_no }, s.container_id)
    } else if (s.type === 'supplier' && s.supplier_id != null) {
      filterAndFocus({ dostawca: String(s.supplier_id) }, null)
    } else {
      filterAndFocus({ szukaj: s.label }, null)   // PO i statek — wyszukiwanie ogólne kolejki je obejmuje
    }
  }
}
