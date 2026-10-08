import { CircleXIcon, Inbox, TruckIcon } from 'lucide-react'
// Panel „Awizacje": zlecenia awizacji dwuetapowej (lista + szczegóły) i akcje logistyki.
// Kontrakt: backend/app/routers/avizo_requests.py; dozwolone akcje wg maszyny stanów
// z backend/app/avizo_workflow.py (backend i tak odbija niedozwolone przejście 409).
// Na dole: starsze propozycje zmian terminu (#59, /api/avizo-proposals), dopóki są.
import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { useT } from '../i18n'
import { formatDate, formatDateTime } from '../dates'
import { useForwarders } from './admin/shared'
import { useBusy } from '../useBusy'

const STATUSES = ['SENT_STAGE1', 'CONFIRMED_BY_FORWARDER', 'REJECTED', 'APPROVED_BY_US',
  'SENT_STAGE2', 'DRIVERS_SUBMITTED', 'EXPIRED', 'CLOSED', 'CANCELLED', 'DRAFT'] as const

const BADGE: Record<string, string> = {
  SENT_STAGE1: 'st-W_TRANSPORCIE', SENT_STAGE2: 'st-W_TRANSPORCIE',
  CONFIRMED_BY_FORWARDER: 'st-ODPRAWA', APPROVED_BY_US: 'st-DOSTARCZONY',
  DRIVERS_SUBMITTED: 'st-DOSTARCZONY', REJECTED: 'delayed', EXPIRED: 'delayed',
}

interface Mail { status: string; stage: number; error: string; sent_at: string | null }

interface RequestRow {
  id: number
  status: string
  forwarder_id: number
  forwarder: string
  company: string
  containers: string[]
  created_at: string
  reject_comment: string
  note: string
  last_mail: Mail | null
}

interface RequestDetail extends RequestRow {
  items: {
    container_id: number
    container_no: string
    notify_date: string | null
    slot_time: string | null
    driver_submitted: boolean
    answer: { decision: string; proposed_date: string | null; slot_time: string
              comment: string; submitted_at: string | null } | null
  }[]
  tokens: { id: number; stage: number }[]
  mails: (Mail & { id: number; kind: string; recipients: string; cc: string; attempts: number })[]
}

type Action = 'approve' | 'reject' | 'revoke' | 'resend' | 'cancel'

// które akcje ma sens pokazać w danym statusie (lustro TRANSITIONS z avizo_workflow.py)
export function allowedActions(d: Pick<RequestDetail, 'status' | 'tokens'>):
    { actions: Action[]; resendStage: 1 | 2 | null } {
  const lastStage = d.tokens.length ? d.tokens[d.tokens.length - 1].stage : 1
  const resendStage = ({ SENT_STAGE1: 1, REJECTED: 1, SENT_STAGE2: 2, APPROVED_BY_US: 2,
    EXPIRED: lastStage } as Record<string, number>)[d.status] as 1 | 2 | undefined
  const actions: Action[] = []
  if (d.status === 'CONFIRMED_BY_FORWARDER') actions.push('approve', 'reject')
  if (d.status === 'SENT_STAGE1' || d.status === 'SENT_STAGE2') actions.push('revoke')
  if (resendStage) actions.push('resend')
  if (!['CLOSED', 'CANCELLED', 'DRIVERS_SUBMITTED'].includes(d.status)) actions.push('cancel')
  return { actions, resendStage: resendStage ?? null }
}

const DECISION_KEY: Record<string, string> = {
  confirmed: 'av1Confirm', date_change: 'av1DateChange', problem: 'av1Problem',
}

function MailStatus({ mail }: { mail: Mail | null }) {
  const t = useT()
  if (!mail) return <span className="muted">—</span>
  return mail.status === 'failed'
    ? <span className="error" title={mail.error}><CircleXIcon size={14} /> {t('avrMailFailed')} ({t('avrStage')} {mail.stage})</span>
    : <span className="muted">✓ {t('avrMailSent')} ({t('avrStage')} {mail.stage})
        {mail.sent_at && ` · ${formatDateTime(mail.sent_at)}`}</span>
}

