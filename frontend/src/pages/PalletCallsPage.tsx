import { ArrowUpIcon, Package, TriangleAlertIcon, InfoIcon } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useUser } from '../App'
import { api, downloadFile, errorMessage } from '../api'
import { useT } from '../i18n'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { formatDate, formatDateTime, formatNum } from '../dates'
import HuInventorySection from './palletcalls/HuInventorySection'
import PazSection from './palletcalls/PazSection'
import { useConfirm } from '../ConfirmDialog'

// #65: CSV inwentaryzacji HU — publiczny eksport zostaje pod starą ścieżką
export { huInventoryCsv } from './palletcalls/HuInventorySection'

type AnalysisRow = {
  produkt: string
  stan_mag_pal: number | null
  stan_dlt_pal: number | null
  dostawy_pal: number
  zlec_niepotw_pal: number
  zlec_potw_pal: number
  wywolane_pal: number
  projekcja_mag_pal: number | null
  dni_zapasu: number | null
  pilne: boolean
  sugestia_pal: number | null
  stan_mag_szt: number
  stan_dlt_szt: number
  zuzycie_szt_dzien: number
  cel_dni: number | null
  hu: { hu: string; ilosc: number }[]
}
type AnalysisPage = {
  items: AnalysisRow[]; total: number; fetched_at: string | null; discrepancies: unknown[]
  features: { hu?: boolean; daily_usage?: boolean }
}
type PalletCall = {
  id: number; number: string; status: string; needed_by: string | null
  notes: string; created_at: string; sent_at: string | null; lines: { produkt: string; ilosc_pal: number }[]
  trucks: { id: number; ordinal: number; capacity: number }[]
}

export const TRUCK_CAPACITY = 33
export const MAX_TRUCKS = 4
export const TOTAL_CAP = TRUCK_CAPACITY * MAX_TRUCKS

// sort: najkrótszy zapas w dniach u góry, brak danych na końcu
export function sortByDaysAsc(items: AnalysisRow[]): AnalysisRow[] {
  return [...items].sort((a, b) =>
    (a.dni_zapasu ?? Infinity) - (b.dni_zapasu ?? Infinity))
}

export type CallLine = {
  produkt: string; ilosc_pal: number; pallets?: number | null
  hu_numbers?: string; truck_no?: number | null
}

// licznik zajętości: miejsca paletowe (ceil ułamka) per auto + suma
export function truckLoads(lines: CallLine[]) {
  const perTruck: Record<number, number> = {}
  let total = 0
  for (const l of lines) {
    const places = Math.ceil(l.pallets ?? l.ilosc_pal)
    total += places
    if (l.truck_no) perTruck[l.truck_no] = (perTruck[l.truck_no] ?? 0) + places
  }
  const overTruck = Object.entries(perTruck)
    .filter(([, p]) => p > TRUCK_CAPACITY).map(([n]) => Number(n))
  return { perTruck, total, overTruck, overTotal: total > TOTAL_CAP }
}
type Company = { id: number; name: string; code: string }
type PbiStatus = { provider: string; configured: boolean; delegated: boolean; needs_connect: boolean }

const num = (v: number | null, d = 1) => formatNum(v, d)
const CALL_STATUSES = ['draft', 'sent', 'confirmed', 'przygotowane', 'wyslane_z_dlt', 'delivered', 'cancelled']

