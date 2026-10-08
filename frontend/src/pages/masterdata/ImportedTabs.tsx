import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../../api'
import { totalOf } from '../../listTotal'
import { formatDate } from '../../dates'
import { useT } from '../../i18n'
import type { Company } from '../../types'
import { dash } from '../admin/shared'
import { Col, EditableTable } from './EditableTable'
import { useIsAdmin } from './tabUtils'

// Zakładki encji z importu (Zamówienia SAP, jednostki MARM, porty kontenerowe) — read-only:
// zostaje historia wiersza (⟲), usuwanie (admin) i link do importu w Administracji.

interface PurchaseOrderRow {
  id: number
  order_no: string
  supplier: string
  etd: string | null
  ready_date: string
  transport_mode: string
  purchase_decision: string
  port_of_departure: string
  amount: number | null
  container_id: number | null
  company_id: number
  created_at: string
}

const SAP_PO_LIMIT = 1000   // przeglądarka: reszta przez wyszukiwanie/filtry (X-Total-Count)

export function SapOrdersTab({ companies }: { companies: Company[] }) {
  const t = useT()
  const isAdmin = useIsAdmin()
  const [rows, setRows] = useState<PurchaseOrderRow[]>([])
  const [q, setQ] = useState('')
  const [companyCode, setCompanyCode] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [ver, setVer] = useState(0)   // bump po usunięciu → refetch
  const [error, setError] = useState('')
  const [total, setTotal] = useState<number | null>(null)
  const companyName = (id: number) => companies.find(c => c.id === id)?.name ?? String(id)

  useEffect(() => {
    const params = new URLSearchParams({ unlinked: 'false', limit: String(SAP_PO_LIMIT) })
    if (q.trim()) params.set('q', q.trim())
    if (companyCode) params.set('company_code', companyCode)
    if (from) params.set('created_from', from)
    if (to) params.set('created_to', to)
    // stale: odpowiedź starszego filtra (wolniejsza) nie nadpisze nowszego; błąd ≠ pusta tabela
    let stale = false
    const timer = setTimeout(() => {
      api.get<PurchaseOrderRow[]>(`/api/purchase-orders?${params}`)
        .then(r => { if (!stale) { setRows(r); setTotal(totalOf(r)); setError('') } })
        .catch(err => { if (!stale) { setRows([]); setTotal(null); setError(errorMessage(err)) } })
    }, 250)   // lekki debounce wyszukiwarki
    return () => { stale = true; clearTimeout(timer) }
  }, [q, companyCode, from, to, ver])

  // Zamówienia SAP są read-only: źródłem jest import EKKO — edycja tutaj rozjechałaby
  // dane z SAP. Zostaje historia wiersza (⟲) i usuwanie (admin).
  const cols: Col<PurchaseOrderRow>[] = [
    { key: 'no', label: t('mdOrderNo'), get: r => r.order_no },
    { key: 'sup', label: t('mdSupplierCol'), get: r => r.supplier },
    { key: 'etd', label: 'ETD', get: r => r.etd ?? '', width: '100px',
      render: r => dash(r.etd ? formatDate(r.etd) : '') },
    { key: 'ready', label: 'Ready', get: r => r.ready_date, width: '110px',
      render: r => dash(r.ready_date ? formatDate(r.ready_date) : '') },
    { key: 'mode', label: 'Transport', get: r => r.transport_mode, width: '100px' },
    { key: 'decision', label: t('mdDecision'), get: r => r.purchase_decision, width: '90px' },
    { key: 'amount', label: t('mdAmount'), get: r => r.amount, width: '110px' },
    { key: 'company', label: t('company'), get: r => companyName(r.company_id), width: '110px' },
    { key: 'created', label: t('mdCreatedAt'), get: r => r.created_at, width: '110px',
      render: r => dash(formatDate(r.created_at)) },
    { key: 'linked', label: t('mdLinked'), get: r => r.container_id, width: '90px',
      render: r => r.container_id
        ? <Link to={`/kontenery/${r.container_id}`}>#{r.container_id}</Link>
        : dash('') },
  ]
  return (
    <div className="panel">
      {error && <p className="error" role="alert">{error}</p>}
      {total !== null && total > rows.length && (
        <p className="kq-truncated" role="status">
          {t('sapPoTruncated').replace('{shown}', String(rows.length)).replace('{total}', String(total))}
        </p>
      )}
      <EditableTable cols={cols} rows={rows} csvName="zamowienia-sap.csv"
        refresh={() => setVer(v => v + 1)} canEdit={isAdmin}
        deletePath="/api/purchase-orders" entityType="purchase_orders"
        nameOf={r => r.order_no} importHref="/master-data/import-po"
        leftControls={<>
          <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
          <select aria-label={t('company')} value={companyCode} onChange={e => setCompanyCode(e.target.value)}>
            <option value="">— {t('company')} —</option>
            {companies.map(c => <option key={c.id} value={c.code}>{c.name}</option>)}
          </select>
          <label>{t('dateFrom')} <input type="date" value={from}
                                        onChange={e => setFrom(e.target.value)} /></label>
          <label>{t('dateTo')} <input type="date" value={to}
                                      onChange={e => setTo(e.target.value)} /></label>
        </>} />
    </div>
  )
}

