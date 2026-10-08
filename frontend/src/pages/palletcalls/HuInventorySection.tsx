import { TriangleAlertIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, downloadCsv, errorMessage, toCsv } from '../../api'
import { useT } from '../../i18n'
import { formatNum } from '../../dates'

// #65: inwentaryzacja HU — rozjazdy HU wg PBI (stan DLT) vs HU wywołane/przyjęte
type HuRow = {
  produkt: string; hu: string; ilosc: number | null
  in_dlt: boolean; called: boolean; call_number: string; call_status: string
  mismatch: boolean
}
type HuInventory = {
  available: boolean; rows: HuRow[]; mismatches?: number; fetched_at?: string | null
}

export function huInventoryCsv(rows: HuRow[]): string {
  return toCsv([
    ['produkt', 'hu', 'ilosc', 'w_dlt', 'wywolane', 'wywolanie', 'status', 'rozjazd'],
    ...rows.map(r => [
      r.produkt, r.hu, r.ilosc ?? '', r.in_dlt ? 'tak' : 'nie',
      r.called ? 'tak' : 'nie', r.call_number, r.call_status,
      r.mismatch ? 'tak' : 'nie',
    ]),
  ])
}

export default function HuInventorySection() {
  const t = useT()
  const [inv, setInv] = useState<HuInventory | null>(null)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.get<HuInventory>('/api/pallet-calls/hu-inventory')
      .then(setInv).catch(e => setMsg(errorMessage(e)))
  }, [])

  const exportCsv = () => {
    if (!inv) return
    downloadCsv('inwentaryzacja_hu.csv', huInventoryCsv(inv.rows))
  }

  return (
    <>
      <h2>{t('huInvTitle')}</h2>
      {msg && <p className="error">{msg}</p>}
      {inv && !inv.available && <p className="muted">{t('huInvUnavailable')}</p>}
      {inv && inv.available && (
        <>
          <div className="row" style={{ gap: 12, alignItems: 'center', marginBottom: 8 }}>
            <span className="muted">{t('huInvMismatches')}: <b>{inv.mismatches ?? 0}</b></span>
            <button className="btn small secondary" onClick={exportCsv}>{t('huInvExport')}</button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="grid" style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  <th>{t('pcProduct')}</th><th>HU</th><th>{t('huInvQty')}</th>
                  <th>{t('huInvInDlt')}</th><th>{t('huInvCalled')}</th>
                  <th>{t('huInvCall')}</th><th>{t('status')}</th>
                </tr>
              </thead>
              <tbody>
                {inv.rows.map(r => (
                  <tr key={`${r.produkt}:${r.hu}`} className={r.mismatch ? 'row-urgent' : ''}>
                    <td>{r.produkt}</td>
                    <td className="mono">{r.hu}</td>
                    <td>{r.ilosc == null ? '—' : formatNum(r.ilosc, 0)}</td>
                    <td>{r.in_dlt ? '✓' : '—'}</td>
                    <td>{r.called ? '✓' : '—'}</td>
                    <td>{r.call_number}</td>
                    <td>{r.mismatch && <><TriangleAlertIcon size={14} /> {t('huInvMismatch')}</>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
