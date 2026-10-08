import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { LoadError } from '../feedback'
import { useT } from '../i18n'
import { formatDateTime } from '../dates'
import { useCompanies, useWarehouses } from './admin/shared'
import { PageHeader } from '../PageHeader'
import { useVisibleInterval } from '../useVisibleInterval'

// W4 #30: tablica zmian dnia — feed z AuditLog od początku dnia (czas PL),
// filtry spółka/magazyn/typ encji/użytkownik, paginacja, auto-refresh 60 s.
type FeedEntry = {
  id: number; at: string; entity_type: string; entity_id: number
  container_no: string | null; field: string; old: string | null; new: string | null
  note: string; user_login: string | null; user_name: string
}
type Feed = {
  total: number; page: number; per_page: number; entries: FeedEntry[]
  entity_types: string[]
  actors: { id: number; login: string; full_name: string }[]
}

const PER_PAGE = 50

export default function ChangesFeedPage() {
  const t = useT()
  const companies = useCompanies()
  const warehouses = useWarehouses()
  const [feed, setFeed] = useState<Feed | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [companyId, setCompanyId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [entityType, setEntityType] = useState('')
  const [userId, setUserId] = useState('')

  // numer żądania: spóźniona odpowiedź dla starego filtra/strony (albo z ticku
  // auto-refreshu) nie nadpisuje listy bieżącego filtra
  const seq = useRef(0)
  const load = useCallback(() => {
    const my = ++seq.current
    const params = new URLSearchParams({ page: String(page), per_page: String(PER_PAGE) })
    if (companyId) params.set('company_id', companyId)
    if (warehouseId) params.set('warehouse_id', warehouseId)
    if (entityType) params.set('entity_type', entityType)
    if (userId) params.set('user_id', userId)
    api.get<Feed>(`/api/changes/feed?${params}`)
      .then(resp => { if (my === seq.current) { setFeed(resp); setError('') } })
      .catch(err => { if (my === seq.current) setError(errorMessage(err)) })
  }, [page, companyId, warehouseId, entityType, userId])

  useEffect(() => { load() }, [load])
  // auto-refresh co 60 s — tablica „na żywo" bez ręcznego odświeżania (tylko widoczna karta)
  useVisibleInterval(load, 60_000)

  const fieldLabel = (f: string) => {
    const label = t('histField_' + f)
    return label === 'histField_' + f ? f : label
  }
  const valLabel = (field: string, v: string | null) => {
    if (v == null || v === '') return '—'
    if (field === 'status') {
      const label = t('st_' + v)
      return label === 'st_' + v ? v : label
    }
    return v
  }

  const pages = feed ? Math.max(1, Math.ceil(feed.total / PER_PAGE)) : 1

  return (
    <main className="page">
      <PageHeader title={t('changesFeedTitle')} subtitle={t('changesFeedHint')} />
      <div className="row" style={{ gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <select value={companyId} aria-label={t('company')}
                onChange={e => { setCompanyId(e.target.value); setPage(1) }}>
          <option value="">{t('changesAllCompanies')}</option>
          {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={warehouseId} aria-label={t('warehouse')}
                onChange={e => { setWarehouseId(e.target.value); setPage(1) }}>
          <option value="">{t('changesAllWarehouses')}</option>
          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <select value={entityType} aria-label={t('changesEntityType')}
                onChange={e => { setEntityType(e.target.value); setPage(1) }}>
          <option value="">{t('changesAllEntities')}</option>
          {(feed?.entity_types ?? []).map(et => <option key={et} value={et}>{et}</option>)}
        </select>
        <select value={userId} aria-label={t('who')}
                onChange={e => { setUserId(e.target.value); setPage(1) }}>
          <option value="">{t('changesAllUsers')}</option>
          {(feed?.actors ?? []).map(a =>
            <option key={a.id} value={a.id}>{a.full_name || a.login}</option>)}
        </select>
        <button className="btn small secondary" onClick={load}>{t('refresh')}</button>
      </div>
      {error && <LoadError message={error} onRetry={load} />}
      {feed && (
        <div className="panel">
          <table className="grid dict-table">
            <thead>
              <tr>
                <th>{t('when')}</th><th>{t('who')}</th><th>{t('changesEntityType')}</th>
                <th>{t('field')}</th><th>{t('changesChange')}</th><th>{t('notes')}</th>
              </tr>
            </thead>
            <tbody>
              {feed.entries.length === 0 && (
                <tr><td colSpan={6} style={{ color: 'var(--muted)' }}>{t('changesEmpty')}</td></tr>
              )}
              {feed.entries.map(entry => (
                <tr key={entry.id}>
                  <td>{formatDateTime(entry.at)}</td>
                  <td>{entry.user_name}</td>
                  <td>{entry.container_no
                    ? <Link to={`/kontenery/${entry.entity_id}`}>{entry.container_no}</Link>
                    : `${entry.entity_type} #${entry.entity_id}`}</td>
                  <td>{fieldLabel(entry.field)}</td>
                  <td>
                    {entry.old != null && entry.old !== '' && (
                      <><span className="feed-old">{valLabel(entry.field, entry.old)}</span>{' → '}</>
                    )}
                    {valLabel(entry.field, entry.new)}
                  </td>
                  <td>{entry.note || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row" style={{ justifyContent: 'space-between', marginTop: 10 }}>
            <span style={{ color: 'var(--muted)' }}>
              {t('changesTotal')}: {feed.total}
            </span>
            <span className="row" style={{ gap: 8 }}>
              <button className="btn small secondary" disabled={page <= 1}
                      aria-label={t('pagePrev')} onClick={() => setPage(p => p - 1)}>‹</button>
              <span>{page} / {pages}</span>
              <button className="btn small secondary" disabled={page >= pages}
                      aria-label={t('pageNext')} onClick={() => setPage(p => p + 1)}>›</button>
            </span>
          </div>
        </div>
      )}
    </main>
  )
}
