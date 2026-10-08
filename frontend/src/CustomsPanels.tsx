import { FormEvent, useEffect, useState } from 'react'
import { useUser } from './App'
import { api, errorMessage } from './api'
import { useT } from './i18n'
import { BackwardStatusConfirm } from './components'
import { HelpTip } from './HelpTip'
import type { Container, CustomsStatus, Named } from './types'
import { CUSTOMS_CLEARED, CUSTOMS_STATUSES } from './types'
import { useConfirm } from './ConfirmDialog'
import { Field } from './Field'
import { useToast } from './feedback'

// Panel odprawy celnej na karcie kontenera (agencja: obieg strukturalny). Spedytor nie ma panelu —
// odprawa to wyłącznie agencja celna (decyzja 2026-09-28).
// Publiczny import zostaje przez './collaboration' (re-eksport).

// Strukturalny obieg agencji celnej (nowy): logistyka zleca agencję, agencja wyznacza
// agenta i aktualizuje status — obie strony powiadamiane. Panel dostosowuje się do roli.
export function CustomsAgencyPanel({ container, onSaved }: {
  container: Container
  onSaved: () => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const user = useUser()
  const isCustoms = user?.role === 'customs'
  const canAssign = user?.role === 'admin' || user?.role === 'logistics'

  const [agencies, setAgencies] = useState<Named[]>([])
  const [agencyId, setAgencyId] = useState(container.customs_agency_id ? String(container.customs_agency_id) : '')
  const [status, setStatus] = useState<CustomsStatus>(container.customs_status)
  const [note, setNote] = useState('')              // komentarz do zmiany statusu
  const [assignNote, setAssignNote] = useState('')  // uwaga do zlecenia agencji (osobne pole, C33)
  const [agent, setAgent] = useState({
    customs_agent_name: container.customs_agent_name,
    customs_agent_phone: container.customs_agent_phone,
    customs_agent_email: container.customs_agent_email,
  })
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [confirmBackward, setConfirmBackward] = useState(false)

  useEffect(() => {
    if (canAssign) api.get<Named[]>('/api/customs/agencies').then(setAgencies).catch(() => {})
  }, [canAssign])
  useEffect(() => {
    setAgencyId(container.customs_agency_id ? String(container.customs_agency_id) : '')
    setStatus(container.customs_status)
    setAgent({
      customs_agent_name: container.customs_agent_name,
      customs_agent_phone: container.customs_agent_phone,
      customs_agent_email: container.customs_agent_email,
    })
    setNote('')
    setAssignNote('')
    setSaved('')
  }, [container.id])

  const flash = (key: string) => { setSaved(key); setTimeout(() => setSaved(''), 2500) }

  const [busy, setBusy] = useState(false)
  const { showToast } = useToast()
  const call = async (path: string, body: unknown, okKey: string) => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      const res = await api.post<Partial<Container>>(path, body)
      if (res?.docs_warning) showToast(res.docs_warning, 'error')   // braki dokumentów: nie blokada
      flash(okKey)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const assign = (e: FormEvent) => {
    e.preventDefault()
    if (!agencyId) return
    call(`/api/customs/containers/${container.id}/assign`,
      { customs_agency_id: Number(agencyId), customs_note: assignNote }, 'saved')
  }
  const unassign = async () => {
    if (!(await confirm(t('confirmUnassignAgency')))) return
    call(`/api/customs/containers/${container.id}/unassign`, {}, 'saved')
  }
  const setAgentFn = (e: FormEvent) => {
    e.preventDefault()
    call(`/api/customs/containers/${container.id}/agent`, agent, 'saved')
  }
  const doChangeStatus = () => call(`/api/customs/containers/${container.id}/status`,
    { customs_status: status, customs_note: note }, 'saved')

  const changeStatus = (e: FormEvent) => {
    e.preventDefault()
    if (CUSTOMS_CLEARED.has(container.customs_status) && !CUSTOMS_CLEARED.has(status)) {
      setConfirmBackward(true)
      return
    }
    doChangeStatus()
  }

  const field = (label: string, value: React.ReactNode) => (
    <span style={{ fontSize: 14 }}>
      <b style={{ color: 'var(--muted)', fontSize: 12, display: 'block',
                  textTransform: 'uppercase' }}>{label}</b>
      {value || '—'}
    </span>
  )

  return (
    <div className="panel">
      <h3>{t('customsAgencyPanel')} <HelpTip label={`${t('helpLabel')}: ${t('customsAgencyPanel')}`} text={t('helpCustomsAgency')} /></h3>
      <div className="row" style={{ gap: 24, marginBottom: 12 }}>
        {field(t('customsAgency'), container.customs_agency_name || container.customs_agency)}
        {field(t('customsAgent'), container.customs_agent_name)}
        {field(t('customsAgentPhone'), container.customs_agent_phone)}
        {field(t('customs'), <CustomsBadgeInline status={container.customs_status} />)}
      </div>

      {canAssign && (
        <form className="field-row" onSubmit={assign}>
          <Field label={t('customsAgency')}>
            <select value={agencyId} onChange={e => setAgencyId(e.target.value)}>
              <option value="">— {t('customsAgency')} —</option>
              {agencies.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </Field>
          <Field label={t('flAssignNote')} className="wide">
            <input value={assignNote} onChange={e => setAssignNote(e.target.value)} />
          </Field>
          <button className="btn secondary" disabled={!agencyId || busy}>
            {container.customs_agency_id ? t('customsReassign') : t('customsAssign')}
          </button>
          {container.customs_agency_id && (
            <button type="button" className="btn small secondary" disabled={busy} onClick={unassign}>
              {t('customsUnassign')}
            </button>
          )}
        </form>
      )}

      {isCustoms && (
        <form className="field-row" onSubmit={setAgentFn}>
          <Field label={t('customsAgent')}>
            <input value={agent.customs_agent_name}
                   onChange={e => setAgent(a => ({ ...a, customs_agent_name: e.target.value }))} />
          </Field>
          <Field label={t('customsAgentPhone')}>
            <input value={agent.customs_agent_phone} inputMode="tel"
                   onChange={e => setAgent(a => ({ ...a, customs_agent_phone: e.target.value }))} />
          </Field>
          <Field label={t('customsAgentEmail')}>
            <input type="email" value={agent.customs_agent_email}
                   onChange={e => setAgent(a => ({ ...a, customs_agent_email: e.target.value }))} />
          </Field>
          <button className="btn secondary" disabled={busy}>{t('customsSetAgent')}</button>
        </form>
      )}

      {(isCustoms || canAssign) && (
        <form className="field-row" onSubmit={changeStatus}>
          <Field label={t('flCustomsStatus')}>
            <select value={status} onChange={e => setStatus(e.target.value as CustomsStatus)}>
              {CUSTOMS_STATUSES.map(s => <option key={s} value={s}>{t(`cs_${s}`)}</option>)}
            </select>
          </Field>
          <Field label={t('flStatusNote')} className="wide">
            <input value={note} onChange={e => setNote(e.target.value)} />
          </Field>
          <button className="btn secondary" disabled={busy}>{t('flCustomsStatusBtn')}</button>
        </form>
      )}
      {confirmBackward && (
        <BackwardStatusConfirm
          fromLabel={t(`cs_${container.customs_status}`)} toLabel={t(`cs_${status}`)}
          note={note} onNoteChange={setNote}
          onConfirm={() => { setConfirmBackward(false); doChangeStatus() }}
          onCancel={() => setConfirmBackward(false)}
        />
      )}

      {saved && <span className="field-row-ok">✓ {t('saved')}</span>}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

function CustomsBadgeInline({ status }: { status: CustomsStatus }) {
  const t = useT()
  return <span className={`badge cs-${status}`}>{t(`cs_${status}`)}</span>
}
