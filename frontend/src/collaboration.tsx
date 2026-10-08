import { FormEvent, useCallback, useEffect, useState } from 'react'
import { useUser } from './App'
import { api, downloadFile, errorMessage } from './api'
import { AttachmentActions, SharedBadge } from './AttachmentActions'
import { useT } from './i18n'
import { SendDocsPreviewModal } from './DocumentsW5'
import type {
  Attachment, Container, Message, TransportOrder, TransportOrderStatus,
} from './types'
import { formatDate, formatDateTime } from './dates'
import { useTransportOrderActions } from './transportOrders'

// panele wydzielone do osobnych modułów — re-eksport trzyma stare ścieżki importu
export { DriverPanel } from './DriverPanel'
export { CustomsAgencyPanel } from './CustomsPanels'

export function OrderBadge({ status }: { status: TransportOrderStatus }) {
  const t = useT()
  const colors: Record<TransportOrderStatus, string> = {
    WYSTAWIONE: 'st-ZAPOWIEDZIANY', ZAAKCEPTOWANE: 'st-W_TRANSPORCIE',
    ODRZUCONE: 'cs-REWIZJA', W_REALIZACJI: 'st-W_DOSTAWIE',
    WYKONANE: 'st-DOSTARCZONY', POTWIERDZONE: 'st-ZREALIZOWANY',
  }
  return <span className={`badge ${colors[status]}`}>{t(`to_${status}`)}</span>
}

export function TransportOrdersPanel({ container }: { container: Container }) {
  const t = useT()
  const user = useUser()
  const [orders, setOrders] = useState<TransportOrder[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    pickup_location: '', delivery_location: '',
    pickup_date: '', delivery_date: '', instructions: '',
  })
  const [busy, setBusy] = useState(false)

  const canCreate = user?.role === 'admin' || user?.role === 'logistics'

  const load = useCallback(() => {
    api.get<TransportOrder[]>(`/api/transport-orders?container_id=${container.id}`)
      .then(setOrders).catch(() => {})
  }, [container.id])
  useEffect(() => load(), [load])
  // CODE-008: przejścia statusów wspólne ze stroną Spedycji; na karcie także akceptacja w imieniu
  const { error, setError, actions, rejectRow } =
    useTransportOrderActions({ role: user?.role, onDone: load, onBehalf: true })

  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post('/api/transport-orders', {
        container_id: container.id,
        ...form,
        pickup_date: form.pickup_date || null,
        delivery_date: form.delivery_date || null,
      })
      setShowForm(false)
      setForm({ pickup_location: '', delivery_location: '', pickup_date: '', delivery_date: '', instructions: '' })
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('transportOrders')}</h3>
        {canCreate && (
          <button className="btn small secondary" onClick={() => setShowForm(s => !s)}>{t('newOrder')}</button>
        )}
      </div>
      {showForm && (
        <form onSubmit={create} className="form-grid" style={{ margin: '12px 0' }}>
          <label>{t('pickup')}
            <input value={form.pickup_location}
                   onChange={e => setForm(f => ({ ...f, pickup_location: e.target.value }))} />
          </label>
          <label>{t('delivery')}
            <input value={form.delivery_location}
                   onChange={e => setForm(f => ({ ...f, delivery_location: e.target.value }))} />
          </label>
          <label>{t('pickupDate')}
            <input type="date" value={form.pickup_date}
                   onChange={e => setForm(f => ({ ...f, pickup_date: e.target.value }))} />
          </label>
          <label>{t('deliveryDate')}
            <input type="date" value={form.delivery_date}
                   onChange={e => setForm(f => ({ ...f, delivery_date: e.target.value }))} />
          </label>
          <label className="wide">{t('instructions')}
            <textarea rows={2} value={form.instructions}
                      onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))} />
          </label>
          <div className="wide" style={{ textAlign: 'right' }}>
            <button className="btn" disabled={busy}>{t('save')}</button>
          </div>
        </form>
      )}
      {error && <p className="error">{error}</p>}
      {orders.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('noOrders')}</p>}
      {orders.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('status')}</th><th>{t('pickup')}</th><th>{t('delivery')}</th>
                <th>{t('pickupDate')}</th><th>{t('createdBy')}</th>
                <th>{t('notes')}</th><th></th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => (
                <tr key={order.id}>
                  <td><OrderBadge status={order.status} /></td>
                  <td>{order.pickup_location}</td>
                  <td>{order.delivery_location}</td>
                  <td>{formatDate(order.pickup_date)}</td>
                  <td>{order.created_by_login}</td>
                  <td>{order.status === 'ODRZUCONE' ? order.rejection_reason : order.instructions}</td>
                  <td className="row">{actions(order)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rejectRow}
    </div>
  )
}

