import { BotIcon, CameraIcon, FileTextIcon, MailIcon, TriangleAlertIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { Modal } from '../components'
import type { Complaint, ComplaintRecipient } from '../types'
import { COMPLAINT_STATUS_BADGE } from './ComplaintsPanel'
import { formatDate, formatDateTime } from '../dates'
import { LoadError, Skeleton } from '../feedback'
import { deadlineTone } from './complaintUtils'
import { useConfirm } from '../ConfirmDialog'

const RECIPIENTS: ComplaintRecipient[] = ['PRZEWOZNIK', 'UBEZPIECZYCIEL', 'DOSTAWCA']
const TONE_CLASS = { ok: 'st-ZREALIZOWANY', warn: 'st-ODPRAWA', over: 'st-W_TRANSPORCIE' } as const

export default function ComplaintDetailPage() {
  const { id } = useParams()
  const t = useT()
  const { confirm } = useConfirm()
  const user = useUser()
  const navigate = useNavigate()
  const [c, setC] = useState<Complaint | null>(null)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [showSend, setShowSend] = useState(false)
  const [target, setTarget] = useState({ target_email: '', target_label: '', message: '' })
  const [busy, setBusy] = useState(false)
  const [costs, setCosts] = useState({ claim_amount: '', recovered_amount: '', claim_currency: 'PLN' })
  const fileRef = useRef<HTMLInputElement>(null)
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'

  const patch = async (body: Record<string, unknown>) => {
    if (busy) return
    setBusy(true); setError('')
    try {
      const updated = await api.patch<Complaint>(`/api/complaints/${id}`, body)
      setC(updated)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const saveCosts = () => patch({
    claim_amount: costs.claim_amount === '' ? null : Number(costs.claim_amount),
    recovered_amount: costs.recovered_amount === '' ? null : Number(costs.recovered_amount),
    claim_currency: costs.claim_currency || 'PLN',
  })

  const load = useCallback(() => {
    setLoadError('')
    api.get<Complaint>(`/api/complaints/${id}`).then(data => {
      setC(data)
      setCosts({
        claim_amount: data.claim_amount === null ? '' : String(data.claim_amount),
        recovered_amount: data.recovered_amount === null ? '' : String(data.recovered_amount),
        claim_currency: data.claim_currency || 'PLN',
      })
    }).catch(err => setLoadError(errorMessage(err)))
  }, [id])
  useEffect(() => load(), [load])

  const addPhotos = async (list: FileList | null) => {
    if (!list) return
    setBusy(true); setError('')
    try {
      for (const file of Array.from(list)) {
        await api.upload(`/api/complaints/${id}/photos`, file)
      }
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (status: string, note = '') => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post(`/api/complaints/${id}/status`, { status, note })
      load()  // odświeżamy dopiero po udanej zmianie (błąd nie udaje sukcesu)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const report = async () => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post(`/api/complaints/${id}/report`, {})
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    setBusy(true); setError('')
    try {
      await api.post(`/api/complaints/${id}/send`, target)
      setShowSend(false)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (loadError) return <main className="page"><LoadError message={loadError} onRetry={load} /></main>
  if (!c) return <main className="page"><Skeleton rows={6} /></main>

  const item = (label: string, value: React.ReactNode) => (
    <div className="detail-grid-item"><b>{label}</b>{value || '—'}</div>
  )
  const dt = (v: string | null) => v ? formatDateTime(v) : '—'

  return (
    <main className="page" style={{ maxWidth: 1000 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 style={{ margin: 0 }}>
          <span className="mono">{c.number}</span>{' '}
          <span className={`badge ${COMPLAINT_STATUS_BADGE[c.status]}`}>{t(`cst_${c.status}`)}</span>
          {' '}<span className="badge st-ODPRAWA">{t(c.kind === 'REKLAMACJA' ? 'complaintKindClaim' : 'complaintKindProblem')}</span>
          {c.auto_draft && <>{' '}<span className="badge st-ZAPOWIEDZIANY"><BotIcon size={14} /> {t('complaintAutoDraft')}</span></>}
        </h2>
        <button className="btn small secondary" onClick={() => navigate(`/kontenery/${c.container_id}`)}>
          {t('containerNo')}: {c.container_no}
        </button>
      </div>

      <div className="panel">
        <div className="detail-grid">
          {item(t('complaintProblems'), c.problems.join(', '))}
          {item(t('createdBy'), c.created_by_login)}
          {item(t('when'), dt(c.created_at))}
          {item(t('complaintAge'), `${c.age_days} ${t('complaintDays')}`)}
          {item(t('complaintReported'), dt(c.reported_at))}
          {item(t('complaintSent'), c.sent_target ? `${c.sent_target} · ${dt(c.sent_at)}` : '—')}
          {item(t('complaintResponse'), dt(c.response_at))}
          {item(t('complaintRecipient'), canEdit ? (
            <select aria-label={t('complaintRecipient')} value={c.recipient_type} disabled={busy} data-testid="recipient-select"
                    onChange={e => patch({ recipient_type: e.target.value })}>
              <option value="">{t('complaintRecipientNone')}</option>
              {RECIPIENTS.map(r => <option key={r} value={r}>{t(`crt_${r}`)}</option>)}
            </select>
          ) : (c.recipient_type ? t(`crt_${c.recipient_type}`) : '—'))}
          {item(t('complaintDeadline'), c.deadline_at ? (() => {
            const tone = deadlineTone(c.deadline_days_left)
            return (
              <span>
                {formatDate(c.deadline_at)}{' '}
                {tone && (
                  <span className={`badge ${TONE_CLASS[tone]}`} data-testid="deadline-clock">
                    ⏳ {tone === 'over'
                      ? t('complaintDeadlineOver')
                      : t('complaintDeadlineLeft').replace('{n}', String(c.deadline_days_left))}
                  </span>
                )}
              </span>
            )
          })() : '—')}
        </div>
        {c.description && <p><b>{t('complaintDesc')}:</b> {c.description}</p>}
        {c.driver_note && <p><b>{t('complaintDriverNote')}:</b> {c.driver_note}</p>}
      </div>

      <div className="panel">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>{t('complaintPhotos')} ({c.photos?.length ?? 0})</h3>
          <button className="btn small secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
            <CameraIcon size={14} /> {t('complaintAddPhoto')}
          </button>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" multiple
                 style={{ display: 'none' }} onChange={e => addPhotos(e.target.files)} />
        </div>
        <div className="photo-thumbs" style={{ marginTop: 10 }}>
          {(c.photos ?? []).map(p => (
            <a key={p.id} className="thumb" href={`/api/complaint-photos/${p.id}/download`}
               target="_blank" rel="noreferrer" title={p.caption || p.filename}>
              <img src={`/api/complaint-photos/${p.id}/download`} alt={p.caption}
                   width={92} height={92} loading="lazy" decoding="async" />
            </a>
          ))}
          {(c.photos?.length ?? 0) === 0 && <span className="muted">{t('complaintNoPhotos')}</span>}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t('complaintCosts')}</h3>
        <div className="row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label className="cform-label">{t('complaintClaimAmount')}
            <input type="number" min={0} step="0.01" value={costs.claim_amount} disabled={!canEdit || busy}
                   onChange={e => setCosts(s => ({ ...s, claim_amount: e.target.value }))} />
          </label>
          <label className="cform-label">{t('complaintRecovered')}
            <input type="number" min={0} step="0.01" value={costs.recovered_amount} disabled={!canEdit || busy}
                   onChange={e => setCosts(s => ({ ...s, recovered_amount: e.target.value }))} />
          </label>
          <label className="cform-label">{t('complaintCurrency')}
            <input value={costs.claim_currency} maxLength={3} style={{ width: 70 }} disabled={!canEdit || busy}
                   onChange={e => setCosts(s => ({ ...s, claim_currency: e.target.value.toUpperCase() }))} />
          </label>
          {canEdit && <button className="btn small" disabled={busy} onClick={saveCosts}>{t('save')}</button>}
        </div>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t('complaintActions')}</h3>
        <div className="row">
          <button className="btn secondary"
                  onClick={() => window.open(`/api/complaints/${c.id}/letter?lang=pl`, '_blank')}>
            <FileTextIcon size={14} /> {t('complaintLetterPl')}
          </button>
          <button className="btn secondary"
                  onClick={() => window.open(`/api/complaints/${c.id}/letter?lang=en`, '_blank')}>
            <FileTextIcon size={14} /> {t('complaintLetterEn')}
          </button>
          {c.status !== 'ZGLOSZONA' && c.status !== 'ZAMKNIETA' && (
            <button className="btn secondary" disabled={busy} onClick={report}><TriangleAlertIcon size={14} /> {t('complaintReport')}</button>
          )}
          {canEdit && c.status !== 'ZAMKNIETA' && (
            <button className="btn" onClick={() => setShowSend(true)}><MailIcon size={14} /> {t('complaintSendClaim')}</button>
          )}
          {canEdit && c.status === 'WYSLANA' && (
            <button className="btn secondary" disabled={busy} onClick={() => setStatus('ODPOWIEDZ')}>
              {t('complaintMarkResponse')}
            </button>
          )}
          {canEdit && c.status !== 'ZAMKNIETA' && (
            <button className="btn secondary" disabled={busy} onClick={async () => (await confirm(t('confirmCloseComplaint'))) && setStatus('ZAMKNIETA')}>
              {t('complaintClose')}
            </button>
          )}
        </div>
      </div>

      {showSend && (
        <Modal title={t('complaintSendClaim')} onClose={() => setShowSend(false)} busy={busy} width={520}>
            <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 0 }}>
              {t('complaintSendInfo')}
            </p>
            <label className="cform-label">{t('email')}
              <input type="email" value={target.target_email}
                     onChange={e => setTarget(s => ({ ...s, target_email: e.target.value }))} />
            </label>
            <label className="cform-label">{t('complaintTargetLabel')}
              <input value={target.target_label} placeholder="spedycja SPEDALFA / ubezpieczyciel"
                     onChange={e => setTarget(s => ({ ...s, target_label: e.target.value }))} />
            </label>
            <label className="cform-label">{t('complaintMessage')}
              <textarea rows={3} value={target.message}
                        onChange={e => setTarget(s => ({ ...s, message: e.target.value }))} />
            </label>
            {error && <p className="error">{error}</p>}
            <div className="actions">
              <button className="btn secondary" disabled={busy} onClick={() => setShowSend(false)}>
                {t('cancel')}
              </button>
              <button className="btn" disabled={busy || !target.target_email} onClick={send}>
                {busy ? t('sending') : t('sendEmail')}
              </button>
            </div>
        </Modal>
      )}
    </main>
  )
}
