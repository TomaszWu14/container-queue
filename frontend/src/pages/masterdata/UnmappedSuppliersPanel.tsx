import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Supplier } from '../../types'

// „Do zmapowania": import kolejki nie tworzy dostawców — nazwy z pliku bez dopasowania
// mapujemy tu na dostawcę (alias w spółce pliku). Spółka na materiałach Acme (catalog)
// mapuje na kartotekę, spółka-klient — na swoich nadawców. Backend przypina od razu
// kontenery z tą nazwą, a kolejne importy rozwiązują ją same.

export interface UnmappedRow { name: string; company_id: number; containers: number; catalog: boolean }

export default function UnmappedSuppliersPanel({ suppliers, isAdmin, onNew }: {
  suppliers: Supplier[]
  isAdmin: boolean
  onNew: (row: UnmappedRow) => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const [rows, setRows] = useState<UnmappedRow[]>([])
  const [pick, setPick] = useState<Record<string, string>>({})
  const load = () =>
    api.get<UnmappedRow[]>('/api/suppliers/unmapped')
      .then(r => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]))
  useEffect(() => { load() }, [suppliers])

  const keyOf = (r: UnmappedRow) => `${r.company_id}|${r.name}`
  const options = (r: UnmappedRow) => suppliers.filter(s =>
    s.client_company_id === r.company_id || (r.catalog && s.client_company_id == null))
  const map = (r: UnmappedRow) =>
    api.post<{ assigned: number }>(`/api/suppliers/${pick[keyOf(r)]}/aliases`,
                                   { alias: r.name, company_id: r.company_id })
      .then(res => { showToast(t('supMappedN').replace('{n}', String(res.assigned))); load() })
      .catch(err => showToast(errorMessage(err), 'error'))

  if (!rows.length) return null
  return (
    <div className="panel" style={{ margin: '8px 0' }} aria-label={t('supUnmappedTitle')}>
      <b>{t('supUnmappedTitle')} ({rows.length})</b>
      <p className="muted" style={{ margin: '4px 0 8px' }}>{t('supUnmappedHint')}</p>
      {rows.map(r => (
        <div key={keyOf(r)} className="row" style={{ gap: 8, flexWrap: 'wrap', padding: '3px 0' }}>
          <span style={{ minWidth: 220, flex: '1 1 220px' }}>{r.name}</span>
          <span className="muted mono" style={{ width: 70 }}>
            {t('supContainersN').replace('{n}', String(r.containers))}</span>
          <select aria-label={`${t('supPick')}: ${r.name}`} value={pick[keyOf(r)] ?? ''}
                  onChange={e => setPick(p => ({ ...p, [keyOf(r)]: e.target.value }))}>
            <option value="">— {t('supPick')} —</option>
            {options(r).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn small" disabled={!pick[keyOf(r)]} onClick={() => map(r)}>
            {t('supMap')}</button>
          {isAdmin && (
            <button className="btn small secondary" onClick={() => onNew(r)}>
              {t('supNewFromName')}</button>
          )}
        </div>
      ))}
    </div>
  )
}
