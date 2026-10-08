import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { formatDate } from '../dates'
import { useT } from '../i18n'
import type { Company, Port, Supplier } from '../types'
import { dash } from './admin/shared'
import {
  ActivePills, Col, EditableTable, filterActive,
} from './masterdata/EditableTable'
import { ActiveFilter, num, str, useIsAdmin } from './masterdata/tabUtils'
import { ContainerPortsTab, MaterialUnitsTab, SapOrdersTab } from './masterdata/ImportedTabs'
import DictionariesTab from './masterdata/DictionariesTab'
import QualityTab from './masterdata/QualityTab'
import ConformityReportTab from './masterdata/ConformityReportTab'
import DocumentsSearchTab from './masterdata/DocumentsSearchTab'
import SupplierMapsTab from './masterdata/SupplierMapsTab'
import AuditTab from './masterdata/AuditTab'
import AgencyTemplatesTab from './masterdata/AgencyTemplatesTab'
import SupplierResolvePanel from './masterdata/SupplierResolvePanel'
import UnmappedSuppliersPanel from './masterdata/UnmappedSuppliersPanel'
import CustomersTab from './admin/CustomersTab'
import MaterialsTab from './admin/MaterialsTab'
import NamedTab from './admin/NamedTab'
import WarehousesTab from './admin/WarehousesTab'
import ChecklistTab from './admin/ChecklistTab'
import DocTemplatesTab from './admin/DocTemplatesTab'
import ProblemsTab from './admin/ProblemsTab'
import ImportTab from './admin/ImportTab'
import PoImportTab from './admin/PoImportTab'
import MarmImportTab from './admin/MarmImportTab'
import SpMaterialsTab from './masterdata/SpMaterialsTab'
import ContainerPortsImportTab from './admin/ContainerPortsImportTab'
import DltStockImportTab from './admin/DltStockImportTab'
import SectionShell, { SectionMore } from './SectionShell'
import { findSection, pathOf } from './sections'
import { useToast } from '../feedback'
import { errorMessage } from '../api'
import { useBusy } from '../useBusy'

// Dane podstawowe w układzie „1a" z wireframe'ów: zakładki-pigułki, wyszukiwarka,
// pigułki Aktywne/Nieaktywne, edycja INLINE w wierszu (istniejące PATCH-e z Administracji),
// dodawanie jako wiersz na górze, ⟲ historia (AuditLog), 🗑 usuwanie (guarded, 409),
// Import CSV = link do sekcji importu (grupa Importy w Master data).
// Encje z importu (Zamówienia SAP, MARM, porty kontenerowe) zostają read-only.

function useCompaniesSafe() {
  const [companies, setCompanies] = useState<Company[]>([])
  useEffect(() => { api.get<Company[]>('/api/companies').then(setCompanies).catch(() => {}) }, [])
  return companies
}

