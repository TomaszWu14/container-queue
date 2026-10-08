// Podgląd importu LFA1 (kartoteka dostawców, spec 2026-09-25 §3): 4 zakładki z licznikami —
// Nowi · Zmienieni (pole po polu stara→nowa) · Zniknęli z SAP · Błędy. Zniknięci są oznaczani
// „nieaktywny w SAP” tylko przy zaznaczonym „pełny eksport” (decyzja usera 2026-09-26).
import { useState } from 'react'
import { useT } from '../../i18n'

interface Brief { id: number; sap_code: string; name: string }
export interface Lfa1Result {
  counts: { total: number; new: number; changed: number; disappeared: number; errors: number }
  new: { sap_code: string; name: string; country: string }[]
  changed: (Brief & { changes: { field: string; old: string; new: string }[] })[]
  disappeared: Brief[]
  errors: { row: number; sap_code: string; name: string; reason: string }[]
}

type Tab = 'new' | 'changed' | 'disappeared' | 'errors'
const TABS: Tab[] = ['new', 'changed', 'disappeared', 'errors']

export function isLfa1Result(r: unknown): r is Lfa1Result {
  const x = r as Lfa1Result | null
  return !!x && typeof x.counts?.disappeared === 'number' && Array.isArray(x.changed)
}

export default function Lfa1Preview({ data, fullExport, onFullExport }: {
  data: Lfa1Result; fullExport: boolean; onFullExport: (v: boolean) => void
}) {
  const t = useT()
  const [tab, setTab] = useState<Tab>(() => TABS.find(k => data.counts[k] > 0) ?? 'new')
  const shown = data[tab].length
  const more = data.counts[tab] - shown
  const field = (f: string) => { const k = `lfa1F_${f}`; const v = t(k); return v === k ? f : v }
  const value = (f: string, v: string) => (f === 'sap_status' && v ? t(`lfa1S_${v}`) : v) || '—'

  return (
    <div data-testid="lfa1-preview" style={{ marginTop: 10 }}>
      <div className="tabs">
        {TABS.map(k => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
            {t(`lfa1Tab_${k}`)} ({data.counts[k]})
          </button>
        ))}
      </div>
      {shown === 0 ? <p className="muted">{t('lfa1Empty')}</p> : (
        <table className="grid">
          <tbody>
            {tab === 'new' && data.new.map(r => (
              <tr key={r.sap_code}><td className="mono">{r.sap_code}</td><td>{r.name}</td><td>{r.country}</td></tr>))}
            {tab === 'changed' && data.changed.map(r => (
              <tr key={r.id}><td className="mono">{r.sap_code}</td><td>{r.name}</td>
                <td>{r.changes.map(c => (
                  <div key={c.field}><span className="muted">{field(c.field)}:</span>{' '}
                    <s className="muted">{value(c.field, c.old)}</s> → <b>{value(c.field, c.new)}</b></div>))}</td></tr>))}
            {tab === 'disappeared' && data.disappeared.map(r => (
              <tr key={r.id}><td className="mono">{r.sap_code}</td><td>{r.name}</td></tr>))}
            {tab === 'errors' && data.errors.map(r => (
              <tr key={`${r.row}-${r.sap_code}`}><td className="mono">{t('lfa1Row')} {r.row}</td>
                <td className="mono">{r.sap_code || '—'}</td><td>{r.name || '—'}</td><td>{r.reason}</td></tr>))}
          </tbody>
        </table>
      )}
      {more > 0 && <p className="muted">{t('lfa1More').replace('{n}', String(more))}</p>}
      {tab === 'disappeared' && data.counts.disappeared > 0 && (
        <p className="muted">{t(fullExport ? 'lfa1DisappearedFull' : 'lfa1DisappearedPartial')}</p>)}
      <label style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
        <input type="checkbox" checked={fullExport} onChange={e => onFullExport(e.target.checked)} />
        {t('lfa1FullExport').replace('{n}', String(data.counts.disappeared))}
      </label>
    </div>
  )
}
