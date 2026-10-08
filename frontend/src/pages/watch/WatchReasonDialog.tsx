import { useState } from 'react'
import { Modal } from '../../components'
import { useT } from '../../i18n'

// klucze szybkich powodów — zapisujemy PRZETŁUMACZONY tekst (powód czyta człowiek)
const QUICK = ['watchReasonUrgent', 'watchReasonDelay', 'watchReasonSpecial', 'watchReasonComplaint']

/** Okienko przy dodaniu obserwacji: szybki powód albo własny tekst; można pominąć. */
export default function WatchReasonDialog({ onConfirm, onClose }: {
  onConfirm: (reason: string) => void
  onClose: () => void
}) {
  const t = useT()
  const [reason, setReason] = useState('')
  return (
    <Modal title={t('watchReasonTitle')} onClose={onClose} width={420}>
      <div className="watch-quick">
        {QUICK.map(k => (
          <button key={k} type="button"
                  className={`btn small${reason === t(k) ? '' : ' secondary'}`}
                  onClick={() => setReason(t(k))}>{t(k)}</button>
        ))}
      </div>
      <label>{t('watchReasonOther')}
        <input value={reason} maxLength={200} onChange={e => setReason(e.target.value)} />
      </label>
      <div className="modal-actions">
        <button type="button" className="btn secondary small" onClick={() => onConfirm('')}>{t('watchSkipReason')}</button>
        <button type="button" className="btn small" onClick={() => onConfirm(reason.trim())}>{t('watchConfirm')}</button>
      </div>
    </Modal>
  )
}
