import { CircleCheckIcon, TriangleAlertIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useT } from '../../i18n'
import { formatDateTime } from '../../dates'
import type { Named, TransportJob } from '../../types'
import { money, useSubmit, type OnAction } from './shared'

// Jeden komponent zamiast zdublowanych ShipmentAgentPanel/WinnerAgentForm.
// mode='logistics': logistyka po wyborze zwycięzcy — edycja numeru przesyłki (PATCH)
//                   + podgląd agenta zgłoszonego przez spedycję.
// mode='winner':    zwycięska spedycja — potwierdzenie + pełny formularz agenta (POST /agent).
export function AgentPanel({ job, onAction, mode }: {
  job: TransportJob
  onAction: OnAction
  mode: 'logistics' | 'winner'
}) {
  const t = useT()
  const [name, setName] = useState(job.agent_name ?? '')
  const [phone, setPhone] = useState(job.agent_phone ?? '')
  const [company, setCompany] = useState(job.agent_company ?? '')
  const [ship, setShip] = useState(job.shipment_number ?? '')
  const { busy, run } = useSubmit()

  if (mode === 'logistics') {
    return (
      <div className="panel quote-form quote-subpanel">
        <h3 className="mt0">{t('quoteAssignment')}</h3>
        <form onSubmit={e => { e.preventDefault(); run(() => onAction(() =>
          api.patch<TransportJob>(`/api/transport-jobs/${job.id}`, { shipment_number: ship }))) }}>
        <label className="lbl-sm">{t('quoteShipment')}
          <div className="row gap-8">
            <input className="grow" value={ship} onChange={e => setShip(e.target.value)}
                   placeholder="BK-..." />
            <button type="submit" className="btn small"
                    disabled={busy || ship === (job.shipment_number ?? '')}>{t('save')}</button>
          </div>
        </label>
        </form>
        {job.agent_name
          ? <p className="muted txt-sm">
              <b>{t('quoteAgent')}:</b> {job.agent_name}
              {job.agent_phone ? ` · ${job.agent_phone}` : ''}
              {job.agent_company ? ` · ${job.agent_company}` : ''}
              {job.agent_submitted_at ? ` (${formatDateTime(job.agent_submitted_at)})` : ''}
            </p>
          : <p className="muted txt-sm">{t('quoteAgentPending')}</p>}
      </div>
    )
  }

  return (
    <div className="panel quote-form quote-subpanel">
      <p className="quote-won mt0">
        <CircleCheckIcon size={14} /> {t('quoteYouWon')}{job.my_quote ? ` (${money(job.my_quote)})` : ''}
      </p>
      <h3 className="h3-tight">{t('quoteAgentForm')}</h3>
      <form onSubmit={e => { e.preventDefault(); run(() => onAction(() =>
        api.post<TransportJob>(`/api/transport-jobs/${job.id}/agent`,
          { agent_name: name, agent_phone: phone, agent_company: company, shipment_number: ship }))) }}>
      <div className="form-grid">
        <label>{t('fullName')} *
          <input value={name} onChange={e => setName(e.target.value)} />
        </label>
        <label>{t('phone')} *
          <input value={phone} onChange={e => setPhone(e.target.value)} />
        </label>
        <label>{t('quoteAgentCompany')} *
          <input value={company} onChange={e => setCompany(e.target.value)} />
        </label>
        <label>{t('quoteShipment')}
          <input value={ship} onChange={e => setShip(e.target.value)} placeholder="BK-..." />
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="btn"
                disabled={busy || !name.trim() || !phone.trim() || !company.trim()}>
          {busy ? t('loading') : (job.agent_submitted_at ? t('quoteUpdate') : t('quoteSubmit'))}
        </button>
      </div>
      </form>
      {job.agent_submitted_at && (
        <p className="muted txt-xs">
          {t('quoteSubmitted')}: {formatDateTime(job.agent_submitted_at)}
        </p>
      )}
      <PriceChangeForm job={job} onAction={onAction} />
    </div>
  )
}

// Zwycięska spedycja zgłasza pilną zmianę ceny (wiersz 21).
export function PriceChangeForm({ job, onAction }: { job: TransportJob; onAction: OnAction }) {
  const t = useT()
  const q = job.my_quote
  const [amount, setAmount] = useState(q?.revised_amount ?? '')
  const [note, setNote] = useState(q?.revised_note ?? '')
  const { busy, run } = useSubmit()
  return (
    <div className="price-change">
      <h3 className="h3-tight"><TriangleAlertIcon size="1em" /> {t('quotePriceChange')}</h3>
      <p className="muted txt-xs mt0">{t('quotePriceChangeHint')}</p>
      <form onSubmit={e => { e.preventDefault(); run(() => onAction(() =>
        api.post<TransportJob>(`/api/transport-jobs/${job.id}/price-change`,
          // polski format („1 250,50") → „1250.50"; backend (Decimal) nie zna przecinka
          { revised_amount: String(amount).replace(/\s/g, '').replace(',', '.'),
            revised_note: note }))) }}>
      <div className="form-grid">
        <label>{t('quoteNewAmount')} *
          <input value={amount} onChange={e => setAmount(e.target.value)} inputMode="decimal" />
        </label>
        <label>{t('quoteCancelReason')}
          <input value={note} onChange={e => setNote(e.target.value)} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="btn secondary" disabled={busy || !String(amount).trim()}>
          {busy ? t('loading') : t('quotePriceChange')}
        </button>
      </div>
      </form>
      {q?.revised_at && (
        <p className="muted txt-xs">
          {t('quoteSubmitted')}: {formatDateTime(q.revised_at)}
        </p>
      )}
    </div>
  )
}

