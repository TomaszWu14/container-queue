// Zaznaczanie i przenoszenie kontenerów na inną datę awizacji (drag&drop, kalendarz,
// akcja zbiorcza) + potwierdzenie z Cofnij. Wyniesione z QueuePage.tsx.
import { useEffect, useState } from 'react'
import type { DragEvent } from 'react'
import { api } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Container } from '../../types'
import type { PendingMove } from './config'

export function useQueueMove({ containers, visible, canMove, replaceContainer, load }: {
  containers: Container[]
  // kontenery po filtrach klienta (★ Moje, 🚩 Specjalne) — tylko te widać na ekranie
  visible: Container[]
  canMove: boolean   // canEdit && !archive
  replaceContainer: (saved: Container) => void
  load: () => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const [moveUnlocked, setMoveUnlocked] = useState(false)
  const [dragId, setDragId] = useState<number | null>(null)
  const [dropDay, setDropDay] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null)
  const [moving, setMoving] = useState(false)
  const [moveError, setMoveError] = useState('')
  const [bulkDatePick, setBulkDatePick] = useState(false)
  const moveActive = canMove && moveUnlocked

  // zmiana modułu czyści zaznaczenie; blokada przenoszenia zamyka wiszące potwierdzenie
  useEffect(() => {
    if (!moveActive) setPendingMove(null)
  }, [moveActive])

  // nowa lista (filtr serwerowy, wyszukiwanie, zakres, archiwum) przycina zaznaczenie do
  // obecnych id — inaczej akcje zbiorcze działałyby na niewidocznych kontenerach
  useEffect(() => {
    setSelected(prev => {
      const present = new Set(containers.map(c => c.id))
      const kept = [...prev].filter(id => present.has(id))
      return kept.length === prev.size ? prev : new Set(kept)
    })
  }, [containers])

  const toggleSelect = (id: number) =>
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleSelectDay = (items: Container[]) =>
    setSelected(prev => {
      const next = new Set(prev)
      const allSelected = items.every(c => next.has(c.id))
      for (const c of items) {
        if (allSelected) next.delete(c.id)
        else next.add(c.id)
      }
      return next
    })

  // zaznaczenie wszystkich WIDOCZNYCH kontenerów (checkbox we wspólnym nagłówku) —
  // liczone po `visible`, nie `containers`: inaczej przy ★ Moje/🚩 Specjalne akcje
  // zbiorcze trafiałyby w kontenery ukryte filtrem klienta
  const allSelected = visible.length > 0 && visible.every(c => selected.has(c.id))
  const toggleSelectAll = () =>
    setSelected(prev => {
      const all = visible.length > 0 && visible.every(c => prev.has(c.id))
      return all ? new Set() : new Set(visible.map(c => c.id))
    })

  const handleDrop = (e: DragEvent, day: string) => {
    e.preventDefault()
    setDropDay(null)
    setDragId(null)
    if (!moveActive || !day) return
    const ids = e.dataTransfer.getData('text/plain')
      .split(',').map(Number).filter(Boolean)
    const toMove = ids.filter(id => {
      const c = containers.find(x => x.id === id)
      return c && (c.notify_date ?? '') !== day
    })
    if (toMove.length === 0) return
    setMoveError('')
    setPendingMove({ ids: toMove, day })
  }

  const confirmMove = async () => {
    if (!pendingMove) return
    setMoving(true)
    setMoveError('')
    const results = await Promise.allSettled(pendingMove.ids.map(id =>
      api.patch<Container>(`/api/containers/${id}`, {
        notify_date: pendingMove.day,
        change_note: pendingMove.note ?? t('moveNote'),
      })))
    const failed: string[] = []
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        replaceContainer(result.value)
      } else {
        const c = containers.find(x => x.id === pendingMove.ids[index])
        failed.push(c?.container_no ?? `#${pendingMove.ids[index]}`)
      }
    })
    setMoving(false)
    if (failed.length > 0) {
      setMoveError(`${t('moveFailed')} ${failed.join(', ')}`)
      load()
      return
    }
    // zmiana daty z kalendarza dotyczy jednego kafelka — nie kasuj zaznaczenia użytkownika
    if (!pendingMove.fromDate) setSelected(new Set())
    // #29: Cofnij — przywróć poprzednie daty tym samym endpointem (toast z akcją, 10 s)
    const undo = pendingMove.ids
      .map(id => ({ id, prev: containers.find(x => x.id === id)?.notify_date ?? null }))
    setPendingMove(null)
    // #49: ostrzeżenie o konflikcie awizacji dostawcy (backend nie blokuje)
    const conflicts = results.reduce((n, r) =>
      n + (r.status === 'fulfilled' ? (r.value.notify_conflict ?? 0) : 0), 0)
    // kolizja transportowa po zmianie daty: paczka rozjeżdża się na różne magazyny
    const tcNames = [...new Set(results.flatMap(r =>
      r.status === 'fulfilled' ? (r.value.transport_conflict ?? []) : []))]
    if (tcNames.length > 0) {
      showToast(`${t('transportConflictWarn')}: ${tcNames.join(' / ')}`, 'error')
    }
    if (conflicts > 0) {
      showToast(`${t('notifyConflictWarn')} (${conflicts})`, 'error')
    } else {
      // #29: Cofnij — przywróć poprzednie daty tym samym endpointem (toast z akcją, 10 s)
      showToast(t('toastDateMoved'), 'success', {
        label: t('undoMove'),
        onClick: () => {
          Promise.allSettled(undo.map(u =>
            api.patch<Container>(`/api/containers/${u.id}`,
              { notify_date: u.prev, change_note: t('undoNote') })))
            .then(rs => {
              rs.forEach(r => { if (r.status === 'fulfilled') replaceContainer(r.value) })
              load()
            })
        },
      })
    }
  }

  return {
    moveUnlocked, setMoveUnlocked, moveActive, dragId, setDragId, dropDay, setDropDay,
    selected, setSelected, allSelected, pendingMove, setPendingMove, moving, moveError,
    bulkDatePick, setBulkDatePick,
    toggleSelect, toggleSelectDay, toggleSelectAll, handleDrop, confirmMove,
  }
}

export type QueueMove = ReturnType<typeof useQueueMove>
