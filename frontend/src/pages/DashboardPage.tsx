import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, downloadCsv, errorMessage, toCsv } from '../api'
import { LoadError, Skeleton } from '../feedback'
import { DocsGapsCard } from '../DocumentsW5'
import NewsFeed from './news/NewsFeed'
import { useUser } from '../App'
import { LangContext, localeFor, useT } from '../i18n'
import { formatDate, formatDayLong, todayISO } from '../dates'

interface DigestEntry {
  container_id: number
  container_no: string
  field: string
  old: string | null
  new: string | null
}

interface Brief {
  id: number
  container_no: string
  supplier_name: string | null
  company_name: string | null
  port_name?: string | null
  notify_date: string | null
  eta: string | null
  delay_days?: number
  status: string
  deadline?: string
}

interface Signal {
  container_id: number; container_no: string; company_name: string | null
  supplier_name: string | null; port_name: string | null
  eta: string | null; notify_date: string | null; status: string
  type: 'delayed'|'demurrage'|'stuck'|'missing_avizo'|'missing_eta'|'missing_docs'
      |'eta_shift'|'po_unconfirmed'|'docs_pre_eta'|'special_care'
  score: number; urgency_days: number; cost_eur: number | null
  action_kind: 'container'|'avizo-form'|'documents'
  summary_key: string; summary_params: Record<string, string | number>
}

interface DashboardData {
  today: number
  tomorrow: number
  in_transit: number
  at_port: number
  customs_in_progress: number | null   // null = rola nie widzi odprawy (spedytor)
  delayed: number
  delayed_list: Brief[]
  today_list: Brief[]
  demurrage_list: Brief[]
  action_feed: Signal[]
}


// Priorytet wg ryzyka (Faza 1: przybliżenie po dniach opóźnienia; pełny wzór
// „opóźnienie × pozostałe demurrage × wartość PO" wymaga danych z Fazy 3).
function priority(score: number): { level: 1 | 2 | 3 } {
  if (score >= 60) return { level: 1 }
  if (score >= 25) return { level: 2 }
  return { level: 3 }
}

// kafelek KPI z akcentową obwódką po lewej (wariant 1a „Wieża kontrolna")
function CtlKpi({ label, value, sub, accent }: {
  label: string; value: number; sub?: string; accent?: 'danger' | 'amber' | 'sky' | 'plain'
}) {
  return (
    <div className={`ctl-kpi ${accent ?? 'plain'}`}>
      <div className="ctl-kpi-label">{label}</div>
      <div className="ctl-kpi-value">{value}</div>
      {sub && <div className="ctl-kpi-sub">{sub}</div>}
    </div>
  )
}

