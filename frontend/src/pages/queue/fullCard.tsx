import { ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'
// „Pełna karta” z kolejki (2026-09-30): osobny ekran /kontenery/:id zamiast panelu wstawianego
// w tabelę kolejki. Kolejka przekazuje w stanie nawigacji swój adres (zakładka/filtry/grupowanie
// w query) i kolejność wierszy → na karcie „← Kolejka” wraca do tego samego widoku, a ‹ ›
// przechodzą po sąsiadach. Przewinięcie kolejki zapamiętane w sessionStorage.
import { useCallback, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useT } from '../../i18n'

const SCROLL_KEY = 'queue.returnScroll'

export type QueueNavState = { queueNav: { back: string; order: number[] | null } }

/** Stan nawigacji odporny na zły kształt (link bezpośredni / cudzy state = null). */
export function readQueueNav(state: unknown): QueueNavState['queueNav'] | null {
  const q = (state as Partial<QueueNavState> | null)?.queueNav
  if (!q || typeof q.back !== 'string') return null
  return { back: q.back, order: Array.isArray(q.order) ? q.order.filter(n => typeof n === 'number') : null }
}

/** Kolejka → pełna karta. order = kolejność wierszy widoku (null = bez strzałek ‹ ›). */
export function useOpenFullCard() {
  const navigate = useNavigate()
  const location = useLocation()
  return useCallback((id: number, order: number[] | null) => {
    try { sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ id, y: window.scrollY })) } catch { /* brak storage */ }
    const state: QueueNavState = { queueNav: { back: location.pathname + location.search, order } }
    navigate(`/kontenery/${id}`, { state })
  }, [navigate, location.pathname, location.search])
}

/** Kolejka po powrocie z karty: przywraca przewinięcie i miga wierszem otwartego kontenera.
    Zapis jest jednorazowy; po ‹ › na karcie wiersz innego kontenera dociągamy do widoku. */
export function useReturnScroll(ready: boolean, rowId: number | null) {
  useEffect(() => {
    if (!ready) return
    let saved: { y?: unknown } | null = null
    try {
      saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) ?? 'null')
      sessionStorage.removeItem(SCROLL_KEY)
    } catch { /* brak storage / zły JSON */ }
    if (typeof saved?.y !== 'number') return
    const target = saved.y
    const frame = requestAnimationFrame(() => {
      window.scrollTo(0, target)
      const row = rowId ? document.querySelector(`[data-cid="${rowId}"]`) : null
      row?.scrollIntoView?.({ block: 'nearest' })
      row?.classList.add('flash')
      if (row) setTimeout(() => row.classList.remove('flash'), 2000)
    })
    return () => cancelAnimationFrame(frame)
  }, [ready, rowId])
}

/** Pasek nad kartą: „← Kolejka” (ten sam widok, podświetlony ten kontener) i ‹ › po kolejce. */
export function FullCardNav({ id }: { id: number }) {
  const t = useT()
  const navigate = useNavigate()
  const location = useLocation()
  const nav = readQueueNav(location.state)
  const back = () => {
    const u = new URL(nav?.back || '/kolejka', window.location.origin)
    // weszliśmy z szuflady → wraca na TEN kontener (po ‹ › może to być inny niż na wejściu)
    if (u.searchParams.has('kontener')) u.searchParams.set('kontener', String(id))
    navigate(u.pathname + u.search)
  }
  const idx = nav?.order ? nav.order.indexOf(id) : -1
  const go = (to: number | undefined) => to !== undefined
    && navigate(`/kontenery/${to}`, { replace: true, state: location.state })
  return (
    <nav className="ct-page-nav" aria-label={t('fcNav')}>
      <button type="button" className="btn small secondary" onClick={back}>
        <ArrowLeftIcon size={14} aria-hidden="true" /> {t('fcBack')}
      </button>
      <span className="spacer" />
      {nav?.order && idx >= 0 && <>
        <span className="kq-dim mono">{idx + 1} / {nav.order.length}</span>
        <button type="button" className="btn small secondary" aria-label={t('kqdPrev')} title={t('kqdPrev')}
                disabled={idx <= 0} onClick={() => go(nav.order![idx - 1])}>
          <ChevronLeftIcon size={14} aria-hidden="true" />
        </button>
        <button type="button" className="btn small secondary" aria-label={t('kqdNext')} title={t('kqdNext')}
                disabled={idx >= nav.order.length - 1} onClick={() => go(nav.order![idx + 1])}>
          <ChevronRightIcon size={14} aria-hidden="true" />
        </button>
      </>}
    </nav>
  )
}