function SuppliersTab({ companies }: { companies: Company[] }) {
  const t = useT()
  const isAdmin = useIsAdmin()
  const { showToast } = useToast()
  const [rows, setRows] = useState<Supplier[]>([])
  const [q, setQ] = useState('')
  // właściciel: '' = wszyscy, 'catalog' = kartoteka Acme, id = nadawcy spółki-klienta
  const [owner, setOwner] = useState('')
  const [act, setAct] = useState<ActiveFilter>('')
  // scalanie duplikatów (#20): źródło znika, jego kontenery/zamówienia/kontakty
  // przechodzą na cel, brakujące pola celu uzupełniane z duplikatu
  const [mergeSource, setMergeSource] = useState<Supplier | null>(null)
  const [mergeTarget, setMergeTarget] = useState('')
  // „+ Nowy dostawca" z panelu Do zmapowania: wiersz dodawania z nazwą i właścicielem z pliku
  const [addPrefill, setAddPrefill] = useState<{ name: string; company: string } | null>(null)
  const [addSignal, setAddSignal] = useState(0)
  const merging = useBusy()   // dwuklik „Scal” = drugi POST na już usunięte źródło (404)
  const doMerge = () => {
    if (!mergeSource || !mergeTarget) return
    void merging.run(() => api.post(`/api/suppliers/${mergeSource.id}/merge`, { target_id: Number(mergeTarget) })
      .then(() => { showToast(t('mdMergeDone')); setMergeSource(null); load() })
      .catch(err => showToast(errorMessage(err), 'error')))
  }
  const load = () => {
    setAddPrefill(null)
    return api.get<Supplier[]>('/api/suppliers?include_inactive=true').then(setRows).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const ownerOf = (s: Supplier) => s.client_company_id ?? null
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return filterActive(rows, act).filter(s =>
      (!owner || (owner === 'catalog' ? ownerOf(s) === null : ownerOf(s) === Number(owner)))
      && (!needle || s.name.toLowerCase().includes(needle)
          || (s.sap_code ?? '').toLowerCase().includes(needle)))
  }, [rows, q, owner, act])

  const ownerName = (s: Supplier) => {
    const id = ownerOf(s)
    return id === null ? t('supCatalog') : companies.find(c => c.id === id)?.name ?? String(id)
  }
  const cols: Col<Supplier>[] = [
    { key: 'sap', label: t('sapCode'), get: s => s.sap_code ?? '', width: '110px' },
    { key: 'name', label: t('name'), get: s => s.name,
      render: s => <Link to={`/dostawcy/${s.id}`}>{s.name}</Link>,
      edit: { type: 'text', width: 180 } },
    { key: 'country', label: t('mdCountry'), get: s => s.country ?? '', width: '70px' },
    { key: 'address', label: t('mdAddress'), get: s => s.address ?? '',
      edit: { type: 'text', width: 220 } },
    { key: 'company', label: t('supOwner'), get: ownerName, width: '150px',
      // właściciela nie zmieniamy po utworzeniu; spółka z materiałami Acme → kartoteka (backend)
      edit: { type: 'select', createOnly: true, value: () => '',
              options: [{ value: '', label: t('supCatalog') },
                        ...companies.map(c => ({ value: String(c.id), label: c.name }))] } },
    { key: 'active', label: t('active'), get: s => (s.is_active !== false ? 1 : 0), width: '80px',
      render: s => (s.is_active !== false ? '✓' : '—'),
      edit: { type: 'check' } },
  ]
  if (isAdmin) {
    // pola z dawnej Administracji → Dostawcy (scalone w jedną sekcję)
    cols.push(
      { key: 'note', label: t('mdNote'), get: s => s.note ?? '', edit: { type: 'text', width: 160 } },
      { key: 'colmap', label: t('columnMap'),
        get: s => s.column_map ?? '', edit: { type: 'text', width: 200 } })
    cols.push({ key: 'merge', label: '', get: () => '', width: '90px',
      render: s => (
        <button className="btn small secondary" title={t('mergeHint')}
                onClick={() => { setMergeSource(s); setMergeTarget('') }}>
          {t('mdMerge')}</button>
      ) })
  }
  // scalać można tylko w obrębie właściciela (kartoteka z kartoteką, nadawcy jednej spółki)
  const mergeTargets = mergeSource
    ? rows.filter(s => s.id !== mergeSource.id && ownerOf(s) === ownerOf(mergeSource))
    : []
  return (
    <div className="panel">
      {isAdmin && <p className="muted" style={{ margin: '0 0 6px' }}>
        {t('columnMap')}: {t('columnMapHint')}</p>}
      {isAdmin && <SupplierResolvePanel suppliers={rows} onChanged={load} />}
      <UnmappedSuppliersPanel suppliers={rows} isAdmin={isAdmin}
        onNew={r => {
          setAddPrefill({ name: r.name, company: r.catalog ? '' : String(r.company_id) })
          setAddSignal(n => n + 1)
        }} />
      {mergeSource && (
        <div className="panel" role="dialog" aria-label={t('mdMergeTitle')}
             style={{ margin: '8px 0', display: 'flex', gap: 8, alignItems: 'center',
                      flexWrap: 'wrap' }}>
          <b>{t('mdMergeTitle')}</b>
          <span>{mergeSource.name} →</span>
          <select aria-label={t('mdMergePick')} value={mergeTarget} onChange={e => setMergeTarget(e.target.value)}>
            <option value="">— {t('mdMergePick')} —</option>
            {mergeTargets.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn small" disabled={!mergeTarget || merging.busy} onClick={doMerge}>
            {t('mdMergeDo')}</button>
          <button className="btn small secondary" onClick={() => setMergeSource(null)}>
            {t('cancel')}</button>
          <span className="muted">{t('mergeHint')}</span>
        </div>
      )}
      <EditableTable cols={cols} rows={filtered} csvName="dostawcy.csv" refresh={load}
        canEdit={isAdmin} editPath="/api/suppliers" createPath="/api/suppliers"
        deletePath="/api/suppliers" entityType="suppliers" nameOf={s => s.name}
        addDefaults={{ active: true, company: '', ...addPrefill }}
        addSignal={addSignal}
        buildBody={(row, v) => ({
          name: str(v.name), is_active: v.active === true,
          address: str(v.address),
          note: v.note === undefined ? row?.note ?? '' : str(v.note),
          column_map: v.colmap === undefined ? row?.column_map ?? '' : str(v.colmap),
          company_id: row ? null : num(v.company),
        })}
        leftControls={<>
          <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
          <select aria-label={t('supOwner')} value={owner} onChange={e => setOwner(e.target.value)}>
            <option value="">— {t('supOwner')} —</option>
            <option value="catalog">{t('supCatalog')}</option>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <ActivePills rows={rows} value={act} onChange={setAct} />
        </>} />
    </div>
  )
}