// Podświetlenie @wzmianek w treści wiadomości (backend wysyła powiadomienie
// tylko do istniejących userów z dostępem — tu tylko wizualne wyróżnienie).
export function renderWithMentions(body: string) {
  const parts = body.split(/(@[\w.-]+)/g)
  return parts.map((part, i) =>
    part.startsWith('@')
      ? <span key={i} className="mention">{part}</span>
      : part)
}

export function MessagesPanel({ container }: { container: Container }) {
  const t = useT()
  const [messages, setMessages] = useState<Message[]>([])
  const [body, setBody] = useState('')

  const load = useCallback(() => {
    api.get<Message[]>(`/api/containers/${container.id}/messages`)
      .then(setMessages).catch(() => {})
  }, [container.id])
  useEffect(() => load(), [load])

  const [sendError, setSendError] = useState('')
  const [sending, setSending] = useState(false)
  const send = async (event: FormEvent) => {
    event.preventDefault()
    if (!body.trim() || sending) return
    setSendError('')
    setSending(true)
    try {
      await api.post(`/api/containers/${container.id}/messages`, { body })
      setBody('')
      load()
    } catch (err) {
      // nie czyścimy pola przy błędzie, żeby nie zgubić treści wiadomości
      setSendError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('messages')}</h3>
      {messages.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('noMessages')}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        {messages.map(message => (
          <div key={message.id} style={{
            background: '#f5f8fd', borderRadius: 8, padding: '8px 12px',
            borderLeft: message.user_role === 'forwarder' ? '3px solid #b54708' : '3px solid var(--accent)',
          }}>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>
              <b>{message.user_full_name || message.user_login}</b>
              {message.user_role === 'forwarder' && ` (${t('role_forwarder')})`}
              {' · '}{formatDateTime(message.created_at)}
            </div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{renderWithMentions(message.body)}</div>
          </div>
        ))}
      </div>
      <form className="row" onSubmit={send}>
        <input style={{ flex: 1 }} aria-label={t('writeMessage')} placeholder={t('writeMessage')} value={body}
               onChange={e => setBody(e.target.value)} />
        <button className="btn" disabled={!body.trim() || sending}
                title={body.trim() ? undefined : t('hintTypeMessage')}>{t('send')}</button>
      </form>
      {sendError && <p className="error">{sendError}</p>}
    </div>
  )
}

