import { CalendarIcon, MailIcon, XIcon } from 'lucide-react'
// Kolejka Enterprise (plaster 3): pasek akcji masowych — zastępuje pasek filtrów, gdy coś
// zaznaczono. Status i magazyn jednym żądaniem (POST /containers/bulk/*), awizacja i wycena
// przez istniejące modale, data przez istniejące potwierdzenie przeniesienia, usuwanie — admin.
import { useContext, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { LangContext, useT } from '../../i18n'
import { CONTAINER_STATUSES } from '../../types'
import { selectedLabel } from './enterprise'
import type { QueueMove } from './useQueueMove'
import { useConfirm } from '../../ConfirmDialog'

type BulkResult = { ok: number[]; failed: { id: number; detail: string }[] }

// ZREALIZOWANY zamyka rozliczenie — nie z kolejki (jak dawny masowy select)
const BULK_STATUSES = CONTAINER_STATUSES.filter(s => s !== 'ZREALIZOWANY')

export default function BulkActionBar({ mv, isAdmin, warehouseOptions, onAvizo, onQuote, reload }: {
  mv: QueueMove
  isAdmin: boolean
  warehouseOptions: string[]
  onAvizo: () => void
  onQuote: () => void
  reload: () => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const { lang } = useContext(LangContext)
  const { showToast } = useToast()
  const [busy, setBusy] = useState(false)
  const ids = [...mv.selected]

  // po akcji: wynik (także częściowe błędy), odśwież dane, wyczyść zaznaczenie
  const finish = (ok: number, total: number, firstError?: string) => {
    showToast(`${t('kqbDone')}: ${ok}/${total}${firstError ? ` — ${firstError}` : ''}`,
              ok === total ? 'success' : 'error')
    mv.setSelected(new Set())
    reload()
  }
  const runBulk = async (path: string, body: Record<string, unknown>) => {
    setBusy(true)
    try {
      const r = await api.post<BulkResult>(`/api/containers/bulk/${path}`, { ids, ...body })
      finish(r.ok.length, ids.length, r.failed[0]?.detail)
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    if (!(await confirm(t('deleteSelectedConfirm').replace('{n}', String(ids.length)), { danger: true }))) return
    setBusy(true)
    const rs = await Promise.allSettled(ids.map(id => api.del(`/api/containers/${id}`)))
    setBusy(false)
    const bad = rs.find((r): r is PromiseRejectedResult => r.status === 'rejected')
    finish(rs.filter(r => r.status === 'fulfilled').length, ids.length,
           bad ? errorMessage(bad.reason) : undefined)
  }

  return (
    <div className="kq-bulk" role="toolbar" aria-label={t('kqbToolbar')}>
      <span><b>{selectedLabel(ids.length, lang)}</b></span>
      <span className="kq-bulk-sep" aria-hidden="true" />
      <select className="kq-bulk-sel" value="" disabled={busy} aria-label={t('changeStatus')}
              onChange={e => e.target.value && runBulk('status', { status: e.target.value })}>
        <option value="">{t('changeStatus')}</option>
        {BULK_STATUSES.map(s => <option key={s} value={s}>{t(`st_${s}`)}</option>)}
      </select>
      {warehouseOptions.length > 0 && (
        <select className="kq-bulk-sel" value="" disabled={busy} aria-label={t('changeWarehouse')}
                onChange={e => e.target.value && runBulk('warehouse', { name: e.target.value })}>
          <option value="">{t('changeWarehouse')}</option>
          {warehouseOptions.map(w => <option key={w} value={w}>{w}</option>)}
        </select>
      )}
      {mv.bulkDatePick ? (
        <input type="date" autoFocus className="kq-bulk-sel" aria-label={t('bulkMoveDate')}
               onChange={e => {
                 const day = e.target.value
                 mv.setBulkDatePick(false)
                 if (day) mv.setPendingMove({ ids, day })
               }}
               onBlur={() => mv.setBulkDatePick(false)} />
      ) : (
        <button type="button" className="btn small secondary" disabled={busy}
                onClick={() => mv.setBulkDatePick(true)}><CalendarIcon size={14} /> {t('bulkMoveDate')}</button>
      )}
      <button type="button" className="btn small avizo-btn" disabled={busy} onClick={onAvizo}>
        <MailIcon size={14} /> {t('kqdAvizo')}
      </button>
      <button type="button" className="btn small secondary" disabled={busy} onClick={onQuote}>
        {t('kqbQuote')}
      </button>
      <span className="spacer" />
      {isAdmin && (
        <button type="button" className="btn small danger" disabled={busy} onClick={remove}>
          {t('kqbDelete')}
        </button>
      )}
      <button type="button" className="kq-bulk-clear" onClick={() => mv.setSelected(new Set())}>
        <XIcon size={14} /> {t('kqbClear')}
      </button>
    </div>
  )
}
