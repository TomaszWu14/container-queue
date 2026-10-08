import { CircleCheckIcon, PackageIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { Modal } from '../components'
import type { Container } from '../types'

interface SendResult {
  sent: { forwarder: string; email: string; containers: number }[]
  warehouse_info: { warehouse: string; email: string; containers: number }[]
  missing_email: string[]
  no_forwarder: number
}

export default function AvizoSendModal({ containers, onDone, onClose }: {
  containers: Container[]
  onDone: () => void
  onClose: () => void
}) {
  const t = useT()
  const [note, setNote] = useState('')
  const [warehouseInfo, setWarehouseInfo] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SendResult | null>(null)

  const byForwarder = useMemo(() => {
    const groups = new Map<string, Container[]>()
    for (const c of containers) {
      const key = c.forwarder_name ?? `— ${t('emailNoForwarder')} —`
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(c)
    }
    return [...groups.entries()]
  }, [containers, t])

  const send = async () => {
    setBusy(true)
    setError('')
    try {
      const response = await api.post<SendResult>('/api/avizo/send', {
        container_ids: containers.map(c => c.id),
        note,
        send_warehouse_info: warehouseInfo,
      })
      setResult(response)
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={t('avizoSendTitle')} onClose={onClose} busy={busy} width={640}>
        {!result && (
          <>
            <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 0 }}>
              {t('avizoSendInfo')}
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table className="grid" style={{ minWidth: 720, marginBottom: 12 }}>
                <thead>
                  <tr><th>{t('forwarder')}</th><th>{t('poContainers')}</th></tr>
                </thead>
                <tbody>
                  {byForwarder.map(([forwarder, items]) => (
                    <tr key={forwarder}>
                      <td>{forwarder}</td>
                      <td>
                        {items.length} — <span className="mono" style={{ fontSize: 12 }}>
                          {items.slice(0, 4).map(c => c.container_no).join(', ')}
                          {items.length > 4 && '…'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label style={{ display: 'block', fontSize: 14, color: 'var(--muted)' }}>
              {t('notes')}
              <textarea rows={2} style={{ width: '100%' }} value={note}
                        onChange={e => setNote(e.target.value)} />
            </label>
            <label className="row" style={{ fontSize: 14, marginTop: 10 }}>
              <input type="checkbox" checked={warehouseInfo}
                     onChange={e => setWarehouseInfo(e.target.checked)} />
              {t('avizoWarehouseInfo')}
            </label>
          </>
        )}
        {result && (
          <div>
            {result.sent.length > 0 && (
              <>
                <p><CircleCheckIcon size={14} /> {t('emailSent')} ({t('forwarding')}):</p>
                <ul>
                  {result.sent.map(entry => (
                    <li key={entry.forwarder}>
                      <b>{entry.forwarder}</b> &lt;{entry.email}&gt; — {entry.containers} {t('contAbbrev')}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {result.warehouse_info.length > 0 && (
              <>
                <p><PackageIcon size={14} /> {t('avizoWarehouseSent')}:</p>
                <ul>
                  {result.warehouse_info.map(entry => (
                    <li key={entry.warehouse}>
                      <b>{entry.warehouse}</b> &lt;{entry.email}&gt; — {entry.containers} {t('contAbbrev')}
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
            {result ? 'OK' : t('cancel')}
          </button>
          {!result && (
            <button className="btn" disabled={busy} onClick={send}>
              {busy ? t('loading') : `${t('sendEmail')} (${containers.length})`}
            </button>
          )}
        </div>
    </Modal>
  )
}
