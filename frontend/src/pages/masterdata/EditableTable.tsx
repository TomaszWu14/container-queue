import { ArrowDownIcon, ArrowUpIcon, PencilIcon, Trash2Icon } from 'lucide-react'
import { Fragment, ReactNode, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, downloadCsv, errorMessage, toCsv } from '../../api'
import { formatDate } from '../../dates'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import { DictTable, dash } from '../admin/shared'
import { useConfirm } from '../../ConfirmDialog'

// Generyczna tabela master data w układzie „1a" z wireframe'ów: edycja INLINE w wierszu
// (klik w komórkę → inputy + Zapisz/Anuluj), dodawanie jako wiersz na górze tabeli,
// ⟲ historia wiersza (AuditLog), 🗑 usuwanie (guarded_delete, 409 z komunikatem),
// sort po nagłówku, paginacja, eksport CSV. Jedna implementacja dla wszystkich zakładek.

export type EditValue = string | boolean

export interface EditSpec<T> {
  type: 'text' | 'number' | 'select' | 'check'
  options?: { value: string; label: string }[]   // dla select
  value?: (r: T) => EditValue                    // wartość startowa; domyślnie get(r)
  width?: number                                 // szerokość inputa (px)
  createOnly?: boolean                           // pole tylko przy dodawaniu (np. spółka)
}

export interface Col<T> {
  key: string
  label: ReactNode
  get: (row: T) => string | number | null | undefined   // wartość do sortu/CSV
  render?: (row: T) => ReactNode
  width?: string
  edit?: EditSpec<T>
}

export interface AuditEntry {
  id: number
  entity_id?: number
  field: string
  old_value: string | null
  new_value: string | null
  note: string
  user_login: string | null
  created_at: string
}

interface Props<T> {
  cols: Col<T>[]
  rows: T[]
  csvName: string
  refresh: () => void
  /** pasek nad tabelą po lewej: wyszukiwarka + pigułki filtrów (od rodzica) */
  leftControls?: ReactNode
  canEdit?: boolean
  editPath?: string                    // PATCH `${editPath}/${id}` (lub POST, patrz saveVia)
  saveVia?: 'patch' | 'post'           // 'post' = endpoint-upsert (np. cele zapasu)
  createPath?: string                  // POST — wiersz „dodaj" na górze tabeli
  buildBody?: (row: T | null, vals: Record<string, EditValue>) => unknown
  addDefaults?: Record<string, EditValue>
  /** zmiana wartości (>0) otwiera wiersz „dodaj" z addDefaults — np. „+ Nowy dostawca" z nazwą */
  addSignal?: number
  addLabel?: string
  deletePath?: string                  // DELETE `${deletePath}/${id}` (guarded, 409)
  nameOf?: (r: T) => string
  entityType?: string                  // ⟲ GET /api/audit/{entityType}/{id}
  importHref?: string                  // link do sekcji importu (Master data → Importy)
}

const PAGE = 200

function exportCsv(filename: string, cols: { label: ReactNode; get: (r: never) => unknown }[],
                   rows: unknown[]) {
  downloadCsv(filename, toCsv([
    cols.map(c => typeof c.label === 'string' ? c.label : ''),
    ...rows.map(r => cols.map(c => (c.get as (x: unknown) => unknown)(r))),
  ]))
}

// pigułki filtrów Aktywne N / Nieaktywne N (wireframe 1a) — dla encji z is_active
export function ActivePills({ rows, value, onChange }: {
  rows: { is_active?: boolean }[]
  value: '' | 'active' | 'inactive'
  onChange: (v: '' | 'active' | 'inactive') => void
}) {
  const t = useT()
  const active = rows.filter(r => r.is_active !== false).length
  const opts: ['' | 'active' | 'inactive', string, number][] = [
    ['', t('mdAll'), rows.length],
    ['active', t('mdActivePill'), active],
    ['inactive', t('mdInactivePill'), rows.length - active],
  ]
  return (
    <span className="tabs" style={{ margin: 0 }}>
      {opts.map(([key, label, n]) => (
        <button key={key} type="button" className={value === key ? 'active' : ''}
                onClick={() => onChange(key)}>{`${label} ${n}`}</button>
      ))}
    </span>
  )
}