function RequestDetails({ id, onChanged }: { id: number; onChanged: () => void }) {
  const t = useT()
  const { showToast } = useToast()
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<Action | null>(null)   // inline potwierdzenie
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDetail(null); setPending(null); setError('')
    api.get<RequestDetail>(`/api/avizo-requests/${id}`).then(setDetail)
      .catch(err => setError(errorMessage(err)))
  }, [id])

  if (!detail) return error ? <p className="error">{error}</p> : <Skeleton rows={3} />
  const { actions, resendStage } = allowedActions(detail)

  const run = async (action: Action) => {
    setBusy(true); setError('')
    try {
      const path = `/api/avizo-requests/${id}/${action}`
        + (action === 'resend' ? `?stage=${resendStage}` : '')
      setDetail(await api.post<RequestDetail>(path,
        action === 'reject' ? { comment: comment.trim() } : {}))
      setPending(null); setComment('')
      showToast(t('toastSaved'))
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally { setBusy(false) }
  }

  const label: Record<Action, string> = {
    approve: t('avrApprove'), reject: t('avrReject'), revoke: t('avrRevoke'),
    resend: `${t('avrResend')} (${t('avrStage')} ${resendStage})`, cancel: t('avrCancel'),
  }

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="mini-title">#{detail.id} · {detail.forwarder} · {detail.company}</div>
      {detail.note && <p className="muted">{t('notes')}: {detail.note}</p>}
      {detail.reject_comment && <p className="muted">{t('avrReject')}: {detail.reject_comment}</p>}

      <div className="avr-actions">
        {pending ? (
          <div className="avr-confirm" role="group" aria-label={label[pending]}>
            <b>{label[pending]} — {t('avrSure')}</b>
            {pending === 'reject' && (
              <textarea rows={2} autoFocus placeholder={t('avrRejectComment')} value={comment}
                        aria-label={t('avrRejectComment')} maxLength={2000}
                        onChange={e => setComment(e.target.value)} />
            )}
            <button className={`btn small${pending === 'cancel' || pending === 'reject' ? ' danger' : ''}`}
                    disabled={busy || (pending === 'reject' && comment.trim().length < 3)}
                    onClick={() => void run(pending)}>{t('avrYes')}</button>
            <button className="btn small secondary" disabled={busy}
                    onClick={() => { setPending(null); setComment('') }}>{t('avrBack')}</button>
          </div>
        ) : actions.map(a => (
          <button key={a} className={`btn small${a === 'approve' ? '' : ' secondary'}`}
                  onClick={() => setPending(a)}>{label[a]}</button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}

      <div className="mini-title">{t('avrAnswers')}</div>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid">
          <thead><tr>
            <th>{t('containerNo')}</th><th>{t('notifyDate')}</th><th>{t('status')}</th>
            <th>{t('av1NewDate')}</th><th>{t('avizoSlot')}</th><th>{t('av1Comment')}</th>
          </tr></thead>
          <tbody>
            {detail.items.map(i => (
              <tr key={i.container_id}>
                <td className="mono strong">
                  <Link to={`/kontenery/${i.container_id}`}>{i.container_no}</Link>
                  {i.driver_submitted && <span title={t('avrDriverDone')}> <TruckIcon size={14} /></span>}
                </td>
                <td className="mono">{formatDate(i.notify_date)}{i.slot_time && ` ${i.slot_time}`}</td>
                <td>{i.answer ? <b>{t(DECISION_KEY[i.answer.decision] ?? i.answer.decision)}</b>
                  : <span className="muted">{t('avrNoAnswer')}</span>}</td>
                <td className="mono">{i.answer?.proposed_date ? formatDate(i.answer.proposed_date) : ''}</td>
                <td className="mono">{i.answer?.slot_time}</td>
                <td>{i.answer?.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mini-title" style={{ marginTop: 12 }}>{t('avrMails')}</div>
      {detail.mails.length === 0 ? <p className="muted">—</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table className="grid">
            <thead><tr>
              <th>{t('avrStage')}</th><th>{t('avrRecipients')}</th><th>{t('status')}</th>
              <th>{t('avrCreated')}</th>
            </tr></thead>
            <tbody>
              {detail.mails.map(m => (
                <tr key={m.id}>
                  <td>{m.stage} · {m.kind}</td>
                  <td>{m.recipients}{m.cc && <span className="muted"> (cc: {m.cc})</span>}</td>
                  <td>{m.status === 'failed'
                    ? <span className="error"><CircleXIcon size={14} /> {t('avrMailFailed')} ×{m.attempts}: {m.error}</span>
                    : <span>✓ {m.status || '…'}</span>}</td>
                  <td className="mono">{m.sent_at ? formatDateTime(m.sent_at) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// #59: starsze propozycje zmian terminu (endpoint zostaje dla linków sprzed etapów)
interface Proposal {
  id: number; container_id: number; container_no: string; current_notify_date: string | null
  proposed_date: string; proposed_time: string; note: string; forwarder: string
}

function LegacyProposals() {
  const t = useT()
  const [items, setItems] = useState<Proposal[]>([])
  const [reason, setReason] = useState<Record<number, string>>({})
  const [error, setError] = useState('')
  const load = useCallback(() => {
    api.get<Proposal[]>('/api/avizo-proposals').then(setItems).catch(() => setItems([]))
  }, [])
  useEffect(() => load(), [load])
  const { busy, run } = useBusy()   // dwuklik „Akceptuj” = jeden POST
  if (items.length === 0) return null
  const act = (id: number, action: 'accept' | 'reject') => run(() =>
    api.post(`/api/avizo-proposals/${id}/${action}`,
      action === 'reject' ? { reason: reason[id] || '' } : {})
      .then(load).catch(err => setError(errorMessage(err))))
  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="mini-title">{t('avrLegacy')}</div>
      {error && <p className="error">{error}</p>}
      <table className="grid">
        <tbody>
          {items.map(p => (
            <tr key={p.id}>
              <td className="mono strong"><Link to={`/kontenery/${p.container_id}`}>{p.container_no}</Link></td>
              <td>{p.forwarder}</td>
              <td className="mono">{formatDate(p.current_notify_date)} → {formatDate(p.proposed_date)}
                {p.proposed_time && ` ${p.proposed_time}`}</td>
              <td>{p.note}</td>
              <td>
                <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <button className="btn small" disabled={busy} onClick={() => act(p.id, 'accept')}>{t('avpAccept')}</button>
                  <input aria-label={t('avpRejectReason')} placeholder={t('avpRejectReason')} value={reason[p.id] ?? ''}
                         onChange={e => setReason(s => ({ ...s, [p.id]: e.target.value }))} />
                  <button className="btn small danger" disabled={busy} onClick={() => act(p.id, 'reject')}>{t('avpReject')}</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AvizoProposalsPage() {
  const t = useT()
  const forwarders = useForwarders()
  const [status, setStatus] = useState('')
  const [forwarderId, setForwarderId] = useState('')
  const [rows, setRows] = useState<RequestRow[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<number | null>(null)

  const load = useCallback(() => {
    const qs = new URLSearchParams()
    if (status) qs.set('status', status)
    if (forwarderId) qs.set('forwarder_id', forwarderId)
    api.get<RequestRow[]>(`/api/avizo-requests${qs.toString() ? `?${qs}` : ''}`)
      .then(r => { setRows(r); setError('') })
      .catch(err => setError(errorMessage(err)))
  }, [status, forwarderId])
  useEffect(() => load(), [load])

  return (
    <main className="page">
      <h1>{t('avrTitle')}</h1>
      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <select value={status} aria-label={t('status')} onChange={e => setStatus(e.target.value)}>
          <option value="">{t('avrAllStatuses')}</option>
          {STATUSES.map(s => <option key={s} value={s}>{t(`avrSt_${s}`)}</option>)}
        </select>
        <select value={forwarderId} aria-label={t('forwarder')}
                onChange={e => setForwarderId(e.target.value)}>
          <option value="">{t('avrAllForwarders')}</option>
          {forwarders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      {error && !rows && <LoadError message={error} onRetry={load} />}
      {error && rows && <p className="error">{error}</p>}
      {!rows && !error && <Skeleton rows={4} />}
      {rows && rows.length === 0 && <EmptyState icon={Inbox} title={t('avrNone')} />}
      {rows && rows.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="grid">
            <thead><tr>
              <th>#</th><th>{t('status')}</th><th>{t('forwarder')}</th><th>{t('company')}</th>
              <th>{t('avrContainers')}</th><th>{t('avrCreated')}</th><th>{t('avrLastMail')}</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <Fragment key={r.id}>
                  <tr className={`avr-row${selected === r.id ? ' selected' : ''}`} tabIndex={0}
                      aria-expanded={selected === r.id}
                      onClick={() => setSelected(s => s === r.id ? null : r.id)}
                      onKeyDown={e => { if (e.key === 'Enter') setSelected(s => s === r.id ? null : r.id) }}>
                    <td className="mono">{r.id}</td>
                    <td><span className={`badge ${BADGE[r.status] ?? 'st-ZAPOWIEDZIANY'}`}>
                      {t(`avrSt_${r.status}`)}</span></td>
                    <td>{r.forwarder}</td>
                    <td>{r.company}</td>
                    <td title={r.containers.join(', ')}>{r.containers.length}</td>
                    <td className="mono">{formatDateTime(r.created_at)}</td>
                    <td><MailStatus mail={r.last_mail} /></td>
                  </tr>
                  {selected === r.id && (
                    <tr><td colSpan={7}><RequestDetails id={r.id} onChanged={load} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <LegacyProposals />
    </main>
  )
}