function PortsTab() {
  const t = useT()
  const isAdmin = useIsAdmin()
  const [rows, setRows] = useState<Port[]>([])
  const [q, setQ] = useState('')
  const [act, setAct] = useState<ActiveFilter>('')
  const load = () =>
    api.get<Port[]>('/api/ports?include_inactive=true').then(setRows).catch(() => {})
  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return filterActive(rows, act)
      .filter(p => !needle || p.name.toLowerCase().includes(needle))
  }, [rows, q, act])

  const cols: Col<Port>[] = [
    { key: 'name', label: t('name'), get: p => p.name, edit: { type: 'text', width: 150 } },
    { key: 'country', label: t('mdCountry'), get: p => p.country, width: '70px',
      edit: { type: 'text', width: 40 } },
    { key: 'category', label: t('mdPortCategory'), get: p => p.category, width: '120px',
      edit: { type: 'select', options: [
        { value: 'GLOWNY_CN', label: 'GLOWNY_CN' }, { value: 'OUT', label: 'OUT' }] } },
    { key: 'tt', label: t('mdTtStd'), get: p => p.transit_time_days, width: '100px',
      edit: { type: 'number' } },
    { key: 'ttLong', label: t('mdTtLong'), get: p => p.transit_time_long_days, width: '110px',
      edit: { type: 'number' } },
    { key: 'active', label: t('active'), get: p => (p.is_active ? 1 : 0), width: '80px',
      render: p => (p.is_active ? '✓' : '—'),
      edit: { type: 'check' } },
  ]
  return (
    <div className="panel">
      <EditableTable cols={cols} rows={filtered} csvName="porty.csv" refresh={load}
        canEdit={isAdmin} editPath="/api/ports" createPath="/api/ports"
        deletePath="/api/ports" entityType="ports" nameOf={p => p.name}
        addLabel={`+ ${t('mdAddPort')}`}
        addDefaults={{ country: 'CN', category: 'OUT', active: true }}
        buildBody={(row, v) => ({
          name: str(v.name), country: str(v.country).toUpperCase() || 'CN',
          category: str(v.category) || 'OUT',
          transit_time_days: num(v.tt), transit_time_long_days: num(v.ttLong),
          is_active: v.active === true,
          // profil sezonowy edytuje panel „Profil sezonowy…” pod tabelą — bez zmian tutaj
          monthly_transit: row?.monthly_transit ?? {},
        })}
        leftControls={<>
          <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
          <ActivePills rows={rows} value={act} onChange={setAct} />
        </>} />
    </div>
  )
}

interface StockTargetRow {
  id: number
  material_no: string
  days: number
  updated_at: string
}