export default function PalletCallsPage() {
  const user = useUser()
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const isEditor = user?.role === 'admin' || user?.role === 'logistics'
  // magazyn DLT (konto warehouse) potwierdza przygotowanie i wysyłkę — bez linku z maila
  const canConfirmDlt = isEditor || user?.role === 'warehouse'
  const [page, setPage] = useState<AnalysisPage | null>(null)
  const [firstLoading, setFirstLoading] = useState(true)
  const [q, setQ] = useState('')
  const [urgentOnly, setUrgentOnly] = useState(false)
  const [belowTarget, setBelowTarget] = useState(false)
  const [qty, setQty] = useState<Record<string, string>>({})
  const [truck, setTruck] = useState<Record<string, string>>({})       // produkt -> auto 1..4
  const [hus, setHus] = useState<Record<string, string[]>>({})         // produkt -> wybrane HU
  const [calls, setCalls] = useState<PalletCall[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [companyId, setCompanyId] = useState<number | ''>('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [pbi, setPbi] = useState<PbiStatus | null>(null)
  // 503 z analizy = Power BI wyłączone i brak importu DLT — jeden baner, bez „spróbuj ponownie” (B19)
  const [pbiOff, setPbiOff] = useState(false)
  const [connectCode, setConnectCode] = useState('')
  const [neededBy, setNeededBy] = useState('')
  const [allowOverDlt, setAllowOverDlt] = useState(false)

  // ref-seq: przy szybkim pisaniu tylko odpowiedź na NAJNOWSZE zapytanie trafia do stanu
  const analysisSeq = useRef(0)
  const loadAnalysis = useCallback((refresh = false) => {
    const p = new URLSearchParams({ limit: '500' })
    if (q) p.set('q', q)
    if (urgentOnly) p.set('urgent_only', 'true')
    if (belowTarget) p.set('below_target', 'true')
    if (refresh) p.set('refresh', 'true')
    const my = ++analysisSeq.current
    api.get<AnalysisPage>(`/api/pallet-calls/analysis?${p}`)
      .then(r => { if (my === analysisSeq.current) { setPage(r); setError(''); setPbiOff(false) } })
      .catch(e => {
        if (my !== analysisSeq.current) return
        if ((e as { status?: number })?.status === 503) setPbiOff(true)
        else setError(errorMessage(e))
      })
      .finally(() => { if (my === analysisSeq.current) setFirstLoading(false) })
  }, [q, urgentOnly, belowTarget])

  const loadCalls = useCallback(() => {
    api.get<PalletCall[]>('/api/pallet-calls').then(setCalls).catch(() => {})
  }, [])

  const loadStatus = useCallback(() => {
    api.get<PbiStatus>('/api/pallet-calls/powerbi/status').then(setPbi).catch(() => {})
  }, [])

  const connect = async () => {
    setError(''); setConnectCode('')
    try {
      const r = await api.post<{ message: string }>('/api/pallet-calls/powerbi/connect', {})
      setConnectCode(r.message)
    } catch (e) { setError(errorMessage(e)) }
  }

  // debounce: nie strzelaj do API na każdy znak w szukajce produktu
  useEffect(() => {
    const t = setTimeout(() => loadAnalysis(), 250)
    return () => clearTimeout(t)
  }, [loadAnalysis])
  useEffect(() => { loadStatus() }, [loadStatus])
  useEffect(() => {
    loadCalls()
    if (user?.role === 'admin') {
      api.get<Company[]>('/api/companies').then(c => {
        setCompanies(c); if (c[0]) setCompanyId(c[0].id)
      }).catch(() => {})
    }
  }, [loadCalls, user?.role])

  const sorted = useMemo(() => sortByDaysAsc(page?.items ?? []), [page])
  const rowByProduct = useMemo(() => {
    const m: Record<string, AnalysisRow> = {}
    for (const r of page?.items ?? []) m[r.produkt] = r
    return m
  }, [page])

  const selected = useMemo<CallLine[]>(() => {
    const products = new Set([
      ...Object.keys(qty).filter(p => Number(qty[p]) > 0),
      ...Object.keys(hus).filter(p => (hus[p] ?? []).length > 0),
    ])
    const lines: CallLine[] = []
    for (const produkt of products) {
      const row = rowByProduct[produkt]
      const picked = hus[produkt] ?? []
      // paz odtworzony ze stanu DLT (szt/pal) — do ułamkowych palet z wybranych HU
      const paz = row && row.stan_dlt_pal ? row.stan_dlt_szt / row.stan_dlt_pal : null
      let pallets: number | null = null
      if (picked.length && row && paz) {
        const szt = row.hu.filter(h => picked.includes(h.hu))
          .reduce((s, h) => s + h.ilosc, 0)
        pallets = Math.round((szt / paz) * 1000) / 1000
      }
      const manual = Number(qty[produkt] || 0)
      const ilosc_pal = manual > 0 ? manual : (pallets ? Math.ceil(pallets) : 0)
      if (ilosc_pal <= 0) continue
      const t = Number(truck[produkt] || 0)
      lines.push({
        produkt, ilosc_pal, pallets,
        hu_numbers: picked.join(','), truck_no: t >= 1 && t <= MAX_TRUCKS ? t : null,
      })
    }
    return lines
  }, [qty, hus, truck, rowByProduct])

  const loads = useMemo(() => truckLoads(selected), [selected])

  const [busy, setBusy] = useState(false)
  const createCall = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError(''); setInfo('')
    if (!selected.length) { setError(t('pcNeedQty')); return }
    if (loads.overTotal) { setError(t('pcOver132').replace('{n}', String(loads.total))); return }
    if (loads.overTruck.length) {
      setError(t('pcOver33').replace('{n}', loads.overTruck.join(', '))); return
    }
    setBusy(true)
    try {
      const body: Record<string, unknown> = { lines: selected, allow_over_dlt: allowOverDlt }
      if (neededBy) body.needed_by = neededBy
      if (user?.role === 'admin') body.company_id = companyId || undefined
      const call = await api.post<PalletCall>('/api/pallet-calls', body)
      setInfo(t('pcCreated').replace('{n}', call.number))
      showToast(t('toastSaved'))
      setQty({}); setTruck({}); setHus({}); loadCalls()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const fillSuggestions = (onlyUrgent: boolean) => {
    const next: Record<string, string> = {}
    for (const r of page?.items ?? []) {
      if (r.sugestia_pal != null && r.sugestia_pal > 0 && (!onlyUrgent || r.pilne))
        next[r.produkt] = String(r.sugestia_pal)
    }
    setQty(next)
  }

  const act = async (id: number, action: 'send' | 'confirm' | 'prepared' | 'shipped' | 'deliver' | 'cancel') => {
    if (busy) return
    if (action === 'cancel' && !(await confirm(t('confirmCancelCall'), { danger: true }))) return
    setError(''); setInfo('')
    setBusy(true)
    try {
      await api.post(`/api/pallet-calls/${id}/${action}`, {})
      showToast(t('toastStatusChanged'))
      loadCalls()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const downloadXlsx = (c: PalletCall) =>
    downloadFile(`/api/pallet-calls/${c.id}/xlsx`, `wywolanie_${c.number}.xlsx`)
      .catch(e => setError(errorMessage(e)))

  const statusLabel = (s: string) => CALL_STATUSES.includes(s) ? t(`pcStatus_${s}`) : s

  return (
    <main className="page">
      <h1>{t('pcTitle')}</h1>
      {/* błąd ładowania analizy pokazuje LoadError niżej — tu tylko błędy akcji */}
      {error && page && <p className="error">{error}</p>}
      {pbiOff && (
        <div className="panel" role="status" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <InfoIcon size={18} aria-hidden /> {t('pcPbiOff')}
        </div>
      )}
      {info && <p className="info">{info}</p>}

      {pbi && !pbiOff && (
        <div className="pbi-status" style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', margin: '8px 0' }}>
          <span className="muted">Power BI: <b>{pbi.provider}</b>{' '}
            {pbi.configured ? `• ${t('pcConfigured')}` : `• ${t('pcNotConfigured')}`}
            {pbi.delegated ? ` • ${t('pcSessionActive')}` : ''}</span>
          {user?.role === 'admin' && pbi.needs_connect &&
            <button className="btn small" onClick={connect}>{t('pcConnect')}</button>}
        </div>
      )}
      {connectCode && (
        <pre className="info" style={{ whiteSpace: 'pre-wrap' }}>{connectCode}</pre>
      )}

      <div className="toolbar" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input aria-label={t('pcSearchProduct')} placeholder={t('pcSearchProduct')} value={q} onChange={e => setQ(e.target.value)} />
        <label><input type="checkbox" checked={urgentOnly}
          onChange={e => setUrgentOnly(e.target.checked)} /> {t('pcUrgentOnly')}</label>
        <label><input type="checkbox" checked={belowTarget}
          onChange={e => setBelowTarget(e.target.checked)} /> {t('pcBelowTarget')}</label>
        {user?.role === 'admin' && (
          <select aria-label={t('company')} value={companyId} onChange={e => setCompanyId(Number(e.target.value))}>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
        {/* UX-026: filtry z lewej, akcje z prawej */}
        <span style={{ flex: 1 }} />
        <button className="btn small secondary" onClick={() => loadAnalysis(true)}>{t('pcRefreshPbi')}</button>
        {isEditor && <button className="btn small secondary" onClick={() => fillSuggestions(false)}>{t('pcFillSuggestions')}</button>}
        {isEditor && <button className="btn small secondary" onClick={() => fillSuggestions(true)}>{t('pcOnlyUrgent')}</button>}
        {isEditor && <label>{t('pcDeadline')} <input type="date" value={neededBy}
          onChange={e => setNeededBy(e.target.value)} /></label>}
        {isEditor && <label title={t('pcOverDltHint')}>
          <input type="checkbox" checked={allowOverDlt}
            onChange={e => setAllowOverDlt(e.target.checked)} /> {t('pcOverDlt')}</label>}
        {isEditor && <button className="btn" disabled={busy} onClick={createCall}>
          {t('pcCreateCall')} ({selected.length})</button>}
        {isEditor && selected.length > 0 && (
          <span className={`muted${loads.overTotal ? ' error' : ''}`} data-testid="truck-loads">
            {[1, 2, 3, 4].filter(n => loads.perTruck[n]).map(n =>
              `${t('pcTruck')} ${n}: ${loads.perTruck[n]}/${TRUCK_CAPACITY}`).join(' • ')}
            {' '}∑ {loads.total}/{TOTAL_CAP}
          </span>
        )}
        {page?.fetched_at && <span className="muted">{t('pcDataAt')}: {formatDateTime(page.fetched_at)}</span>}
      </div>

      {firstLoading && !page && <Skeleton rows={4} />}
      {!firstLoading && !pbiOff && error && !page && <LoadError message={error} onRetry={() => loadAnalysis()} />}
      {page && (
      <div style={{ overflowX: 'auto' }}>
        <table className="grid" style={{ minWidth: 720 }}>
          <thead>
            <tr>
              <th>{t('pcProduct')}</th><th>{t('pcStockMag')}</th><th>{t('pcStockDlt')}</th>
              <th>{t('pcDeliveries')}</th><th>{t('pcUnconfirmed')}</th><th>{t('pcConfirmedOrders')}</th><th>{t('pcProjection')}</th>
              <th>{t('pcUsagePerDay')}</th><th>{t('pcDaysStock')} <ArrowUpIcon size={14} /></th><th>{t('pcTargetDays')}</th>
              <th>{t('pcUrgent')}</th><th>{t('pcSuggestion')}</th><th>{t('pcToCall')}</th><th>{t('pcTruck')}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => (
              <tr key={r.produkt} className={r.pilne ? 'row-urgent' : ''}>
                <td>{r.produkt}</td>
                <td title={`${formatNum(r.stan_mag_szt, 0)} szt`}>{num(r.stan_mag_pal)}</td>
                <td title={`${formatNum(r.stan_dlt_szt, 0)} szt`}>{num(r.stan_dlt_pal)}
                  {page.features?.hu && r.hu.length > 0 && isEditor && (
                    <details style={{ display: 'inline-block', marginLeft: 6 }}>
                      <summary style={{ cursor: 'pointer' }}>HU ({r.hu.length})</summary>
                      <div style={{ maxHeight: 160, overflowY: 'auto' }}>
                        {r.hu.map(h => (
                          <label key={h.hu} style={{ display: 'block', whiteSpace: 'nowrap' }}>
                            <input type="checkbox"
                              checked={(hus[r.produkt] ?? []).includes(h.hu)}
                              onChange={e => setHus(s => {
                                const cur = s[r.produkt] ?? []
                                return {
                                  ...s,
                                  [r.produkt]: e.target.checked
                                    ? [...cur, h.hu] : cur.filter(x => x !== h.hu),
                                }
                              })} /> {h.hu} ({formatNum(h.ilosc, 0)} szt)
                          </label>
                        ))}
                      </div>
                    </details>
                  )}
                </td>
                <td>{num(r.dostawy_pal)}</td>
                <td>{num(r.zlec_niepotw_pal)}</td>
                <td>{num(r.zlec_potw_pal)}</td>
                <td>{num(r.projekcja_mag_pal)}</td>
                <td>{formatNum(r.zuzycie_szt_dzien, 1)}</td>
                <td>{num(r.dni_zapasu)}</td>
                <td>{r.cel_dni ?? ''}</td>
                <td>{r.pilne && <TriangleAlertIcon size={14} role="img" aria-label={t('pcUrgent')} />}</td>
                <td>{r.sugestia_pal == null ? t('pcNoPaz') : r.sugestia_pal}</td>
                <td>
                  {isEditor && r.sugestia_pal != null && (
                    <input aria-label={t('pcToCall')} type="number" min={0} style={{ width: 70 }}
                      value={qty[r.produkt] ?? ''}
                      placeholder={String(r.sugestia_pal)}
                      onChange={e => setQty(s => ({ ...s, [r.produkt]: e.target.value }))} />
                  )}
                </td>
                <td>
                  {isEditor && (
                    <select aria-label={`${t('pcTruck')} ${r.produkt}`}
                      value={truck[r.produkt] ?? ''}
                      onChange={e => setTruck(s => ({ ...s, [r.produkt]: e.target.value }))}>
                      <option value="">—</option>
                      {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
      {page && sorted.length === 0 && <EmptyState icon={Package} title={t('pcNone')} />}

      <h2>{t('pcHistory')}</h2>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid" style={{ minWidth: 720 }}>
          <thead><tr><th>{t('pcNumber')}</th><th>{t('status')}</th><th>{t('pcTermin')}</th><th>{t('pcPositions')}</th><th></th></tr></thead>
          <tbody>
            {calls.map(c => (
              <tr key={c.id}>
                <td>{c.number}</td><td>{statusLabel(c.status)}</td><td>{formatDate(c.needed_by)}</td>
                <td>{c.lines?.length ?? 0}</td>
                <td style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button className="btn small secondary" onClick={() => downloadXlsx(c)}>xlsx</button>
                  {isEditor && c.status === 'draft' &&
                    <button className="btn small" onClick={() => act(c.id, 'send')}>{t('pcSendToDlt')}</button>}
                  {isEditor && c.status === 'sent' &&
                    <button className="btn small secondary" onClick={() => act(c.id, 'confirm')}>{t('pcConfirm')}</button>}
                  {canConfirmDlt && (c.status === 'sent' || c.status === 'confirmed') &&
                    <button className="btn small" onClick={() => act(c.id, 'prepared')}>{t('pcMarkPrepared')}</button>}
                  {canConfirmDlt && c.status === 'przygotowane' &&
                    <button className="btn small" onClick={() => act(c.id, 'shipped')}>{t('pcMarkShipped')}</button>}
                  {isEditor && ['sent', 'confirmed', 'przygotowane', 'wyslane_z_dlt'].includes(c.status) &&
                    <button className="btn small secondary" onClick={() => act(c.id, 'deliver')}>{t('pcDelivered')}</button>}
                  {isEditor && c.status !== 'cancelled' && c.status !== 'delivered' &&
                    <button className="btn small danger" onClick={() => act(c.id, 'cancel')}>{t('cancel')}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {page && <HuInventorySection />}

      {isEditor && <PazSection />}
    </main>
  )
}