export function filterActive<T extends { is_active?: boolean }>(
    rows: T[], f: '' | 'active' | 'inactive'): T[] {
  if (!f) return rows
  return rows.filter(r => (r.is_active !== false) === (f === 'active'))
}

// label = nagłówek kolumny jako nazwa pola dla czytnika ekranu (w wierszu tabeli nie ma <label>)
function EditCell<T>({ spec, value, onChange, label }: {
  spec: EditSpec<T>; value: EditValue; onChange: (v: EditValue) => void; label?: string
}) {
  if (spec.type === 'check') {
    return <input type="checkbox" aria-label={label} checked={value === true}
                  onChange={e => onChange(e.target.checked)} />
  }
  if (spec.type === 'select') {
    return (
      <select aria-label={label} value={String(value)} onChange={e => onChange(e.target.value)}>
        {(spec.options ?? []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    )
  }
  return <input type={spec.type === 'number' ? 'number' : 'text'} aria-label={label} value={String(value)}
                style={{ width: spec.width ?? (spec.type === 'number' ? 70 : 140) }}
                onChange={e => onChange(e.target.value)} />
}

function HistoryRow({ entityType, id, span }: { entityType: string; id: number; span: number }) {
  const t = useT()
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  useEffect(() => {
    api.get<AuditEntry[]>(`/api/audit/${entityType}/${id}`)
      .then(setEntries).catch(() => setEntries([]))
  }, [entityType, id])
  return (
    <tr className="md-history">
      <td colSpan={span} style={{ background: 'var(--soft)' }}>
        {entries === null ? <span className="muted">{t('loading')}</span>
          : !entries.length ? <span className="muted">{t('mdNoHistory')}</span>
          : (
            <table className="grid" style={{ margin: '4px 0', fontSize: 12 }}>
              <thead><tr><th>{t('mdHistDate')}</th><th>{t('mdHistUser')}</th>
                <th>{t('mdHistField')}</th><th>{t('mdHistChange')}</th></tr></thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.id}>
                    <td>{formatDate(e.created_at)}</td>
                    <td>{dash(e.user_login)}</td>
                    <td>{e.field}</td>
                    <td>{dash(e.old_value)} → {dash(e.new_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </td>
    </tr>
  )
}

// „Historia zmian" całej zakładki (#19): listing AuditLog per entity_type, paginowany,
// filtry po polu i dacie (serwer) oraz loginie (na wczytanej stronie).
export function TypeHistory({ entityType }: { entityType: string }) {
  const t = useT()
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  const [field, setField] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [who, setWho] = useState('')
  const [page, setPage] = useState(0)
  const LIMIT = 50
  useEffect(() => {
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
    if (field.trim()) params.set('field', field.trim())
    if (from) params.set('date_from', from)
    if (to) params.set('date_to', to)
    const timer = setTimeout(() => {
      api.get<AuditEntry[]>(`/api/audit/${entityType}?${params}`)
        .then(setEntries).catch(() => setEntries([]))
    }, 250)
    return () => clearTimeout(timer)
  }, [entityType, field, from, to, page])
  const shown = (entries ?? []).filter(e =>
    !who.trim() || (e.user_login ?? '').toLowerCase().includes(who.trim().toLowerCase()))
  return (
    <div className="panel" style={{ margin: '8px 0' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input aria-label={t('mdHistField')} placeholder={t('mdHistField')} value={field} style={{ width: 120 }}
               onChange={e => { setField(e.target.value); setPage(0) }} />
        <input aria-label={t('mdHistUser')} placeholder={t('mdHistUser')} value={who} style={{ width: 120 }}
               onChange={e => setWho(e.target.value)} />
        <label>{t('dateFrom')} <input type="date" value={from}
               onChange={e => { setFrom(e.target.value); setPage(0) }} /></label>
        <label>{t('dateTo')} <input type="date" value={to}
               onChange={e => { setTo(e.target.value); setPage(0) }} /></label>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="btn small secondary" disabled={page === 0}
                  aria-label={t('pagePrev')} onClick={() => setPage(p => p - 1)}>‹</button>
          {page + 1}
          <button className="btn small secondary" disabled={(entries?.length ?? 0) < LIMIT}
                  aria-label={t('pageNext')} onClick={() => setPage(p => p + 1)}>›</button>
        </span>
      </div>
      {entries === null ? <p className="muted">{t('loading')}</p>
        : !shown.length ? <p className="muted">{t('mdNoHistory')}</p>
        : (
          <table className="grid" style={{ marginTop: 6, fontSize: 13 }}>
            <thead><tr><th>{t('mdHistDate')}</th><th>ID</th><th>{t('mdHistUser')}</th>
              <th>{t('mdHistField')}</th><th>{t('mdHistChange')}</th></tr></thead>
            <tbody>
              {shown.map(e => (
                <tr key={e.id}>
                  <td>{formatDate(e.created_at)}</td>
                  <td>{e.entity_id}</td>
                  <td>{dash(e.user_login)}</td>
                  <td>{e.field}</td>
                  <td>{dash(e.old_value)} → {dash(e.new_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}

export function EditableTable<T extends { id: number }>(props: Props<T>) {
  const { cols, rows, csvName, refresh, canEdit, editPath, createPath, buildBody,
          deletePath, nameOf, entityType, importHref, leftControls, addDefaults,
          addLabel, saveVia, addSignal } = props
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const [page, setPage] = useState(0)
  const [editingId, setEditingId] = useState<number | null>(null)   // -1 = wiersz „dodaj"
  const [vals, setVals] = useState<Record<string, EditValue>>({})
  const [saving, setSaving] = useState(false)
  const [historyId, setHistoryId] = useState<number | null>(null)
  const [typeHistory, setTypeHistory] = useState(false)
  useEffect(() => { setPage(0) }, [rows])

  const editable = !!(canEdit && editPath && buildBody)
  const editCols = cols.filter(c => c.edit)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = cols.find(c => c.key === sort.key)
    if (!col) return rows
    return [...rows].sort((a, b) => {
      const va = col.get(a), vb = col.get(b)
      if (va == null || va === '') return 1        // puste zawsze na koniec
      if (vb == null || vb === '') return -1
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sort.dir
      return String(va).localeCompare(String(vb), 'pl') * sort.dir
    })
  }, [rows, sort, cols])

  const pages = Math.ceil(sorted.length / PAGE)
  const visible = sorted.slice(page * PAGE, (page + 1) * PAGE)

  const startEdit = (row: T) => {
    if (!editable) return
    const init: Record<string, EditValue> = {}
    for (const c of editCols) {
      init[c.key] = c.edit!.value ? c.edit!.value(row)
        : c.edit!.type === 'check' ? !!c.get(row)   // get() zwraca 1/0 do sortu
        : String(c.get(row) ?? '')
    }
    setVals(init)
    setEditingId(row.id)
    setHistoryId(null)
  }

  const startAdd = () => {
    setVals({ ...(addDefaults ?? {}) })
    setEditingId(-1)
    setHistoryId(null)
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (addSignal) startAdd() }, [addSignal])

  const save = (row: T | null) => {
    if (!buildBody) return
    setSaving(true)
    const req = row
      ? (saveVia === 'post'
          ? api.post(editPath!, buildBody(row, vals))
          : api.patch(`${editPath}/${row.id}`, buildBody(row, vals)))
      : api.post(createPath!, buildBody(null, vals))
    req.then(() => { setEditingId(null); refresh() })
      .catch(err => showToast(errorMessage(err), 'error'))
      .finally(() => setSaving(false))
  }

  const remove = async (row: T) => {
    const name = nameOf ? nameOf(row) : String(row.id)
    if (!(await confirm(t('mdDeleteConfirm').replace('{name}', name), { danger: true }))) return
    api.del(`${deletePath}/${row.id}`)
      .then(() => { showToast(t('deleteDone')); refresh() })
      .catch(err => showToast(errorMessage(err), 'error'))
  }

  const onKey = (row: T | null) => (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !saving) save(row)
    if (e.key === 'Escape') setEditingId(null)
  }

  const hasActions = !!(editable || (canEdit && deletePath) || entityType)
  const span = cols.length + (hasActions ? 1 : 0)

  const header = (c: Col<T>) => ({
    label: (
      <button type="button" className="md-sort" title={t('mdSortHint')}
              onClick={() => setSort(s => s?.key === c.key
                ? { key: c.key, dir: s.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 })}
              style={{ all: 'unset', cursor: 'pointer', fontWeight: 600 }}>
        {c.label}{sort?.key === c.key && (sort.dir === 1 ? <ArrowUpIcon size={12} /> : <ArrowDownIcon size={12} />)}
      </button>
    ),
    width: c.width,
  })

  const editRow = (row: T | null) => (
    <tr className="md-edit-row" onKeyDown={onKey(row)}>
      {cols.map(c => (
        <td key={c.key}>
          {c.edit && !(row && c.edit.createOnly)
            ? <EditCell spec={c.edit} value={vals[c.key] ?? ''} label={typeof c.label === 'string' ? c.label : c.key}
                        onChange={v => setVals(s => ({ ...s, [c.key]: v }))} />
            : (row ? (c.render ? c.render(row) : dash(c.get(row))) : null)}
        </td>
      ))}
      {hasActions && (
        <td style={{ whiteSpace: 'nowrap' }}>
          <button className="btn small" disabled={saving} onClick={() => save(row)}>
            {t('save')}</button>{' '}
          <button className="btn small secondary" onClick={() => setEditingId(null)}>
            {t('cancel')}</button>
        </td>
      )}
    </tr>
  )

  return (
    <>
      <div className="actions" style={{ display: 'flex', gap: 8, alignItems: 'center',
                                        flexWrap: 'wrap', margin: '8px 0' }}>
        {leftControls}
        <span style={{ flex: 1 }} />
        {entityType && (
          <button className={`btn small ${typeHistory ? '' : 'secondary'}`}
                  onClick={() => setTypeHistory(h => !h)}>{t('mdTypeHistory')}</button>
        )}
        {importHref && <Link className="btn small secondary" to={importHref}>{t('importCsv')}</Link>}
        <button className="btn small secondary" disabled={!sorted.length}
                onClick={() => exportCsv(csvName, cols as never, sorted)}>
          {t('exportCsv')}
        </button>
        {canEdit && createPath && buildBody && (
          <button className="btn small" onClick={startAdd}>{addLabel ?? t('mdAdd')}</button>
        )}
      </div>
      <div className="actions" style={{ display: 'flex', gap: 8, alignItems: 'center',
                                        margin: '8px 0' }}>
        <span className="muted">
          {sorted.length} {t('mdRows')}{editable ? ` · ${t('mdInlineEdit')}` : ''}
        </span>
        {pages > 1 && (
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className="btn small secondary" disabled={page === 0}
                    aria-label={t('pagePrev')} onClick={() => setPage(p => p - 1)}>‹</button>
            {page + 1} / {pages}
            <button className="btn small secondary" disabled={page >= pages - 1}
                    aria-label={t('pageNext')} onClick={() => setPage(p => p + 1)}>›</button>
          </span>
        )}
      </div>
      {typeHistory && entityType && <TypeHistory entityType={entityType} />}
      <DictTable cols={[...cols.map(header), ...(hasActions ? [{ label: '', width: '110px' }] : [])]}>
        {editingId === -1 && editRow(null)}
        {visible.map(r => (
          <Fragment key={r.id}>
            {editingId === r.id ? editRow(r) : (
              <tr>
                {cols.map(c => (
                  <td key={c.key}
                      onClick={c.edit && editable ? () => startEdit(r) : undefined}
                      style={c.edit && editable ? { cursor: 'pointer' } : undefined}>
                    {c.render ? c.render(r) : dash(c.get(r))}
                  </td>
                ))}
                {hasActions && (
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {editable && (
                      <button className="btn small secondary" title={t('mdEditRow')}
                              aria-label={t('mdEditRow')} onClick={() => startEdit(r)}><PencilIcon size={14} /></button>
                    )}{' '}
                    {entityType && (
                      <button className="btn small secondary" title={t('mdHistory')}
                              aria-label={t('mdHistory')}
                              onClick={() => setHistoryId(h => h === r.id ? null : r.id)}>⟲</button>
                    )}{' '}
                    {canEdit && deletePath && (
                      <button className="btn small danger" title={t('del')} aria-label={t('del')}
                              onClick={() => remove(r)}><Trash2Icon size={14} /></button>
                    )}
                  </td>
                )}
              </tr>
            )}
            {historyId === r.id && entityType && (
              <HistoryRow entityType={entityType} id={r.id} span={span} />
            )}
          </Fragment>
        ))}
      </DictTable>
    </>
  )
}