export function AttachmentsPanel({ container, onChanged }: {
  container: Container
  onChanged?: () => void   // podmiana / usunięcie → status kontenera i kafelki (§4 pkt 29)
}) {
  const t = useT()
  const user = useUser()
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [docTypes, setDocTypes] = useState<{ id: number; name: string; is_required: boolean }[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sentInfo, setSentInfo] = useState('')
  // W5 #36: przed wysyłką pokazujemy podgląd wiadomości z szablonu (z listą braków)
  const [showPreview, setShowPreview] = useState(false)
  // nowe pliki wchodzą tylko przez poczekalnię (IntakePanel); tu Podmień/Usuń istniejących.
  // §4 pkt 48: sprzedaż tylko czyta
  const canUpload = user?.role !== 'warehouse' && user?.role !== 'sales'
  // wysyłka dokumentów do agencji celnej: transport (logistyka), zakupy, admin
  const canSendDocs = (user?.role === 'admin' || user?.role === 'logistics'
    || user?.role === 'purchasing') && !!container.customs_agency_id
  // kontener w obiegu celnym → pokazujemy checklistę braków
  const inCustomsFlow = !!container.customs_agency_id || container.customs_status !== 'BRAK'
  const missing = inCustomsFlow
    ? docTypes.filter(dt => dt.is_required
        && !attachments.some(a => a.document_type_id === dt.id)).map(dt => dt.name)
    : []

  const load = useCallback(() => {
    api.get<Attachment[]>(`/api/containers/${container.id}/attachments`)
      .then(r => setAttachments(Array.isArray(r) ? r : []))
      .catch(err => setError(errorMessage(err)))   // §4 pkt 48: błąd listy nie jest połykany
  }, [container.id])
  useEffect(() => load(), [load])
  useEffect(() => {
    api.get<typeof docTypes>('/api/customs/document-types?active_only=true')
      .then(setDocTypes).catch(() => {})
  }, [])

  const changed = () => { load(); onChanged?.() }

  const download = async (attachment: Attachment) => {
    try {
      await downloadFile(`/api/attachments/${attachment.id}/download`, attachment.filename)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const sendDocs = async (force: boolean) => {
    setBusy(true)
    setError('')
    setSentInfo('')
    try {
      // podgląd (z serwera) pokazał braki — potwierdzenie usera to świadome „mimo braków”
      await api.post(`/api/customs/containers/${container.id}/send-docs`, { force })
      setShowPreview(false)
      setSentInfo(t('docsSentToAgency'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('files')}</h3>
        <div className="row" style={{ gap: 8 }}>
          {attachments.length > 0 && user?.role !== 'warehouse' && (
            <button className="btn small secondary" disabled={busy}
                    onClick={() => downloadFile(`/api/containers/${container.id}/attachments/zip`,
                      `dokumenty_${container.container_no}.zip`).catch(err => setError(errorMessage(err)))}>
              {t('downloadAllZip')}
            </button>
          )}
          {canSendDocs && attachments.length > 0 && (
            <button className="btn small" disabled={busy} onClick={() => setShowPreview(true)}>
              {t('sendDocsToAgency')}
            </button>
          )}
        </div>
      </div>
      {missing.length > 0 && (
        <p style={{ fontSize: 13, margin: '6px 0 0' }}>
          <span className="badge cs-ZLECONA">{t('missingDocs')}</span>{' '}
          <span className="muted">{missing.join(', ')}</span>
        </p>
      )}
      {sentInfo && <p style={{ color: '#0e8a6a', fontSize: 14 }}>{sentInfo}</p>}
      {error && <p className="error">{error}</p>}
      {showPreview && (
        <SendDocsPreviewModal containerId={container.id} containerNo={container.container_no} busy={busy}
          onConfirm={sendDocs} onClose={() => setShowPreview(false)} />
      )}
      {attachments.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('noFiles')}</p>}
      {attachments.length > 0 && (
        <table className="grid">
          <thead>
            <tr><th>{t('name')}</th><th>{t('who')}</th><th>{t('when')}</th>
<th></th></tr>
          </thead>
          <tbody>
            {attachments.map(attachment => (
              <tr key={attachment.id}>
                <td>
                  {attachment.filename} <span style={{ color: 'var(--muted)' }}>
                  ({Math.max(1, Math.round(attachment.size / 1024))} kB)</span>
                  {attachment.document_type_name && (
                    <span className="badge cs-DOKUMENTY_KOMPLETNE" style={{ marginLeft: 6 }}>
                      {attachment.document_type_name}
                    </span>
                  )}
                  <SharedBadge attachment={attachment} />
                </td>
                <td>{attachment.uploaded_by_login}</td>
                <td>{formatDateTime(attachment.created_at)}</td>
                <td>
                  <button className="btn small secondary" onClick={() => download(attachment)}>
                    {t('download')}
                  </button>
                  {canUpload && <> <AttachmentActions attachment={attachment} containerId={container.id}
                    busy={busy} setBusy={setBusy} onChanged={changed} onError={setError}
                    linkClass="btn small secondary" /></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