// Cele pokrycia zapasu (dni) per materiał — nadpisania globalnego celu wywołań-DLT (#373),
// w układzie 1a: edycja inline dni (POST to upsert po material_no), dodawanie wierszem
// na górze, 🗑 usuwanie. Bez ⟲ — endpoint celów nie pisze do AuditLog.
function StockTargetsTab() {
  const t = useT()
  const user = useUser()
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'   // Editors
  const [rows, setRows] = useState<StockTargetRow[]>([])
  const [globalDays, setGlobalDays] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [ver, setVer] = useState(0)

  useEffect(() => {
    api.get<{ global_days: number; items: StockTargetRow[] }>('/api/stock-targets')
      .then(r => { setRows(r.items); setGlobalDays(r.global_days) })
      .catch(() => setRows([]))
  }, [ver])

  const filtered = useMemo(() => {
    const needle = q.trim()
    return needle ? rows.filter(r => r.material_no.includes(needle)) : rows
  }, [rows, q])

  const cols: Col<StockTargetRow>[] = [
    { key: 'mat', label: t('pcMaterialNo'), get: r => r.material_no,
      edit: { type: 'text', createOnly: true } },   // klucz upsertu — nie zmieniamy w edycji
    { key: 'days', label: t('pcTargetDaysCol'), get: r => r.days, width: '110px',
      edit: { type: 'number' } },
    { key: 'upd', label: t('pcTargetUpdated'), get: r => r.updated_at,
      render: r => dash(formatDate(r.updated_at)) },
  ]
  return (
    <div className="panel">
      {globalDays != null && (
        <p className="muted">{t('pcTargetGlobal')}: <b>{globalDays}</b> (PALLET_TARGET_DAYS)</p>
      )}
      <EditableTable cols={cols} rows={filtered} csvName="cele-zapasu.csv"
        refresh={() => setVer(v => v + 1)} canEdit={canEdit}
        editPath="/api/stock-targets" createPath="/api/stock-targets"
        deletePath="/api/stock-targets" nameOf={r => r.material_no}
        saveVia="post"   // POST = upsert po material_no; PATCH per id nie istnieje
        buildBody={(row, v) => ({
          material_no: row ? row.material_no : str(v.mat),
          days: num(v.days) ?? 0,
        })}
        leftControls={
          <input aria-label={t('pcMaterialNo')} placeholder={t('pcMaterialNo')} value={q}
                 onChange={e => setQ(e.target.value)} />
        } />
    </div>
  )
}

// Master data = kartoteki, słowniki, importy i kontrola danych (sekcje w sections.ts).
// Sekcje z dawnej Administracji zachowują dostęp tylko dla admina (403 per trasa).
export default function MasterDataPage() {
  const t = useT()
  const navigate = useNavigate()
  const companies = useCompaniesSafe()
  const isAdmin = useIsAdmin()
  // pełny formularz z dawnej Administracji — pod szybką edycją w tabeli, tylko admin
  const more = (label: string, body: ReactNode) =>
    isAdmin && <SectionMore label={label}>{body}</SectionMore>
  const info = (key: string) => <p className="muted" style={{ marginTop: 0 }}>{t(key)}</p>
  const render = (slug: string) => {
    switch (slug) {
      case 'dostawcy': return <SuppliersTab companies={companies} />
      case 'klienci': return <CustomersTab />
      case 'materialy': return <MaterialsTab />
      case 'jednostki-materialow': return <MaterialUnitsTab />
      case 'dane-materialowe-sp': return <SpMaterialsTab />
      case 'armatorzy': return <NamedTab endpoint="/api/carriers" manageable
        extraFields={[{ key: 'demurrage_free_days', label: t('carrierFreeDays') }]} />
      case 'porty': return <><PortsTab />
        {more(t('secPortsMore'), <NamedTab endpoint="/api/ports" manageable monthlyTransit />)}</>
      case 'porty-kontenerowe': return <ContainerPortsTab />
      case 'magazyny': return <><DictionariesTab kind="warehouses" companies={companies} />
        {more(t('secWarehousesMore'), <WarehousesTab />)}</>
      case 'punkty-kontroli': return <ChecklistTab />
      case 'zamowienia-sap': return <SapOrdersTab companies={companies} />
      case 'cele-zapasu': return <StockTargetsTab />
      case 'statusy-sprawy-celnej': return <>{info('caseStatusesInfo')}
        <DictionariesTab kind="caseStatuses" companies={companies} /></>
      case 'typy-dokumentow': return <>{info('documentTypesInfo')}
        <DictionariesTab kind="docTypes" companies={companies} /></>
      case 'szablony-wysylki': return <DocTemplatesTab />
      case 'wzory-plikow-agencji': return <>{info('atplInfo')}<AgencyTemplatesTab /></>
      case 'problemy-dostaw': return <ProblemsTab />
      case 'import-excel': return <ImportTab />
      case 'import-po': return <PoImportTab />
      case 'import-marm': return <MarmImportTab />
      case 'import-portow': return <ContainerPortsImportTab />
      case 'import-dlt': return <DltStockImportTab />
      case 'jakosc-danych': return <QualityTab companies={companies} onGoTab={key => {
        const target = findSection(key)
        if (target) navigate(pathOf(target))
      }} />
      case 'dokumenty': return <DocumentsSearchTab />
      case 'podejrzane-faktury': return <ConformityReportTab />
      case 'mapowania-indeksow': return <SupplierMapsTab companies={companies} />
      case 'audyt': return <AuditTab />
      default: return null
    }
  }
  return <SectionShell area="md" title={t('masterData')} render={render} />
}
