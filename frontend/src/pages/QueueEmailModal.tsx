import { CircleCheckIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { Modal } from '../components'
import { formatDate, shiftDays, todayISO } from '../dates'
import { useT } from '../i18n'
import type { Warehouse } from '../types'

interface SendResult {
  sent: { forwarder: string; email: string; containers: number }[]
  missing_email: string[]
  no_forwarder: number
}

export default function QueueEmailModal({ companyCode, onClose }: {
  companyCode: string
  onClose: () => void
}) {
  const t = useT()
  const [day, setDay] = useState(() => shiftDays(todayISO(), 1))
  const [warehouseId, setWarehouseId] = useState('')
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SendResult | null>(null)
  const [confirming, setConfirming] = useState(false)

  // tylko magazyny tej spółki (koniec z „naszymi" magazynami innych spółek na liście)
  useEffect(() => {
    api.get<Warehouse[]>(`/api/warehouses?company_code=${encodeURIComponent(companyCode)}`)
      .then(setWarehouses).catch(() => setWarehouses([]))
  }, [companyCode])

  const send = async () => {
    // wysyłka na zewnątrz (do spedytorów) — potwierdzenie w oknie (nie window.confirm)
    setConfirming(false)
    setBusy(true)
    setError('')
    try {
      const response = await api.post<SendResult>('/api/forwarding/queue-email', {
        company_code: companyCode,
        day,
        warehouse_id: warehouseId ? Number(warehouseId) : null,
      })
      setResult(response)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <Modal title={t('emailQueueTitle')} onClose={onClose} busy={busy} width={540}>
        {!result && (
          <>
            <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 0 }}>
              {t('emailQueueInfo')}
            </p>
            <div className="row">
              <label style={{ fontSize: 14 }}>{t('notifyDate')}{' '}
                <input type="date" value={day} onChange={e => setDay(e.target.value)} />
              </label>
              <select aria-label={t('warehouse')} value={warehouseId} onChange={e => setWarehouseId(e.target.value)}>
                <option value="">{t('allWarehouses')}</option>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
          </>
        )}
        {result && (
          <div>
            {result.sent.length > 0 && (
              <>
                <p><CircleCheckIcon size={14} /> {t('emailSent')}:</p>
                <ul>
                  {result.sent.map(entry => (
                    <li key={entry.forwarder}>
                      <b>{entry.forwarder}</b> &lt;{entry.email}&gt; — {entry.containers} {t('contAbbrev')}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {result.missing_email.length > 0 && (
              <p className="error">{t('emailMissing')}: {result.missing_email.join(', ')}</p>
            )}
            {result.no_forwarder > 0 && (
              <p style={{ color: 'var(--muted)' }}>
                {result.no_forwarder} {t('contAbbrev')} {t('emailNoForwarder')}
              </p>
            )}
          </div>
        )}
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>
            {result ? t('ok') : t('cancel')}
          </button>
          {!result && (
            <button className="btn" disabled={busy || !day} onClick={() => setConfirming(true)}>
              {busy ? t('loading') : t('sendEmail')}
            </button>
          )}
        </div>
    </Modal>
      {confirming && (
        <Modal title={t('emailQueueTitle')} onClose={() => setConfirming(false)}>
          <p>{t('confirmSendQueueMail')} <b>{formatDate(day)}</b>?</p>
          <div className="actions">
            <button className="btn secondary" onClick={() => setConfirming(false)}>{t('cancel')}</button>
            <button className="btn" onClick={send}>{t('sendEmail')}</button>
          </div>
        </Modal>
      )}
    </>
  )
}
