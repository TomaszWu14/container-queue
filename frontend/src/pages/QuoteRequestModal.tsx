import { useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { Modal } from '../components'
import type { Container, Named, TransportJob } from '../types'

// Zlecenie wyceny z zaznaczonych kontenerów w kolejce: wybór spedycji + odbiór/dostawa.
export default function QuoteRequestModal({ containers, forwarders, onDone, onClose }: {
  containers: Container[]
  forwarders: Named[]
  onDone: () => void
  onClose: () => void
}) {
  const t = useT()
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [fwdSearch, setFwdSearch] = useState('')
  const [pickup, setPickup] = useState('')
  const [delivery, setDelivery] = useState('')
  const [note, setNote] = useState('')
  const [hours, setHours] = useState('24')
  const [scfi, setScfi] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const toggle = (id: number) => setPicked(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const query = fwdSearch.trim().toLowerCase()
  const shownForwarders = query
    ? forwarders.filter(f => f.name.toLowerCase().includes(query))
    : forwarders

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      // utwórz zlecenie, następnie wyślij do zaproszonych spedycji
      // guard: nigdy nie wysyłamy do spedytora bez adresu (checkbox i tak zablokowany,
      // ale filtrujemy też na wypadek nieaktualnego stanu picked)
      const withEmail = new Set(
        forwarders.filter(f => f.email && f.email.trim()).map(f => f.id))
      const job = await api.post<TransportJob>('/api/transport-jobs', {
        container_ids: containers.map(c => c.id),
        forwarder_ids: [...picked].filter(id => withEmail.has(id)),
        pickup_location: pickup, delivery_location: delivery, note,
        response_hours: Math.min(336, Math.max(1, Number(hours) || 24)), scfi_index: scfi,
      })
      await api.post(`/api/transport-jobs/${job.id}/send`, {})
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`${t('quoteNew')} — ${containers.length} ${t('contAbbrev')}`} onClose={onClose} busy={busy} width={560}>
        <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 0 }}>
          {t('quoteNewInfo')}
        </p>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <label style={{ flex: 1, fontSize: 14 }}>{t('quotePickup')}
            <input value={pickup} onChange={e => setPickup(e.target.value)} />
          </label>
          <label style={{ flex: 1, fontSize: 14 }}>{t('quoteDelivery')}
            <input value={delivery} onChange={e => setDelivery(e.target.value)} />
          </label>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <label style={{ flex: 1, fontSize: 14 }}>{t('quoteResponseHours')}
            <input type="number" min="1" max="336" value={hours}
                   onChange={e => setHours(e.target.value)} />
          </label>
          <label style={{ flex: 1, fontSize: 14 }}>SCFI ({t('quoteScfiHint')})
            <input value={scfi} onChange={e => setScfi(e.target.value)}
                   placeholder="1200 USD/FEU" />
          </label>
        </div>
        <label style={{ fontSize: 14 }}>{t('notes')}
          <textarea rows={2} value={note} onChange={e => setNote(e.target.value)} />
        </label>

        <div style={{ fontSize: 14, fontWeight: 600, margin: '10px 0 4px' }}>
          {t('quotePickForwarders')}
        </div>
        <input className="quote-fwd-search" aria-label={t('quoteFwdSearch')} placeholder={t('quoteFwdSearch')}
               value={fwdSearch} onChange={e => setFwdSearch(e.target.value)} />
        <div className="quote-fwd-list">
          {shownForwarders.map(f => {
            const hasEmail = !!(f.email && f.email.trim())
            return (
              // bez adresu e-mail nie da się zaznaczyć — wysyłka i tak by do niego nie dotarła,
              // jawna blokada jest lepsza niż ciche „nic się nie stało"
              <label key={f.id}
                     className={`quote-fwd${picked.has(f.id) ? ' on' : ''}${hasEmail ? '' : ' disabled'}`}
                     title={hasEmail ? f.email : t('fwdNoEmail')}>
                <input type="checkbox" checked={picked.has(f.id)} disabled={!hasEmail}
                       onChange={() => hasEmail && toggle(f.id)} />
                <span className="quote-fwd-name">{f.name}</span>
                <span className="quote-fwd-mail">{hasEmail ? f.email : t('fwdNoEmail')}</span>
              </label>
            )
          })}
          {shownForwarders.length === 0 && (
            <span className="muted" style={{ fontSize: 14 }}>{t('empty')}</span>
          )}
        </div>

        <div className="import-rows" style={{ marginTop: 10 }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="grid" style={{ minWidth: 720 }}>
              <thead><tr><th>{t('containerNo')}</th><th>{t('supplier')}</th><th>{t('orderNumbers')}</th></tr></thead>
              <tbody>
                {containers.map(c => (
                  <tr key={c.id}>
                    <td className="mono">{c.container_no}</td>
                    <td>{c.supplier_name}</td>
                    <td className="mono">{c.order_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
          <button className="btn" disabled={busy || picked.size === 0} onClick={submit}>
            {busy ? t('loading') : `${t('quoteCreateSend')} (${picked.size})`}
          </button>
        </div>
    </Modal>
  )
}
