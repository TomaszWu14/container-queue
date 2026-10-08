// Preferencje widoku kolejki per użytkownik (localStorage/prefs, nie URL): grupowanie,
// zapisane widoki, sort, rozwinięte komórki i obserwowane kontenery. Wyniesione z QueuePage.tsx.
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { setPref } from '../../prefs'
import type { Container } from '../../types'
import { SORT_ACCESSOR } from './config'
import { applyOrder, DEFAULT_ORDER, moveBeside, moveStep, ORDER_KEY, readColumns, readDense, readOrder,
  toggleColumn, visibleColumns, writeColumns, writeDense } from './columns'
import type { GroupBy, SortKey } from './config'

export interface SavedView {
  name: string
  search: string
  groupBy?: GroupBy
  columns?: string[] | null
  order?: string[] | null   // kolejność kolumn (widoki sprzed tej zmiany jej nie mają — bez zmian)
  dense?: boolean
}

const toggled = <T,>(prev: Set<T>, v: T) => {
  const next = new Set(prev)
  if (next.has(v)) next.delete(v)
  else next.add(v)
  return next
}

const NONE: ReadonlySet<string> = new Set()

export function useViewPrefs(roleHidden: ReadonlySet<string> = NONE) {
  // zwinięcie sekcji planowania pamiętane między wejściami — filtr „zaplanowane/nie" to te same przyciski
  const [collapsedPlanning, setCollapsedPlanning] = useState<string[]>(() => {
    // uszkodzony wpis nie może wywalić całej kolejki
    try {
      const raw = JSON.parse(localStorage.getItem('queueCollapsedPlanning') ?? '[]')
      return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === 'string') : []
    } catch { return [] }
  })
  const togglePlanSection = (status: string) => setCollapsedPlanning(prev => {
    const next = prev.includes(status) ? prev.filter(x => x !== status) : [...prev, status]
    setPref('queueCollapsedPlanning', JSON.stringify(next))
    return next
  })
  // Kolejka Enterprise: Grupuj Dzień (weekday) / Etap (status) / Magazyn — domyślnie Dzień
  const [groupBy, setGroupByState] = useState<GroupBy>(() => {
    const saved = localStorage.getItem('queueGroupBy')
    return saved === 'warehouse' || saved === 'status' ? saved : 'weekday'
  })
  const setGroupBy = (g: GroupBy) => {
    setGroupByState(g); localStorage.setItem('queueGroupBy', g)
  }
  // 4a — rozwinięte komórki PO / nr dostaw, klucz „<id>:<kolumna>" (w pamięci sesji)
  const [openCells, setOpenCells] = useState<Set<string>>(new Set())
  const toggleCell = (key: string) => setOpenCells(prev => toggled(prev, key))
  // „rozwiń wszystkie” w nagłówku kolumny (2026-10-01) — pamiętane w przeglądarce;
  // przełączenie kolumny czyści jej pojedyncze rozwinięcia (komórka = kolumna XOR własny klik)
  const [openCols, setOpenCols] = useState<Set<string>>(() => {
    try {
      const raw: unknown = JSON.parse(localStorage.getItem('kqOpenCols') ?? '[]')
      return new Set(Array.isArray(raw) ? raw.filter((k): k is string => typeof k === 'string') : [])
    } catch { return new Set() }
  })
  const toggleColOpen = (col: string) => {
    setOpenCols(prev => {
      const next = toggled(prev, col)
      try { localStorage.setItem('kqOpenCols', JSON.stringify([...next])) } catch { /* tryb prywatny */ }
      return next
    })
    setOpenCells(prev => new Set([...prev].filter(k => !k.endsWith(`:${col}`))))
  }
  // Kolejka Enterprise: widoczne kolumny i gęstość wiersza (localStorage, per przeglądarka)
  const [savedCols, setSavedCols] = useState<string[] | null>(readColumns)
  const columns = useMemo(() => {
    const cols = visibleColumns(savedCols)
    roleHidden.forEach(k => cols.delete(k))
    return cols
  }, [savedCols, roleHidden])
  const toggleCol = (key: string) => {
    const next = toggleColumn(columns, key)
    setSavedCols(next); writeColumns(next)
  }
  const resetCols = () => { setSavedCols(null); writeColumns(null) }
  // kolejność kolumn: profil konta (setPref → /api/auth/me/prefs), null = domyślna z kodu
  const [savedOrder, setSavedOrder] = useState<string[] | null>(readOrder)
  const colOrder = useMemo(() => applyOrder(DEFAULT_ORDER, savedOrder), [savedOrder])
  const setOrder = (next: string[] | null) => { setSavedOrder(next); setPref(ORDER_KEY, JSON.stringify(next)) }
  const moveCol = (key: string, target: string, after: boolean) => setOrder(moveBeside(colOrder, key, target, after))
  const stepCol = (key: string, dir: -1 | 1, among: readonly string[]) => setOrder(moveStep(colOrder, key, dir, among))
  const resetOrder = () => setOrder(null)
  const [dense, setDenseState] = useState(readDense)
  const setDense = (d: boolean) => { setDenseState(d); writeDense(d) }

  // multi-sort w dniu (Shift+klik nagłówka dokłada kryterium; klik = pojedyncze)
  const [sortBy, setSortBy] = useState<SortKey[]>([])
  // zapisane widoki: nazwa -> location.search (zakładka/zakres/filtry żyją w URL) + preferencje
  // układu (grupowanie, kolumny, gęstość). Stary format {name, search} nadal działa.
  const [savedViews, setSavedViews] = useState<SavedView[]>(() => {
    try {
      const raw = JSON.parse(localStorage.getItem('queueViews') || '[]')
      return Array.isArray(raw) ? raw.filter(v => v && typeof v.name === 'string' && typeof v.search === 'string') : []
    } catch { return [] }
  })
  const persistViews = (views: SavedView[]) => {
    setSavedViews(views)
    setPref('queueViews', JSON.stringify(views))
  }
  const saveView = (name: string, search: string) => persistViews([
    ...savedViews.filter(v => v.name !== name),
    { name, search, groupBy, columns: savedCols, order: savedOrder, dense }])
  const deleteView = (name: string) => persistViews(savedViews.filter(v => v.name !== name))
  // zastosuj układ zapisanego widoku (URL ustawia wywołujący — navigate({ search }))
  const applyViewLayout = (v: SavedView) => {
    if (v.groupBy) setGroupBy(v.groupBy)
    if (v.columns !== undefined) { setSavedCols(v.columns); writeColumns(v.columns) }
    if (v.order !== undefined) setOrder(Array.isArray(v.order) ? v.order.filter(k => typeof k === 'string') : null)
    if (v.dense !== undefined) setDense(v.dense)
  }
  const toggleSort = (key: string, additive: boolean) => {
    setSortBy(prev => {
      const found = prev.find(x => x.key === key)
      const rest = prev.filter(x => x.key !== key)
      const next: SortKey = { key, dir: found ? (found.dir === 1 ? -1 : 1) : 1 }
      // trzeci klik na jedynym kryterium zdejmuje sort
      if (found && found.dir === -1 && !additive) return []
      if (found && found.dir === -1) return rest
      return additive ? [...rest, next] : [next]
    })
  }
  const sortItems = (items: Container[]) => {
    if (sortBy.length === 0) return items
    return [...items].sort((a, b) => {
      for (const { key, dir } of sortBy) {
        const get = SORT_ACCESSOR[key]
        if (!get) continue
        const av = get(a), bv = get(b)
        if (av < bv) return -dir
        if (av > bv) return dir
      }
      return 0
    })
  }

  // „moje kontenery": zbiór obserwowanych id (gwiazdka) + filtr Moje
  const [watched, setWatched] = useState<Set<number>>(new Set())
  // powód obserwacji (tylko niepusty) — etykieta przy numerze w kolejce i w szufladzie
  const [watchReasons, setWatchReasons] = useState<ReadonlyMap<number, string>>(new Map())
  useEffect(() => {
    api.get<number[]>('/api/watch').then(ids => setWatched(new Set(ids))).catch(() => {})
    api.get<{ container_id: number; reason: string }[]>('/api/watch/reasons')
      .then(rows => { if (Array.isArray(rows)) setWatchReasons(new Map(rows.map(r => [r.container_id, r.reason]))) })
      .catch(() => {})
  }, [])
  // dodanie gwiazdki pyta o powód (WatchReasonDialog w TileMenus); zdjęcie — od razu
  const [watchPrompt, setWatchPrompt] = useState<number | null>(null)
  const postWatch = (id: number, body: { reason?: string }) => {
    api.post<{ watching: boolean }>(`/api/containers/${id}/watch`, body)
      .then(r => {
        setWatched(prev => {
          const next = new Set(prev)
          if (r.watching) next.add(id); else next.delete(id)
          return next
        })
        setWatchReasons(prev => {
          const next = new Map(prev)
          const reason = body.reason?.trim()
          if (r.watching && reason) next.set(id, reason); else next.delete(id)
          return next
        })
      }).catch(() => {})
  }
  const toggleWatch = (id: number) => {
    if (watched.has(id)) postWatch(id, {}); else setWatchPrompt(id)
  }
  const confirmWatch = (reason: string) => {
    if (watchPrompt !== null) postWatch(watchPrompt, { reason })
    setWatchPrompt(null)
  }
  const cancelWatch = () => setWatchPrompt(null)

  return {
    groupBy, setGroupBy, collapsedPlanning, togglePlanSection,
    columns, roleHidden, toggleCol, resetCols, dense, setDense, colOrder, moveCol, stepCol, resetOrder,
    openCells, toggleCell, openCols, toggleColOpen, sortBy, toggleSort, sortItems, savedViews, saveView, deleteView,
    applyViewLayout,
    watched, watchReasons, toggleWatch, watchPrompt, confirmWatch, cancelWatch,
  }
}

export type ViewPrefs = ReturnType<typeof useViewPrefs>
