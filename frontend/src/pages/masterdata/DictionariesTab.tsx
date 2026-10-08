import { useEffect, useMemo, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { Company } from '../../types'
import { ActivePills, Col, EditValue, EditableTable, filterActive } from './EditableTable'
import { ActiveFilter, num, str, useIsAdmin } from './tabUtils'

export type DictKind = 'companies' | 'warehouses' | 'agencies' | 'docTypes' | 'caseStatuses'

interface DictRow {
  id: number
  name: string
  is_active?: boolean
  [k: string]: unknown
}

// Konfiguracja per słownik: skąd czytać, gdzie pisać, jak zbudować pełne body PATCH-a
// (endpointy przyjmują komplet pól — brakujące bierzemy z wiersza).
// Spółki celowo bez usuwania — to korzeń separacji danych; zostaje dezaktywacja.
// kind: jeden słownik na sekcję (/master-data/<slug>, /administracja/<slug>) — bez podzakładek.
export default function DictionariesTab({ kind, companies }: { kind: DictKind; companies: Company[] }) {
  const t = useT()
  const isAdmin = useIsAdmin()
  const [rows, setRows] = useState<DictRow[]>([])
  const [q, setQ] = useState('')
  const [act, setAct] = useState<ActiveFilter>('')

  const SOURCES: Record<DictKind, string> = {
    companies: '/api/companies',
    warehouses: '/api/warehouses',
    // admin widzi pełny rejestr (z nieaktywnymi); pozostali — aktywne z widoku celnego
    agencies: isAdmin ? '/api/customs-agencies' : '/api/customs/agencies',
    docTypes: '/api/customs/document-types',
    caseStatuses: '/api/customs/case-statuses',
  }
  const [error, setError] = useState('')
  // numer żądania: wolna odpowiedź poprzedniego słownika nie nadpisze bieżącego
  const seq = useRef(0)
  const load = () => {
    const my = ++seq.current
    setError('')
    return api.get<DictRow[]>(SOURCES[kind])
      .then(r => { if (my === seq.current) setRows(r) })
      .catch(err => { if (my === seq.current) setError(errorMessage(err)) })
  }
  useEffect(() => {
    setRows([])
    setAct('')
    load()
  }, [kind])   // eslint-disable-line react-hooks/exhaustive-deps
  const companyName = (id: unknown) =>
    companies.find(c => c.id === id)?.name ?? (id == null ? '' : String(id))

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return filterActive(rows, act)
      .filter(r => !needle || r.name.toLowerCase().includes(needle))
  }, [rows, q, act])

  const yesNo = (v: unknown) => (v ? '✓' : '—')
  const nameCol: Col<DictRow> = {
    key: 'name', label: t('name'), get: r => r.name, edit: { type: 'text', width: 180 },
  }
  const activeCol: Col<DictRow> = {
    key: 'active', label: t('active'), get: r => (r.is_active !== false ? 1 : 0), width: '90px',
    render: r => yesNo(r.is_active), edit: { type: 'check' },
  }

  const cfg: Record<DictKind, {
    cols: Col<DictRow>[]
    editPath?: string
    createPath?: string
    deletePath?: string
    entityType: string
    hasActive: boolean
    buildBody?: (row: DictRow | null, v: Record<string, EditValue>) => unknown
  }> = {
    companies: {
      cols: [nameCol,
        { key: 'code', label: t('code'), get: r => String(r.code ?? ''), width: '110px',
          edit: { type: 'text', width: 90 } },
        activeCol],
      editPath: '/api/companies', createPath: '/api/companies',
      entityType: 'companies', hasActive: true,
      buildBody: (row, v) => ({
        name: str(v.name), code: str(v.code).toUpperCase(), is_active: v.active === true,
        avizo_cc: String(row?.avizo_cc ?? '') }),
    },
    warehouses: {
      cols: [nameCol,
        { key: 'company', label: t('company'), get: r => companyName(r.company_id),
          width: '130px' },
        { key: 'country', label: t('mdCountry'), get: r => String(r.country ?? ''), width: '80px',
          edit: { type: 'select', options: [
            { value: 'PL', label: 'PL' }, { value: 'PT', label: 'PT' }] } },
        { key: 'email', label: 'E-mail', get: r => String(r.email ?? ''),
          edit: { type: 'text', width: 200 } },
        { key: 'limit', label: t('dailyLimit'),
          get: r => Number(r.default_daily_limit ?? 0), width: '110px',
          edit: { type: 'number' } }],
      editPath: '/api/warehouses', createPath: '/api/warehouses',
      deletePath: '/api/warehouses', entityType: 'warehouses', hasActive: false,
      buildBody: (row, v) => ({
        name: str(v.name), email: str(v.email), country: str(v.country) || 'PL',
        default_daily_limit: num(v.limit) ?? 7,
        company_id: row?.company_id ?? companies[0]?.id ?? null,
        address: String(row?.address ?? ''),
        contact_phone: String(row?.contact_phone ?? ''),
        entry_instructions: String(row?.entry_instructions ?? ''),
      }),
    },
    agencies: {
      cols: [nameCol,
        { key: 'email', label: 'E-mail', get: r => String(r.email ?? ''),
          edit: { type: 'text', width: 200 } },
        { key: 'contact', label: t('mdContact'), get: r => String(r.contact_person ?? ''),
          edit: { type: 'text', width: 160 } },
        activeCol],
      editPath: '/api/customs-agencies', createPath: '/api/customs-agencies',
      deletePath: '/api/customs-agencies', entityType: 'customs_agencies', hasActive: isAdmin,
      buildBody: (row, v) => ({
        name: str(v.name), email: str(v.email), is_active: v.active === true,
        contact_person: str(v.contact),
        contact_phone: String(row?.contact_phone ?? ''),
        address: String(row?.address ?? ''), note: String(row?.note ?? ''),
      }),
    },
    docTypes: {
      cols: [nameCol,
        { key: 'required', label: t('mdRequired'), get: r => (r.is_required ? 1 : 0),
          width: '100px', render: r => yesNo(r.is_required),
          edit: { type: 'check' } },
        // kafelek dokumentów dostawy (spec 2026-10-01): stały kod, jeden typ na kafelek
        { key: 'tile', label: t('dtTileCol'), get: r => String(r.tile_code ?? ''), width: '120px',
          render: r => (r.tile_code ? String(r.tile_code).replace('_', '-') : '—'),
          edit: { type: 'select', options: [{ value: '', label: '—' },
            ...['PI', 'CI', 'PL', 'BL', 'SAD_DRAFT', 'SAD_PZ', 'SAD_PW'].map(c => ({ value: c, label: c.replace('_', '-') }))] } },
        activeCol],
      editPath: '/api/customs/document-types', createPath: '/api/customs/document-types',
      deletePath: '/api/customs/document-types', entityType: 'document_types', hasActive: true,
      buildBody: (row, v) => ({
        name: str(v.name), sort_order: Number(row?.sort_order ?? 100),
        is_active: v.active === true, is_required: v.required === true,
        tile_code: str(v.tile) || null,   // bez tego zapis typu kasowałby kod kafelka
      }),
    },
    caseStatuses: {
      cols: [nameCol,
        { key: 'order', label: '#', get: r => Number(r.sort_order ?? 0), width: '70px',
          edit: { type: 'number' } },
        activeCol],
      editPath: '/api/customs/case-statuses', createPath: '/api/customs/case-statuses',
      deletePath: '/api/customs/case-statuses', entityType: 'customs_case_statuses',
      hasActive: true,
      buildBody: (_row, v) => ({
        name: str(v.name), sort_order: num(v.order) ?? 100, is_active: v.active === true }),
    },
  }
  const c = cfg[kind]

  return (
    <div className="panel">
      {error && <p className="error">{error}</p>}
      <EditableTable key={kind} cols={c.cols} rows={filtered} csvName={`slownik-${kind}.csv`}
        refresh={load} canEdit={isAdmin} editPath={c.editPath} createPath={c.createPath}
        deletePath={c.deletePath} entityType={c.entityType} nameOf={r => r.name}
        addDefaults={{ active: true, country: 'PL', limit: '7' }}
        buildBody={c.buildBody}
        leftControls={<>
          <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
          {c.hasActive && <ActivePills rows={rows} value={act} onChange={setAct} />}
        </>} />
    </div>
  )
}