interface MaterialUnitRow {
  id: number
  material_no: string
  unit: string
  numerator: number
  denominator: number
  volume: number | null
  volume_unit: string
  gross_weight: number | null
  weight_unit: string
  length: number | null
  width: number | null
  height: number | null
  dimension_unit: string
  sap_status?: string
}

export function MaterialUnitsTab() {
  const t = useT()
  const isAdmin = useIsAdmin()
  const [rows, setRows] = useState<MaterialUnitRow[]>([])
  const [q, setQ] = useState('')
  const [ver, setVer] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams({ limit: '500' })
    if (q.trim()) params.set('q', q.trim())
    let stale = false   // jak w zakładce zamówień SAP: bez wyścigu odpowiedzi, błąd ≠ pusta tabela
    const timer = setTimeout(() => {
      api.get<MaterialUnitRow[]>(`/api/material-units?${params}`)
        .then(r => { if (!stale) { setRows(r); setError('') } })
        .catch(err => { if (!stale) { setRows([]); setError(errorMessage(err)) } })
    }, 250)   // debounce jak w zakładce zamówień SAP
    return () => { stale = true; clearTimeout(timer) }
  }, [q, ver])

  // read-only: źródłem jest import MARM z SAP — ręczna edycja przeliczników
  // rozjechałaby się z danymi przy następnym imporcie
  const cols: Col<MaterialUnitRow>[] = [
    // DATA-003: „brak w SAP” = zniknął z pełnego eksportu; przelicznik nadal liczony (decyzja 2026-09-28)
    { key: 'mat', label: t('mdMaterialNo'), get: r => r.material_no,
      render: r => <>{r.material_no}{r.sap_status === 'brak_w_sap'
        && <> <span className="badge danger">{t('sapMissingBadge')}</span></>}</> },
    { key: 'unit', label: t('mdUnit'), get: r => r.unit, width: '80px' },
    { key: 'num', label: t('mdNumerator'), get: r => r.numerator, width: '90px' },
    { key: 'den', label: t('mdDenominator'), get: r => r.denominator, width: '90px' },
    { key: 'vol', label: t('mdVolume'), get: r => r.volume, width: '110px',
      render: r => dash(r.volume != null ? `${r.volume} ${r.volume_unit}` : '') },
    { key: 'weight', label: t('mdWeight'), get: r => r.gross_weight, width: '110px',
      render: r => dash(r.gross_weight != null ? `${r.gross_weight} ${r.weight_unit}` : '') },
    { key: 'dims', label: t('mdDims'), get: r => r.length, width: '150px',
      render: r => dash(r.length != null && r.width != null && r.height != null
        ? `${r.length}×${r.width}×${r.height} ${r.dimension_unit}` : '') },
  ]
  return (
    <div className="panel">
      {error && <p className="error" role="alert">{error}</p>}
      <EditableTable cols={cols} rows={rows} csvName="jednostki-marm.csv"
        refresh={() => setVer(v => v + 1)} canEdit={isAdmin}
        deletePath="/api/material-units" entityType="material_units"
        nameOf={r => `${r.material_no} ${r.unit}`} importHref="/master-data/import-marm"
        leftControls={
          <input aria-label={t('mdMaterialSearch')} placeholder={t('mdMaterialSearch')} value={q}
                 onChange={e => setQ(e.target.value)} />
        } />
    </div>
  )
}

interface ContainerPortRow {
  id: number
  code: string
  name: string
  country_code: string
  country_name: string
  lat: number | null
  lon: number | null
  is_active: boolean
}

// Porty kontenerowe z importu klienta (read-only): kod, nazwa, kraj, czy mają
// współrzędne dopasowane z UN/LOCODE (te bez współrzędnych nie trafiają na mapę).
export function ContainerPortsTab() {
  const t = useT()
  const isAdmin = useIsAdmin()
  const [rows, setRows] = useState<ContainerPortRow[]>([])
  const [q, setQ] = useState('')
  const [ver, setVer] = useState(0)

  useEffect(() => {
    api.get<ContainerPortRow[]>('/api/container-ports')
      .then(setRows).catch(() => setRows([]))
  }, [ver])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle
      ? rows.filter(p => p.code.toLowerCase().includes(needle)
          || p.name.toLowerCase().includes(needle)
          || p.country_name.toLowerCase().includes(needle))
      : rows
  }, [rows, q])

  const cols: Col<ContainerPortRow>[] = [
    { key: 'code', label: t('code'), get: p => p.code, width: '90px' },
    { key: 'name', label: t('name'), get: p => p.name },
    { key: 'cc', label: t('mdCountry'), get: p => p.country_code, width: '70px' },
    { key: 'country', label: t('mdCountry'), get: p => p.country_name, width: '160px' },
    { key: 'coords', label: t('mdCoords'), get: p => (p.lat != null ? 1 : 0), width: '110px',
      render: p => (p.lat != null && p.lon != null ? `${p.lat}, ${p.lon}` : '—') },
  ]
  return (
    <div className="panel">
      <EditableTable cols={cols} rows={filtered} csvName="porty-kontenerowe.csv"
        refresh={() => setVer(v => v + 1)} canEdit={isAdmin}
        deletePath="/api/container-ports" entityType="container_ports"
        nameOf={p => `${p.code} ${p.name}`} importHref="/master-data/import-portow"
        leftControls={
          <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
        } />
    </div>
  )
}
