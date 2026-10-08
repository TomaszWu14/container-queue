import { Fragment, FormEvent, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { LangContext, localeFor, useT } from '../i18n'
import type { Container, CustomsStatus, Named } from '../types'
import { CUSTOMS_CLEARED, CUSTOMS_STATUSES } from '../types'
import { LoadError, Skeleton, useToast } from '../feedback'
import { BackwardStatusConfirm, Modal } from '../components'
import { formatDate } from '../dates'


function AssignModal({ onSaved, onClose }: { onSaved: () => void; onClose: () => void }) {
  const t = useT()
  const { showToast } = useToast()
  const [containers, setContainers] = useState<Container[]>([])
  const [agencies, setAgencies] = useState<Named[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [form, setForm] = useState({ container_id: '', customs_agency_id: '', customs_note: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<Container[]>('/api/containers?completed=false&limit=2000')
      .then(setContainers).catch(() => {})
    api.get<Named[]>('/api/customs/agencies').then(setAgencies).catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return containers
    return containers.filter(c =>
      c.container_no.toLowerCase().includes(needle)
      || (c.supplier_name ?? '').toLowerCase().includes(needle)
      || (c.order_number ?? '').toLowerCase().includes(needle))
  }, [containers, query])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post(`/api/customs/containers/${Number(form.container_id)}/assign`, {
        customs_agency_id: Number(form.customs_agency_id),
        customs_note: form.customs_note,
      })
      showToast(t('toastAssigned'))
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={t('customsAssign')} onClose={onClose} busy={busy}>
        <form onSubmit={submit} className="form-grid">
          <label className="wide">{t('search')}
            <input value={query} onChange={e => setQuery(e.target.value)}
                   placeholder={t('containerNo')} />
          </label>
          <label className="wide">{t('containerNo')}
            <select required value={form.container_id}
                    onChange={e => setForm(f => ({ ...f, container_id: e.target.value }))}>
              <option value="">—</option>
              {filtered.map(c => (
                <option key={c.id} value={c.id}>
                  {c.container_no} · {c.supplier_name ?? ''} {c.order_number ? `· PO ${c.order_number}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">{t('customsAgency')}
            <select required value={form.customs_agency_id}
                    onChange={e => setForm(f => ({ ...f, customs_agency_id: e.target.value }))}>
              <option value="">—</option>
              {agencies.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label className="wide">{t('notes')}
            <textarea rows={2} value={form.customs_note}
                      onChange={e => setForm(f => ({ ...f, customs_note: e.target.value }))} />
          </label>
        </form>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
          <button className="btn" onClick={submit}
                  disabled={!form.container_id || !form.customs_agency_id || busy}>{t('customsAssign')}</button>
        </div>
    </Modal>
  )
}

// termin/SLA sprawy wyprowadzony ze statusu odprawy + przydziału agencji (dane, które już mamy)
function term(c: Container, t: (k: string) => string): { text: string; color: string } {
  if (c.customs_status === 'REWIZJA') return { text: t('csTermReview'), color: 'var(--danger)' }
  if (CUSTOMS_CLEARED.has(c.customs_status)) return { text: t('csTermClosed'), color: '#2f7d54' }
  if (!(c.customs_agency_name || c.customs_agency_id)) return { text: t('csTermWaiting'), color: 'var(--muted)' }
  return { text: t('csTermProgress'), color: 'var(--muted)' }
}

export default function CustomsPage() {
  const t = useT()
  const { lang } = useContext(LangContext)
  const user = useUser()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [rows, setRows] = useState<Container[]>([])
  const [caseStatuses, setCaseStatuses] = useState<Named[]>([])
  const [tab, setTab] = useState<'' | CustomsStatus>('')
  const [query, setQuery] = useState('')
  const [agency, setAgency] = useState('')
  const [grouping, setGrouping] = useState<'eta' | 'agency'>('eta')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAssign, setShowAssign] = useState(false)
  const [incompleteOnly, setIncompleteOnly] = useState(false)
  const [archive, setArchive] = useState(false)   // zrealizowane — osobno, z limitem (PERF-003)
  const [busy, setBusy] = useState(false)

  const isCustoms = user?.role === 'customs'
  const canManage = user?.role === 'admin' || user?.role === 'logistics'

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api.get<Container[]>(`/api/customs/board${archive ? '?archive=true' : ''}`)
      .then(setRows)
      .catch(err => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [archive])
  useEffect(() => load(), [load])
  useEffect(() => {
    api.get<Named[]>('/api/customs/case-statuses?active_only=true')
      .then(setCaseStatuses).catch(err => setError(errorMessage(err)))
  }, [])

  const counts = useMemo(() => {
    const map: Partial<Record<CustomsStatus, number>> = {}
    for (const r of rows) map[r.customs_status] = (map[r.customs_status] ?? 0) + 1
    return map
  }, [rows])

  const agencies = useMemo(() => {
    const set = new Set<string>()
    for (const r of rows) { const a = r.customs_agency_name || r.customs_agency; if (a) set.add(a) }
    return [...set].sort()
  }, [rows])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return rows.filter(r => {
      if (tab && r.customs_status !== tab) return false
      if (agency && (r.customs_agency_name || r.customs_agency) !== agency) return false
      if (incompleteOnly && (r.missing_documents?.length ?? 0) === 0) return false
      if (!needle) return true
      return (`${r.container_no} ${r.order_number ?? ''} ${r.company_name ?? ''} `
        + `${r.customs_agency_name ?? ''} ${r.customs_agent_name ?? ''}`)
        .toLowerCase().includes(needle)
    })
  }, [rows, tab, agency, incompleteOnly, query])

  const groups = useMemo(() => {
    const keys: string[] = []
    const byKey: Record<string, Container[]> = {}
    for (const r of visible) {
      const k = grouping === 'eta'
        ? (r.eta || '')
        : (r.customs_agency_name || r.customs_agency || t('csNoAgencyGroup'))
      if (!byKey[k]) { byKey[k] = []; keys.push(k) }
      byKey[k].push(r)
    }
    if (grouping === 'eta') keys.sort()   // ETA rosnąco; '' (brak) na końcu po sort? pusty na początku
    return keys.map(k => {
      const list = byKey[k]
      let title: string, note: string
      if (grouping === 'eta') {
        const weekday = k
          ? new Date(`${k}T00:00:00`).toLocaleDateString(localeFor(lang), { weekday: 'long' })
          : t('noEta')
        title = k ? `${weekday} · ${formatDate(k)}` : t('noEta')
        const pending = list.filter(r => !CUSTOMS_CLEARED.has(r.customs_status)).length
        // B34: odmiana (1 sprawa / 2 sprawy / 5 spraw) — klucze jawnie, bez dynamicznych nazw
        const form = new Intl.PluralRules(lang).select(pending)
        const label = form === 'one' ? t('csInProgress_one') : form === 'few' ? t('csInProgress_few') : t('csInProgress')
        note = pending ? `${pending} ${label}` : t('csAllCleared')
      } else {
        title = k
        const noAgent = list.filter(r => !r.customs_agent_name).length
        note = noAgent ? `${noAgent} ${t('csWithoutAgent')}` : t('csAgentsAssigned')
      }
      return { key: k, title, note, count: list.length, rows: list }
    })
  }, [visible, grouping, lang, t])

  const colCount = isCustoms ? 7 : 8

  const [backward, setBackward] = useState<{ container: Container; customs_status: CustomsStatus; note: string } | null>(null)

  const doChangeStatus = async (container: Container, customs_status: CustomsStatus, note?: string) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const saved = await api.post<Container>(`/api/customs/containers/${container.id}/status`,
        { customs_status, ...(note ? { customs_note: note } : {}) })
      showToast(saved?.docs_warning || t('toastStatusChanged'), saved?.docs_warning ? 'error' : undefined)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const changeStatus = (container: Container, customs_status: CustomsStatus) => {
    if (CUSTOMS_CLEARED.has(container.customs_status) && !CUSTOMS_CLEARED.has(customs_status)) {
      setBackward({ container, customs_status, note: '' })
      return
    }
    doChangeStatus(container, customs_status)
  }

  const changeCaseStatus = async (container: Container, raw: string) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.post(`/api/customs/containers/${container.id}/case-status`,
        { customs_case_status_id: raw ? Number(raw) : null })
      showToast(t('toastStatusChanged'))
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const resultLabel = t('csResult')
    .replace('{n}', String(visible.length)).replace('{total}', String(rows.length))

  return (
    <main className="page">
      <div className="cs-head">
        <div>
          <div className="cs-eyebrow">{t('customsEyebrow')}</div>
          <h1 className="cs-title">{t('customsModule')}</h1>
          <div className="cs-sub">
            {isCustoms ? t('customsIntroAgency') : t('customsIntroLogistics')}
          </div>
        </div>
        {canManage && <button className="btn" onClick={() => setShowAssign(true)}>{t('customsAssign')}</button>}
      </div>

      <div className="filters" style={{ alignItems: 'center' }}>
        <input type="text" value={query} onChange={e => setQuery(e.target.value)}
               aria-label={`${t('containerNo')}, PO, ${t('customsAgent').toLowerCase()}`} placeholder={`${t('containerNo')}, PO, ${t('customsAgent').toLowerCase()}`} />
        <select aria-label={t('customsAgency')} value={agency} onChange={e => setAgency(e.target.value)} style={{ minWidth: 180 }}>
          <option value="">{t('csAllAgencies')}</option>
          {agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <div className="seg">
          <button className={grouping === 'eta' ? 'active' : ''} onClick={() => setGrouping('eta')}>{t('csGroupEta')}</button>
          <button className={grouping === 'agency' ? 'active' : ''} onClick={() => setGrouping('agency')}>{t('csGroupAgency')}</button>
        </div>
        <div className="spacer" />
        <span className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>{resultLabel}</span>
      </div>

      <div className="tabs">
        <button className={tab === '' ? 'active' : ''} onClick={() => setTab('')}>
          {t('allOrders')} ({rows.length})
        </button>
        {CUSTOMS_STATUSES.map(s => (
          <button key={s} className={tab === s ? 'active' : ''} onClick={() => setTab(s)}>
            {t(`cs_${s}`)} ({counts[s] ?? 0})
          </button>
        ))}
        <button className={incompleteOnly ? 'active' : ''}
                onClick={() => setIncompleteOnly(v => !v)}>
          {t('onlyIncomplete')} ({rows.filter(r => (r.missing_documents?.length ?? 0) > 0).length})
        </button>
        <button className={archive ? 'active' : ''} aria-pressed={archive}
                title={t('customsArchiveHint')} onClick={() => setArchive(v => !v)}>
          {t('customsArchive')}
        </button>
      </div>

      {loading && rows.length === 0 && <Skeleton rows={4} />}
      {!loading && error && rows.length === 0 && <LoadError message={error} onRetry={load} />}
      {error && rows.length > 0 && <p className="error">{error}</p>}
      {!loading && !error && visible.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('customsEmpty')}</p>}

      {visible.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="grid cs-board">
            <thead>
              <tr>
                <th>{t('containerNo')}</th>
                {!isCustoms && <th>{t('company')}</th>}
                <th>{t('eta')}</th>
                <th>{t('customsAgency')}</th>
                <th>{t('customsAgent')}</th>
                <th>{t('customs')}</th>
                <th>{t('caseStatus')}</th>
                <th>{t('csTerm')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(g => (
                <Fragment key={`g-${g.key}`}>
                  <tr className="cs-group">
                    <td colSpan={colCount}>
                      <div className="cs-group-banner">
                        <span className="cs-group-title">{g.title}</span>
                        <span className="cs-group-note">{g.note}</span>
                        <span className="cs-group-count">{g.count}</span>
                      </div>
                    </td>
                  </tr>
                  {g.rows.map(c => {
                    const tm = term(c, t)
                    return (
                      <tr key={c.id} className={`cs-row cs-row-${c.customs_status}`}>
                        <td className="mono">
                          <a className="order-link" onClick={() => navigate(`/kontenery/${c.id}`)}>
                            {c.container_no}
                          </a>
                          {c.order_number && <div className="cs-po">PO {c.order_number}</div>}
                          {(c.missing_documents?.length ?? 0) > 0 && (
                            <span className="badge cs-ZLECONA" style={{ marginLeft: 6 }}
                                  title={c.missing_documents!.join(', ')}>
                              {t('missingDocs')}
                            </span>
                          )}
                        </td>
                        {!isCustoms && <td>{c.company_name}</td>}
                        <td>{c.eta ? formatDate(c.eta) : '—'}</td>
                        <td style={{ color: (c.customs_agency_name || c.customs_agency) ? 'var(--text)' : 'var(--muted)' }}>
                          {c.customs_agency_name || c.customs_agency || t('csNoAgencyGroup')}
                        </td>
                        <td>
                          <div style={{ color: c.customs_agent_name ? 'var(--text)' : 'var(--muted)' }}>
                            {c.customs_agent_name || t('csNoAgentLabel')}
                          </div>
                          {c.customs_agent_phone && (
                            <div className="cs-agent-meta">{c.customs_agent_phone}</div>
                          )}
                        </td>
                        <td>
                          <select aria-label={t('status')} value={c.customs_status} disabled={busy}
                                  onChange={e => changeStatus(c, e.target.value as CustomsStatus)}>
                            {CUSTOMS_STATUSES.map(s => <option key={s} value={s}>{t(`cs_${s}`)}</option>)}
                          </select>
                        </td>
                        <td>
                          {c.customs_agency_id ? (
                            <select aria-label={t('caseStatus')} value={c.customs_case_status_id ?? ''} disabled={busy}
                                    onChange={e => changeCaseStatus(c, e.target.value)}>
                              <option value="">—</option>
                              {caseStatuses.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                              {c.customs_case_status_id
                                && !caseStatuses.some(s => s.id === c.customs_case_status_id)
                                && <option value={c.customs_case_status_id}>{c.customs_case_status_name}</option>}
                            </select>
                          ) : '—'}
                        </td>
                        <td>
                          <div className="cs-term-cell">
                            <span style={{ fontSize: 12, color: tm.color }}>{tm.text}</span>
                            <button className="btn small secondary" onClick={() => navigate(`/kontenery/${c.id}`)}>
                              {t('customsManage')}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAssign && <AssignModal onSaved={load} onClose={() => setShowAssign(false)} />}
      {backward && (
        <BackwardStatusConfirm
          fromLabel={t(`cs_${backward.container.customs_status}`)} toLabel={t(`cs_${backward.customs_status}`)}
          note={backward.note} onNoteChange={note => setBackward(b => b && { ...b, note })}
          onConfirm={() => { doChangeStatus(backward.container, backward.customs_status, backward.note); setBackward(null) }}
          onCancel={() => setBackward(null)}
        />
      )}
    </main>
  )
}
