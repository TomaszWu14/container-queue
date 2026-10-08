import { PackageIcon, TruckIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, api, errorMessage } from '../api'
import { LoadError } from '../feedback'
import { useT } from '../i18n'
import { formatDate } from '../dates'

interface DltLine {
  produkt: string
  krotki_opis: string
  ilosc_pal: number
  pallets: number | null
  hu_numbers: string
  data_dostawy: string | null
}

interface DltInfo {
  number: string
  status: string
  needed_by: string | null
  notes: string
  trucks: { ordinal: number; capacity: number; lines: DltLine[] }[]
  unassigned_lines: DltLine[]
}

function Lines({ lines }: { lines: DltLine[] }) {
  const t = useT()
  return (
    <table className="grid">
      <thead>
        <tr><th>{t('pcProduct')}</th><th>pal.</th><th>HU</th></tr>
      </thead>
      <tbody>
        {lines.map((ln, i) => (
          <tr key={i}>
            <td><span className="mono">{ln.produkt}</span>
              {ln.krotki_opis && <div style={{ fontSize: 13, color: 'var(--muted)' }}>{ln.krotki_opis}</div>}</td>
            <td className="mono">{ln.pallets ?? ln.ilosc_pal}</td>
            <td className="mono" style={{ fontSize: 13 }}>{ln.hu_numbers}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Publiczna strona DLT (link z maila wywołania): wywołanie read-only
    (auta → pozycje → HU/ilości) + „Przygotowane" / „Wysłane". Bez logowania. */
export default function DltPage() {
  const t = useT()
  const { token } = useParams()
  const [info, setInfo] = useState<DltInfo | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(() => {
    setError('')
    api.get<DltInfo>(`/api/dlt/${token}`)
      .then(setInfo)
      .catch(err => {
        if (err instanceof ApiError && (err.status === 404 || err.status === 410)) setNotFound(true)
        else setError(errorMessage(err))
      })
  }, [token])
  useEffect(() => load(), [load])

  const act = async (path: string, doneMsg: string) => {
    setBusy(true); setError('')
    try {
      await api.post(`/api/dlt/${token}/${path}`, {})
      setDone(doneMsg)
      if (path === 'shipped') setInfo(i => i ? { ...i, status: 'wyslane_z_dlt' } : i)
      else setInfo(i => i ? { ...i, status: 'przygotowane' } : i)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (notFound) return <main className="page driver-page"><p>{t('driverLinkExpired')}</p></main>
  if (error && !info) return <main className="page driver-page"><LoadError message={error} onRetry={load} /></main>
  if (!info) return <main className="page driver-page"><p>{t('loading')}</p></main>

  const prepared = info.status === 'przygotowane'
  const shipped = info.status === 'wyslane_z_dlt'

  return (
    <main className="page driver-page">
      <div className="panel">
        <div className="driver-brand">DLT · TIMPORYE</div>
        <h1 className="mono title-token">
          {t('dltCallTitle')} {info.number}
        </h1>
        {info.needed_by && (
          <p style={{ margin: '0 0 8px' }}>
            {t('pcDeadline')}: <b className="mono">{formatDate(info.needed_by)}</b>
          </p>
        )}
        {info.notes && <p style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{info.notes}</p>}
        {info.trucks.map(truck => (
          <div key={truck.ordinal} style={{ marginTop: 10 }}>
            <h3 style={{ margin: '4px 0' }}>{t('pcTruck')} {truck.ordinal} · {truck.capacity} pal.</h3>
            <Lines lines={truck.lines} />
          </div>
        ))}
        {info.unassigned_lines.length > 0 && (
          <div style={{ marginTop: 10 }}><Lines lines={info.unassigned_lines} /></div>
        )}
      </div>

      <div className="panel">
        {shipped
          ? <p style={{ color: '#0e8a6a', fontWeight: 600, margin: 0 }}>✓ {done || t('dltShippedDone')}</p>
          : (
            <>
              {done && <p style={{ color: '#0e8a6a', fontWeight: 600 }}>✓ {done}</p>}
              {!prepared && (
                <button className="btn driver-big" disabled={busy}
                        onClick={() => act('prepared', t('dltPreparedDone'))}>
                  <PackageIcon size={14} /> {t('dltPrepared')}
                </button>
              )}
              <button className="btn driver-big" disabled={busy || !prepared}
                      style={{ marginTop: 10 }}
                      title={prepared ? undefined : t('dltPreparedFirst')}
                      onClick={() => act('shipped', t('dltShippedDone'))}>
                <TruckIcon size={14} /> {t('dltShipped')}
              </button>
            </>
          )}
        {error && <p className="error">{error}</p>}
      </div>
    </main>
  )
}
