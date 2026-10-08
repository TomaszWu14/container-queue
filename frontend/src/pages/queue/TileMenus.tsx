// Menu kontekstowe kafelka kolejki: „⋯" (touch), zmiana magazynu rozładunku (+ okno
// potwierdzenia) i zmiana daty awizacji. Wyniesione z QueuePage.tsx.
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { useDismiss } from '../../ColumnFilter'
import { Modal } from '../../components'
import { formatDate } from '../../dates'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Container } from '../../types'
import WatchReasonDialog from '../watch/WatchReasonDialog'
import { idLabel } from './cells'
import type { PendingMove, TileMenuPos } from './config'
import { ArrowLeftRight, CalendarDays, ChevronDown, Star, Warehouse } from 'lucide-react'

export function useTileMenus(replaceContainer: (saved: Container) => void) {
  const t = useT()
  const { showToast } = useToast()
  // menu kontekstowe zmiany magazynu rozładunku (prawy przycisk na kafelku) + potwierdzenie
  const [whMenu, setWhMenu] = useState<TileMenuPos | null>(null)
  // menu kontekstowe zmiany daty awizacji (prawy przycisk na kafelku) → kalendarz
  const [dateMenu, setDateMenu] = useState<TileMenuPos | null>(null)
  // menu „⋯" wywoływane tapem (touch/tablet) — brak right-click w magazynie
  const [tileMenu, setTileMenu] = useState<TileMenuPos | null>(null)
  const [whConfirm, setWhConfirm] = useState<{ c: Container; name: string } | null>(null)
  const [whBusy, setWhBusy] = useState(false)
  const [whError, setWhError] = useState('')

  // zapis po potwierdzeniu w oknie (żeby nie przeklikać przypadkiem)
  const changeWarehouse = async () => {
    if (!whConfirm) return
    setWhBusy(true)
    setWhError('')
    try {
      const saved = await api.post<Container>(
        `/api/containers/${whConfirm.c.id}/warehouse`, { name: whConfirm.name })
      replaceContainer(saved)
      setWhConfirm(null)
      // ostrzeżenie (nie blokada): zmiana magazynu rozjechała paczkę transportową
      if (saved.transport_conflict?.length) {
        showToast(`${t('transportConflictWarn')}: ${saved.transport_conflict.join(' / ')}`, 'error')
      } else {
        showToast(t('toastWarehouseChanged'))
      }
    } catch (err) {
      setWhError(errorMessage(err))
    } finally {
      setWhBusy(false)
    }
  }

  // menu kontekstowe (magazyn / data / kebab) zamykamy Escape / klikiem poza / scrollem
  useDismiss(!!whMenu, () => setWhMenu(null))
  useDismiss(!!dateMenu, () => setDateMenu(null))
  useDismiss(!!tileMenu, () => setTileMenu(null))

  return {
    whMenu, setWhMenu, dateMenu, setDateMenu, tileMenu, setTileMenu,
    whConfirm, setWhConfirm, whBusy, whError, setWhError, changeWarehouse,
  }
}

export type TileMenusState = ReturnType<typeof useTileMenus>