// Formularz oferty spedytora (lub przekierowanie do panelu zwycięzcy po rozstrzygnięciu).
export function ForwarderQuote({ job, onAction }: { job: TransportJob; onAction: OnAction }) {
  const t = useT()
  const q = job.my_quote
  const [amount, setAmount] = useState(q?.amount ?? '')
  const [currency, setCurrency] = useState(q?.currency ?? 'USD')
  const [validUntil, setValidUntil] = useState(q?.valid_until ?? '')
  const [carrierId, setCarrierId] = useState<number | null>(q?.carrier_id ?? null)
  const [etd, setEtd] = useState(q?.etd ?? '')
  const [eta, setEta] = useState(q?.eta ?? '')
  const [transit, setTransit] = useState(q?.transit_time_days != null ? String(q.transit_time_days) : '')
  const [noEquip, setNoEquip] = useState(q?.no_equipment ?? false)
  const [canRoll, setCanRoll] = useState(q?.can_roll_booking ?? false)
  const [note, setNote] = useState(q?.note ?? '')
  const [carriers, setCarriers] = useState<Named[]>([])
  const { busy, run } = useSubmit()
  useEffect(() => { api.get<Named[]>('/api/carriers').then(setCarriers).catch(() => setCarriers([])) }, [])

  if (job.status === 'ZLECONE') {
    if (q?.status !== 'WYBRANA') {
      return <p className="muted quote-subpanel-gap">{t('quoteYouLost')}</p>
    }
    return <AgentPanel job={job} onAction={onAction} mode="winner" />
  }
  if (job.kpi.deadline_passed) {
    return <p className="quote-late quote-subpanel-gap">⏱ {t('quoteDeadlinePassed')}</p>
  }
  return (
    <div className="panel quote-form quote-subpanel">
      <h3 className="mt0">{t('quoteYourOffer')}</h3>
      <form onSubmit={e => { e.preventDefault(); run(() => onAction(() =>
        api.post<TransportJob>(`/api/transport-jobs/${job.id}/quote`, {
          amount, currency, valid_until: validUntil || null,
          carrier_id: carrierId, etd: etd || null, eta: eta || null,
          transit_time_days: transit === '' ? null : Number(transit),
          no_equipment: noEquip, can_roll_booking: canRoll, note,
        }))) }}>
      <div className="form-grid">
        <label>{t('quoteAmount')}
          <input type="number" min="0" step="0.01" value={amount}
                 onChange={e => setAmount(e.target.value)} />
        </label>
        <label>{t('zlCurrency')}
          <select value={currency} onChange={e => setCurrency(e.target.value)}>
            {['USD', 'EUR', 'PLN'].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label>{t('carriers')}
          <select value={String(carrierId ?? '')}
                  onChange={e => setCarrierId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">—</option>
            {carriers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>ETD
          <input type="date" value={etd} onChange={e => setEtd(e.target.value)} />
        </label>
        <label>ETA
          <input type="date" value={eta} onChange={e => setEta(e.target.value)} />
        </label>
        <label>{t('zlTransit')}
          <input type="number" min="0" value={transit} onChange={e => setTransit(e.target.value)} />
        </label>
        <label>{t('quoteValid')}
          <input type="date" value={validUntil} onChange={e => setValidUntil(e.target.value)} />
        </label>
        <label className="row check-row">
          <input type="checkbox" checked={noEquip} onChange={e => setNoEquip(e.target.checked)} />
          {t('quoteNoEquip')}
        </label>
        <label className="row check-row">
          <input type="checkbox" checked={canRoll} onChange={e => setCanRoll(e.target.checked)} />
          {t('quoteRoll')}
        </label>
        <label className="wide">{t('notes')}
          <textarea rows={2} value={note} onChange={e => setNote(e.target.value)} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="btn" disabled={busy || !amount}>
          {busy ? t('loading') : (q?.status === 'WYCENIONA' ? t('quoteUpdate') : t('quoteSubmit'))}
        </button>
      </div>
      </form>
      {q?.status === 'WYCENIONA' && (
        <p className="muted txt-xs">
          {t('quoteSubmitted')}: {money(q)} · {formatDateTime(q.submitted_at)}
        </p>
      )}
    </div>
  )
}

// Anulowanie zlecenia z obowiązkowym powodem (wiersz 20) — działa też na zleceniu ZLECONE.
export function CancelBar({ job, onAction }: { job: TransportJob; onAction: OnAction }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  if (!open) {
    return (
      <div className="actions">
        <button className="btn secondary" onClick={() => setOpen(true)}>{t('quoteCancel')}</button>
      </div>
    )
  }
  return (
    <div className="panel quote-form quote-subpanel">
      <label>{t('quoteCancelReason')} *
        <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} />
      </label>
      <div className="actions">
        <button className="btn secondary" disabled={!reason.trim()} onClick={() =>
          onAction(() => api.post<TransportJob>(`/api/transport-jobs/${job.id}/cancel`, { reason }))}>
          {t('quoteCancel')}
        </button>
        <button className="btn small" onClick={() => { setOpen(false); setReason('') }}>
          {t('cancel')}
        </button>
      </div>
    </div>
  )
}
