import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import type { Container } from '../types'
import { ComplaintsPanel } from './ComplaintsPanel'
import { LoadError, Skeleton } from '../feedback'
import { formatDate } from '../dates'

// Widok konta zewnętrznego magazynu (np. DLT): uproszczona kolejka dostaw z numerem
// kontenera, datą dostawy i szczegółami do rozładunku + zgłaszanie reklamacji.
// Dane handlowe (dostawca, spedytor, zamówienia) są maskowane po stronie API.

function deliveryDate(c: Container): string | null {
  return c.notify_date  // data dostawy u DLT = data awizacji rozładunku
}

// C28: kompaktowy wiersz tabeli (jak kolejka innych ról) — cały wiersz klikalny, przycisk secondary;
// szczegóły do rozładunku i reklamacje w rozwinięciu pod wierszem
function WarehouseRow({ c }: { c: Container }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <Fragment>
      <tr className="clickable" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <td className="mono"><b>{c.container_no}</b></td>
        <td><span className={`badge st-${c.status}`}>{t(`st_${c.status}`)}</span></td>
        <td>{formatDate(deliveryDate(c))}</td>
        <td>{c.warehouse_name || '—'}</td>
        <td className="hide-sm">{c.container_size || '—'}</td>
        <td className="hide-sm num">{c.pallet_count ?? '—'}</td>
        <td>
          <button type="button" className="btn small secondary"
                  onClick={e => { e.stopPropagation(); setOpen(o => !o) }}>
            {open ? t('whHideDetails') : t('whShowDetails')}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="wh-detail">
          <td colSpan={7}>
            <div className="form-grid">
              <div>
                <div className="muted" style={{ fontSize: 13 }}>{t('whMaterials')}</div>
                <p className="pre" style={{ margin: 0 }}>{c.materials_list || '—'}</p>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 13 }}>{t('whPalletization')}</div>
                <p className="pre" style={{ margin: 0 }}>{c.palletization_note || '—'}</p>
              </div>
            </div>
            <ComplaintsPanel container={c} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}

export default function WarehouseQueuePage() {
  const t = useT()
  const [containers, setContainers] = useState<Container[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api.get<Container[]>('/api/containers')
      .then(setContainers)
      .catch(err => { setContainers([]); setError(errorMessage(err)) })
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => load(), [load])

  const sorted = [...containers].sort((a, b) => {
    const da = deliveryDate(a) ?? '9999'
    const db = deliveryDate(b) ?? '9999'
    return da.localeCompare(db)
  })

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>{t('whDeliveries')}</h1>
      </div>
      {loading && sorted.length === 0 && <Skeleton rows={4} />}
      {!loading && error && sorted.length === 0 && <LoadError message={error} onRetry={load} />}
      {!loading && !error && sorted.length === 0 && <p className="muted">{t('whNoDeliveries')}</p>}
      {sorted.length > 0 && (
        <div className="panel p0">
          <div className="table-scroll">
            <table className="grid wh-table">
              <thead>
                <tr>
                  <th>{t('containerNo')}</th><th>{t('status')}</th><th>{t('deliveryDate')}</th>
                  <th>{t('warehouse')}</th><th className="hide-sm">{t('size')}</th>
                  <th className="hide-sm">{t('whPallets')}</th><th>{t('actions')}</th>
                </tr>
              </thead>
              <tbody>{sorted.map(c => <WarehouseRow key={c.id} c={c} />)}</tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  )
}
