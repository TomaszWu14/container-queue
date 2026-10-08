// Kolejka Enterprise (plaster 5): zakładki szuflady Dokumenty / Wiadomości / Koszty —
// wyłącznie istniejące endpointy (izolacja po stronie backendu):
//   GET /containers/{id}/attachments (nowe pliki: poczekalnia IntakePanel), GET /attachments/{id}/download,
//   GET/POST /containers/{id}/messages, GET /freight-invoices?container_id=.
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useUser } from '../../App'
import { api, downloadFile, errorMessage } from '../../api'
import { AttachmentActions, SharedBadge } from '../../AttachmentActions'
import { renderWithMentions } from '../../collaboration'
import { formatDate, formatDateTime } from '../../dates'
import { BatchDocuments } from './BatchDocuments'
import { IntakePanel } from '../../IntakeWaitingRoom'
import { useLocale, useT } from '../../i18n'
import type { Attachment, Message } from '../../types'

type Freight = {
  id: number; bl_number: string; invoice_number: string; forwarder_name: string | null
  amount: number | null; currency: string; amount_per_container: number | null
  containers: { id: number }[]; status: string
}

/** Dane zakładek ładowane przy otwarciu kontenera — liczniki w nagłówkach zakładek.
    Koszty: null = brak uprawnień do faktur frachtowych (rola) → zakładka ukryta. */
export function useDrawerData(containerId: number) {
  const [files, setFiles] = useState<Attachment[] | null>(null)
  const [messages, setMessages] = useState<Message[] | null>(null)
  const [costs, setCosts] = useState<Freight[] | null | 'forbidden'>(null)
  const loadFiles = useCallback(() => {
    api.get<Attachment[]>(`/api/containers/${containerId}/attachments`)
      .then(r => setFiles(Array.isArray(r) ? r : [])).catch(() => setFiles([]))
  }, [containerId])
  const loadMessages = useCallback(() => {
    api.get<Message[]>(`/api/containers/${containerId}/messages`)
      .then(r => setMessages(Array.isArray(r) ? r : [])).catch(() => setMessages([]))
  }, [containerId])
  useEffect(() => {
    setFiles(null); setMessages(null); setCosts(null)
    loadFiles(); loadMessages()
    api.get<Freight[]>(`/api/freight-invoices?container_id=${containerId}`)
      .then(r => setCosts(Array.isArray(r) ? r : [])).catch(() => setCosts('forbidden'))
  }, [containerId, loadFiles, loadMessages])
  return { files, messages, costs, loadFiles, loadMessages }
}
export type DrawerData = ReturnType<typeof useDrawerData>

const ext = (name: string) => (name.split('.').pop() ?? '').slice(0, 4).toUpperCase()
const size = (b: number) => (b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} kB`)

export function DocumentsTab({ containerId, d }: { containerId: number; d: DrawerData }) {
  const t = useT()
  const user = useUser()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const canUpload = user?.role !== 'warehouse'   // Podmień/Usuń istniejących (backend i tak pilnuje)
  if (d.files === null) return <span className="kq-dim">…</span>
  return (
    <>
      {d.files.length === 0 && <span className="kq-dim">{t('noFiles')}</span>}
      <ul className="kq-docs">
        {d.files.map(a => (
          <li key={a.id}>
            <i className={`kq-doc-ico${ext(a.filename) === 'PDF' ? ' pdf' : ''}`}>{ext(a.filename) || '—'}</i>
            <div className="kq-doc-main">
              <b title={a.filename}>{a.filename}<SharedBadge attachment={a} /></b>
              <small>{[a.document_type_name, size(a.size), formatDate(a.created_at), a.uploaded_by_login].filter(Boolean).join(' · ')}</small>
            </div>
            <button type="button" className="kq-link"
                    onClick={() => downloadFile(`/api/attachments/${a.id}/download`, a.filename)
                      .catch(err => setError(errorMessage(err)))}>{t('download')}</button>
            {canUpload && <AttachmentActions attachment={a} containerId={containerId} busy={busy} setBusy={setBusy}
                                             onChanged={d.loadFiles} onError={setError} linkClass="kq-link" />}
          </li>
        ))}
      </ul>
      <BatchDocuments containerId={containerId} refreshKey={d.files} />
      <IntakePanel containerId={containerId} onChanged={d.loadFiles} />
      {error && <p className="error">{error}</p>}
    </>
  )
}

export function MessagesTab({ containerId, d }: { containerId: number; d: DrawerData }) {
  const t = useT()
  const user = useUser()
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const send = async (e: FormEvent) => {
    e.preventDefault()
    if (!body.trim() || sending) return
    setSending(true); setError('')
    try {
      await api.post(`/api/containers/${containerId}/messages`, { body })
      setBody('')
      d.loadMessages()
    } catch (err) { setError(errorMessage(err)) } finally { setSending(false) }   // treść zostaje przy błędzie
  }
  if (d.messages === null) return <span className="kq-dim">…</span>
  return (
    <>
      {d.messages.length === 0 && <span className="kq-dim">{t('noMessages')}</span>}
      <div className="kq-msgs">
        {d.messages.map(m => {
          const mine = !!user && m.user_login === user.login
          return (
            <div key={m.id} className={`kq-msg${mine ? ' mine' : ''}`}>
              <small>{m.user_full_name || m.user_login} · {formatDateTime(m.created_at)}</small>
              <div className="kq-bubble">{renderWithMentions(m.body)}</div>
            </div>
          )
        })}
      </div>
      <form className="kq-msg-form" onSubmit={send}>
        <textarea rows={2} placeholder={t('writeMessage')} aria-label={t('writeMessage')}
                  value={body} onChange={e => setBody(e.target.value)} />
        <button className="btn small" disabled={!body.trim() || sending}>{t('send')}</button>
      </form>
      {error && <p className="error">{error}</p>}
    </>
  )
}

/** Sumy per waluta — bez przeliczania kursów (faktury bywają w USD i EUR). */
export function costTotals(rows: Freight[]): [string, number][] {
  const sums = new Map<string, number>()
  for (const r of rows) {
    const v = r.amount_per_container ?? r.amount
    if (v != null) sums.set(r.currency, (sums.get(r.currency) ?? 0) + Number(v))
  }
  return [...sums.entries()]
}

const money = (v: number, cur: string, locale: string) =>
  `${v.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`

export function CostsTab({ rows }: { rows: Freight[] }) {
  const t = useT()
  const locale = useLocale()
  if (rows.length === 0) return <span className="kq-dim">{t('kqdNoCosts')}</span>
  return (
    <dl className="kq-costs">
      {rows.map(r => {
        const v = r.amount_per_container ?? r.amount
        const shared = r.containers.length > 1
        return (
          <div key={r.id}>
            <dt>{t('kqdFreight')} {r.bl_number || r.invoice_number}
              {r.forwarder_name && <small> · {r.forwarder_name}</small>}
              {shared && <small title={v != null && r.amount != null ? money(Number(r.amount), r.currency, locale) : undefined}>
                {' '}· {t('kqdCostShare').replace('{n}', String(r.containers.length))}</small>}
            </dt>
            <dd className="mono">{v != null ? money(Number(v), r.currency, locale) : '—'}</dd>
          </div>
        )
      })}
      {costTotals(rows).map(([cur, sum]) => (
        <div key={cur} className="kq-costs-total">
          <dt>{t('kqdTotal')}</dt><dd className="mono">{money(sum, cur, locale)}</dd>
        </div>
      ))}
    </dl>
  )
}
