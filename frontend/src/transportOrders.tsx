import { useState } from 'react'
import type { ReactNode } from 'react'
import { api, errorMessage } from './api'
import { useConfirm } from './ConfirmDialog'
import { useT } from './i18n'
import type { TransportOrder, TransportOrderStatus } from './types'

// CODE-008: jedna logika akcji i przejść zleceń transportowych dla karty kontenera
// (TransportOrdersPanel) i strony Spedycji — wcześniej ~90 linii skopiowanych w obu miejscach,
// więc poprawka reguły w jednym nie trafiała do drugiego.
//   spedytor:   WYSTAWIONE → przyjmij / odrzuć (z powodem); ZAAKCEPTOWANE → w realizacji / wykonane;
//               W_REALIZACJI → wykonane
//   logistyka:  WYSTAWIONE → akceptacja w imieniu spedytora z notatką (tylko gdy onBehalf);
//               WYKONANE → potwierdź albo cofnij do realizacji (pomyłka spedytora, z powodem);
//               ODRZUCONE → wystaw ponownie (z powodem) — BIZ-008
export function useTransportOrderActions({ role, onDone, onBehalf = false }: {
  role: string | undefined
  onDone: () => void          // po udanej zmianie statusu (przeładowanie listy, toast)
  onBehalf?: boolean          // przycisk „Akceptuj w imieniu spedytora” (karta kontenera)
}) {
  const t = useT()
  const { prompt } = useConfirm()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [rejectFor, setRejectFor] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const isForwarder = role === 'forwarder'
  const canManage = role === 'admin' || role === 'logistics'

  const changeStatus = async (orderId: number, status: TransportOrderStatus, statusReason = '') => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post(`/api/transport-orders/${orderId}/status`, { status, reason: statusReason })
      setRejectFor(null)
      setReason('')
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // logistyka: akceptacja w imieniu spedytora (np. po telefonie) — zawsze z notatką (2026-09-28)
  const acceptOnBehalf = async (orderId: number) => {
    const note = await prompt(t('acceptOnBehalfPrompt'))
    if (note === null) return
    if (!note.trim()) { setError(t('acceptOnBehalfNoteRequired')); return }
    await changeStatus(orderId, 'ZAAKCEPTOWANE', note.trim())
  }

  // BIZ-008: korekta obiegu przez logistykę — zawsze z powodem (audyt + powiadomienie spedytora)
  const correct = async (orderId: number, status: TransportOrderStatus) => {
    const note = await prompt(t('orderCorrectionPrompt'))
    if (note === null) return
    if (!note.trim()) { setError(t('orderCorrectionReasonRequired')); return }
    await changeStatus(orderId, status, note.trim())
  }

  const actions = (order: TransportOrder): ReactNode => {
    if (isForwarder) {
      if (order.status === 'WYSTAWIONE') {
        return (
          <>
            <button className="btn small" onClick={() => changeStatus(order.id, 'ZAAKCEPTOWANE')}>{t('accept')}</button>
            <button className="btn small secondary" onClick={() => setRejectFor(order.id)}>{t('reject')}</button>
          </>
        )
      }
      if (order.status === 'ZAAKCEPTOWANE') {
        return (
          <>
            <button className="btn small" onClick={() => changeStatus(order.id, 'W_REALIZACJI')}>{t('startWork')}</button>
            <button className="btn small secondary" onClick={() => changeStatus(order.id, 'WYKONANE')}>{t('markDone')}</button>
          </>
        )
      }
      if (order.status === 'W_REALIZACJI') {
        return <button className="btn small" onClick={() => changeStatus(order.id, 'WYKONANE')}>{t('markDone')}</button>
      }
    } else if (canManage && onBehalf && order.status === 'WYSTAWIONE') {
      return <button className="btn small secondary" onClick={() => acceptOnBehalf(order.id)}>{t('acceptOnBehalf')}</button>
    } else if (canManage && order.status === 'WYKONANE') {
      return (
        <>
          <button className="btn small" onClick={() => changeStatus(order.id, 'POTWIERDZONE')}>{t('confirm')}</button>
          <button className="btn small secondary" onClick={() => correct(order.id, 'W_REALIZACJI')}>{t('orderRevertDone')}</button>
        </>
      )
    } else if (canManage && order.status === 'ODRZUCONE') {
      return <button className="btn small secondary" onClick={() => correct(order.id, 'WYSTAWIONE')}>{t('orderReissue')}</button>
    }
    return null
  }

  // pole powodu odrzucenia (spedytor) — pod listą zleceń
  const rejectRow = rejectFor !== null && (
    <div className="row to-reject">
      <input aria-label={t('rejectionReason')} placeholder={t('rejectionReason')} value={reason}
             onChange={e => setReason(e.target.value)} style={{ flex: 1 }} />
      <button className="btn small" disabled={!reason.trim()}
              onClick={() => changeStatus(rejectFor, 'ODRZUCONE', reason)}>
        {t('reject')}
      </button>
      <button className="btn small secondary" onClick={() => setRejectFor(null)}>{t('cancel')}</button>
    </div>
  )

  return { busy, error, setError, actions, rejectRow }
}