export default function DashboardPage() {
  const t = useT()
  // summary_key + summary_params → tekst przetłumaczony (FIX 1: backend nie wysyła gotowej prozy PL)
  const sigText = (r: Signal) => Object.entries(r.summary_params).reduce(
    (s, [k, v]) => s.replace(`{${k}}`, String(v)), t(r.summary_key))
  // „CO” = typ ryzyka + szczegół (bez powtarzania typu); demurrage: kwota tylko w „KOSZT” (A3)
  const detail = (r: Signal) => (r.type === 'demurrage' ? '' : sigText(r))
  const csvWhat = (r: Signal) => [t(`sig_${r.type}`), detail(r)].filter(Boolean).join(': ')
  const { lang } = useContext(LangContext)
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [digest, setDigest] = useState<
    { created: DigestEntry[]; status: DigestEntry[]; eta: DigestEntry[] } | null>(null)
  const [error, setError] = useState('')
  const [company, setCompany] = useState('')   // filtr spółki listy działań (klient)

  const load = useCallback(() => {
    setError('')
    // kubełki dziś/jutro wg zegara usera, nie UTC (0:00–2:00 w PL rozjeżdża się z kolejką)
    api.get<DashboardData>(`/api/stats/dashboard?today=${todayISO()}`)
      .then(d => { setData(d); setError('') })
      .catch(err => setError(errorMessage(err)))
    api.get<{ created: DigestEntry[]; status: DigestEntry[]; eta: DigestEntry[] }>('/api/changes/digest')
      .then(setDigest).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  // lista działań = action_feed (już posortowany wg score przez backend)
  const actions = useMemo(() =>
    (data?.action_feed ?? []).filter(r => !company || r.company_name === company),
    [data, company])

  const companies = useMemo(
    () => [...new Set((data?.action_feed ?? []).map(r => r.company_name).filter(Boolean))] as string[],
    [data])

  // deep-link per typ akcji: karta kontenera czyta ?akcja i przewija do panelu
  // (documents → załączniki, avizo-form → panel awizo/kierowcy); container = bez kotwicy
  const goTo = (r: Signal) => navigate(
    r.action_kind === 'container'
      ? `/kontenery/${r.container_id}`
      : `/kontenery/${r.container_id}?akcja=${r.action_kind}`)

  // C6: błąd ładowania nie zjada nagłówka — użytkownik wie, która strona nie wczytała danych
  const head = (
    <div className="dash-head"><div>
      <div className="dash-eyebrow">{t('dashEyebrow')}</div>
      <h1 className="dash-title">{t('ctlTitle')}</h1>
    </div></div>
  )
  if (error && !data) return (
    <main className="page dash">{head}<LoadError message={error} onRetry={load} /></main>
  )
  if (!data) return <main className="page"><Skeleton rows={6} /></main>

  const todayLabel = formatDayLong(todayISO(), localeFor(lang))

  const doExport = () => downloadCsv('co-dzis.csv', toCsv([
    [t('containerNo'), t('ctlWhat'), t('company'), t('port'), t('eta'), t('ctlCostCol'), t('status')],
    actions.map(r => [r.container_no, csvWhat(r),
      r.company_name ?? '', r.port_name ?? '', r.eta ? formatDate(r.eta) : '',
      r.cost_eur ? `€${Math.round(r.cost_eur)}` : '', t(`st_${r.status}`)])]))

  return (
    <main className="page dash">
      <div className="dash-head">
        <div>
          <div className="dash-eyebrow">{t('dashEyebrow')}</div>
          <h1 className="dash-title">{t('ctlTitle')}</h1>
          <div className="dash-sub">{t('dashStateToday')} — {todayLabel}</div>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <select value={company} onChange={e => setCompany(e.target.value)}
                  aria-label={t('company')}>
            <option value="">{t('ctlAllCompanies')}</option>
            {companies.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn secondary small" disabled={!actions.length}
                  onClick={doExport}>{t('exportCsv')}</button>
        </div>
      </div>

      <div className="ctl-kpis">
        <CtlKpi label={t('ctlDecisions')} value={actions.length}
                sub={t('ctlItemsUnit')} accent="danger" />
        <CtlKpi label={t('ctlDemurrage3')} value={data.demurrage_list.length}
                sub={t('dashDemurrageList')} accent="amber" />
        <CtlKpi label={t('dashToday')} value={data.today} accent="sky" />
        <CtlKpi label={t('dashTomorrow')} value={data.tomorrow} accent="sky" />
        {data.customs_in_progress !== null && (
          <CtlKpi label={t('dashCustoms')} value={data.customs_in_progress} accent="amber" />)}
        <CtlKpi label={t('ctlQueueTotal')} value={data.at_port + data.in_transit}
                sub={`${data.at_port} ${t('ctlInPort')} · ${data.in_transit} ${t('ctlInTransit')}`} />
      </div>

      <section className="panel ctl-actions">
        <div className="dash-card-head">
          <span className="dash-card-title">{t('ctlActions')}</span>
          <span className="count-chip">{actions.length}</span>
          <div className="spacer" />
          <Link to="/kolejka" className="link-like no-underline">{t('dashOpenQueue')} →</Link>
        </div>
        {actions.length === 0 ? (
          <p className="muted" style={{ margin: '8px 2px' }}>{t('dashAllClear')}</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="grid">
              <thead>
                <tr>
                  <th>{t('dashPriorities')}</th><th>{t('containerNo')}</th><th>{t('ctlWhat')}</th>
                  {/* A7: ≤ 1024 px bez Spółki/Portu — „Szczegóły” mieści się bez przewijania w bok */}
                  <th className="hide-md">{t('company')}</th><th className="hide-md">{t('port')}</th><th>{t('eta')}</th>
                  <th>{t('ctlCostCol')}</th><th>{t('status')}</th><th>{t('ctlAction')}</th>
                </tr>
              </thead>
              <tbody>
                {actions.map(r => {
                  const p = priority(r.score)
                  return (
                    <tr key={`${r.container_id}-${r.type}`} className="clickable"
                        onClick={() => goTo(r)}>
                      <td><span className={`prio prio-${p.level}`}>P{p.level}</span></td>
                      <td className="mono">{r.container_no}</td>
                      <td>{t(`sig_${r.type}`)}{detail(r) && <>: <span>{detail(r)}</span></>}</td>
                      <td className="hide-md">{r.company_name}</td>
                      <td className="hide-md">{r.port_name || '—'}</td>
                      <td>{formatDate(r.eta)}</td>
                      <td>{r.cost_eur ? `€${Math.round(r.cost_eur)}` : '—'}</td>
                      <td><span className={`badge st-${r.status}`}>{t(`st_${r.status}`)}</span></td>
                      <td>
                        <button className="btn small secondary"
                                onClick={e => { e.stopPropagation(); goTo(r) }}>
                          {t('details')}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              {t('ctlPriorityHint')}
            </div>
          </div>
        )}
      </section>

      {/* Aktualności: powiadomienia jak news — lista + panel czytania (spec 2026-10-01) */}
      <NewsFeed />

      {/* #47: decyzje cross-module — faktury transportowe czekające na akceptację (admin) */}
      <FreightApprovalsCard />

      {/* W5 #32: braki dokumentów przed ETA (admin/logistics — bramka roli w karcie) */}
      <DocsGapsCard />

      {digest && (digest.created.length + digest.status.length + digest.eta.length) > 0 && (
        <div className="panel" style={{ marginTop: 12 }}>
          <div className="mini-title">{t('digestTitle')}</div>
          {digest.created.length > 0 && (
            <div className="digest-row">
              <b>{digest.created.length}</b> {t('digestCreated')}
              <span className="muted"> — {digest.created.slice(0, 3).map(e => e.container_no).join(', ')}{digest.created.length > 3 ? '…' : ''}</span>
            </div>
          )}
          {digest.status.length > 0 && (
            <div className="digest-row">
              <b>{digest.status.length}</b> {t('digestStatus')}
              <span className="muted"> — {digest.status.slice(0, 3).map(e => `${e.container_no}→${e.new}`).join(', ')}{digest.status.length > 3 ? '…' : ''}</span>
            </div>
          )}
          {digest.eta.length > 0 && (
            <div className="digest-row">
              <b>{digest.eta.length}</b> {t('digestEta')}
              <span className="muted"> — {digest.eta.slice(0, 3).map(e => `${e.container_no}: ${e.old ?? '—'}→${e.new ?? '—'}`).join(', ')}{digest.eta.length > 3 ? '…' : ''}</span>
            </div>
          )}
        </div>
      )}
    </main>
  )
}

type PendingFreight = { id: number; bl_number: string; invoice_number: string
  amount: number | null; currency: string; status: string }

function FreightApprovalsCard() {
  const t = useT()
  const user = useUser()
  const [items, setItems] = useState<PendingFreight[]>([])
  const isAdmin = user?.role === 'admin'
  useEffect(() => {
    if (!isAdmin) return
    api.get<PendingFreight[]>('/api/freight-invoices')
      .then(r => setItems(Array.isArray(r) ? r.filter(i => i.status === 'DO_AKCEPTACJI') : []))
      .catch(() => {})
  }, [isAdmin])
  if (!isAdmin || items.length === 0) return null
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="mini-title">{t('inboxApprovals')} ({items.length})</div>
      {items.slice(0, 10).map(i => (
        <div key={i.id} className="row" style={{ justifyContent: 'space-between' }}>
          <Link to="/spedycja" className="mono">{i.bl_number} · {i.invoice_number}</Link>
          <span>{i.amount != null ? `${i.amount} ${i.currency}` : '—'}</span>
        </div>
      ))}
    </div>
  )
}