export default function TileMenus({ m, warehouseOptions, canEdit, setPendingMove, watched, toggleWatch,
  watchPrompt, confirmWatch, cancelWatch, onDetails, onStatus, statusLabel }: {
  // Kolejka Enterprise: akcje wiersza (Szczegóły / Status) przeniesione z wiersza do menu ⋯
  onDetails: (c: Container) => void
  onStatus: ((c: Container) => void) | null
  statusLabel: string
  m: TileMenusState
  warehouseOptions: string[]   // menu magazynu (prawy klik na komórce Magazyn)
  canEdit: boolean
  setPendingMove: (v: PendingMove) => void
  watched: Set<number>          // ten sam stan co gwiazdka ☆ na liście → zmiana widoczna od razu w obu
  toggleWatch: (id: number) => void
  watchPrompt: number | null    // dodanie gwiazdki pyta o powód — okienko renderowane tu (poza menu)
  confirmWatch: (reason: string) => void
  cancelWatch: () => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const { tileMenu, whMenu, dateMenu, whConfirm, whBusy, whError } = m
  return (
    <>
      {tileMenu && (
        <div className="ctx-menu tile-action-menu"
             // prawa krawędź menu przy punkcie kliknięcia — `right` zamiast translateX(-100%) (ostry tekst)
             style={{ top: Math.round(tileMenu.y), right: Math.round(document.documentElement.clientWidth - tileMenu.x) }}
             onClick={e => e.stopPropagation()}
             onContextMenu={e => e.preventDefault()}>
          <div className="ctx-title">{idLabel(tileMenu.c)}</div>
          <button onClick={() => { const c = tileMenu.c; m.setTileMenu(null); onDetails(c) }}>
            <ChevronDown size={16} aria-hidden="true" /> {t('cdExpand')}
          </button>
          {onStatus && (
            <button onClick={() => { const c = tileMenu.c; m.setTileMenu(null); onStatus(c) }}>
              <ArrowLeftRight size={16} aria-hidden="true" /> {statusLabel}
            </button>
          )}
          {canEdit && (
            <button onClick={() => { const pos = tileMenu; m.setTileMenu(null); m.setDateMenu(pos) }}>
              <CalendarDays size={16} aria-hidden="true" /> {t('changeNotifyDate')}
            </button>
          )}
          {canEdit && warehouseOptions.length > 0 && (
            <button onClick={() => { const pos = tileMenu; m.setTileMenu(null); m.setWhMenu(pos) }}>
              <Warehouse size={16} aria-hidden="true" /> {t('changeWarehouse')}
            </button>
          )}
          <button onClick={() => { const id = tileMenu.c.id; m.setTileMenu(null); toggleWatch(id) }}>
            <Star size={16} aria-hidden="true" fill={watched.has(tileMenu.c.id) ? 'currentColor' : 'none'} />
            {watched.has(tileMenu.c.id) ? t('watchRemove') : t('watchAdd')}
          </button>
        </div>
      )}

      {whMenu && (
        <div className="ctx-menu" style={{ top: Math.round(whMenu.y), left: Math.round(whMenu.x) }}
             onClick={e => e.stopPropagation()}
             onContextMenu={e => e.preventDefault()}>
          <div className="ctx-title">{t('changeWarehouse')}</div>
          <div className="ctx-current mono">{idLabel(whMenu.c)}</div>
          {warehouseOptions.map(name => {
            const current = (whMenu.c.warehouse_name ?? '').toUpperCase() === name.toUpperCase()
            return (
              <button key={name} className={current ? 'active' : ''}
                      onClick={() => { m.setWhConfirm({ c: whMenu.c, name }); m.setWhMenu(null) }}>
                {name}{current && ' ✓'}
              </button>
            )
          })}
        </div>
      )}

      {dateMenu && (
        <div className="ctx-menu date-menu" style={{ top: Math.round(dateMenu.y), left: Math.round(dateMenu.x) }}
             onClick={e => e.stopPropagation()}
             onContextMenu={e => e.preventDefault()}>
          <div className="ctx-title">{t('changeNotifyDate')}</div>
          <div className="ctx-current mono">
            {idLabel(dateMenu.c)} · {dateMenu.c.notify_date ? formatDate(dateMenu.c.notify_date) : t('noNotifyDate')}
          </div>
          <input type="date" autoFocus defaultValue={dateMenu.c.notify_date ?? ''}
                 aria-label={t('pickNewDate')}
                 onChange={e => {
                   const day = e.target.value
                   const target = dateMenu
                   m.setDateMenu(null)
                   // ta sama data = brak zmiany; inaczej otwieramy zwykłe potwierdzenie przeniesienia
                   if (day && day !== (target.c.notify_date ?? '')) {
                     setPendingMove({ ids: [target.c.id], day,
                                      note: t('dateChangeNote'), fromDate: true })
                   }
                 }} />
          {!dateMenu.c.notify_date && (
            // #50: auto-propozycja daty przy pustej awizacji (ETA + bufor, wolny dzień roboczy)
            <button className="btn small secondary" style={{ marginTop: 6, width: '100%' }}
                    onClick={async () => {
                      const target = dateMenu
                      try {
                        const s = await api.get<{ date: string; eta: string | null; buffer_days: number }>(
                          `/api/containers/${target.c.id}/suggest-notify-date`)
                        m.setDateMenu(null)
                        setPendingMove({ ids: [target.c.id], day: s.date,
                                         note: t('suggestNote'), fromDate: true })
                        showToast(s.eta
                          ? `${t('suggestFromEta')} ${formatDate(s.eta)} + ${s.buffer_days}d → ${formatDate(s.date)}`
                          : `${t('suggestFromToday')} → ${formatDate(s.date)}`)
                      } catch (err) {
                        showToast(errorMessage(err), 'error')
                      }
                    }}>
              {t('suggestDate')}
            </button>
          )}
        </div>
      )}

      {whConfirm && (
        <Modal title={t('changeWarehouse')} onClose={() => m.setWhConfirm(null)} busy={whBusy} width={440}>
            <p className="move-question">
              {t('warehouseConfirm')}{' '}
              <span className="mono strong">{idLabel(whConfirm.c)}</span>{' '}
              <span style={{ color: 'var(--muted)' }}>
                {whConfirm.c.warehouse_name || '—'} →
              </span>{' '}
              <b>{whConfirm.name}</b>?
            </p>
            {whError && <p className="error">{whError}</p>}
            <div className="actions">
              <button className="btn secondary" disabled={whBusy}
                      onClick={() => m.setWhConfirm(null)}>
                {t('cancel')}
              </button>
              <button className="btn" disabled={whBusy} onClick={m.changeWarehouse}>
                {whBusy ? t('loading') : t('warehouseChangeYes')}
              </button>
            </div>
        </Modal>
      )}

      {watchPrompt !== null && <WatchReasonDialog onConfirm={confirmWatch} onClose={cancelWatch} />}
    </>
  )
}
