import { XIcon } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import type { Container } from '../types'
import { formatDate, formatNum } from '../dates'
import { useConfirm } from '../ConfirmDialog'

interface OrderItem {
  id: number
  order_number: string
  position: string
  material: string
  description: string
  quantity: string
  unit: string
  net_weight: string
  gross_weight: string
  volume: string
  volume_unit: string
  planned_ship_date: string | null
  computed_volume_m3: number | null
}

interface SentLink {
  id: number
  sent_number: string
  order_number: string
  note: string
}

export function ItemsPanel({ container }: { container: Container }) {
  const t = useT()
  const [items, setItems] = useState<OrderItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
    api.get<OrderItem[]>(`/api/containers/${container.id}/items`)
      .then(setItems).catch(err => setError(errorMessage(err)))
  }, [container.id])

  // błąd ładowania pokazujemy (nie mylimy z „brak pozycji"); pusta lista = panel ukryty
  if (error) return <div className="panel"><p className="error">{t('refContents')}: {error}</p></div>
  if (items.length === 0) return null

  const sum = (key: 'net_weight' | 'gross_weight' | 'volume') =>
    items.reduce((acc, item) => acc + (parseFloat(item[key]) || 0), 0)
  const sumMarm = items.reduce((acc, item) => acc + (item.computed_volume_m3 ?? 0), 0)
  const hasMarm = items.some(item => item.computed_volume_m3 != null)

  return (
    <div className="panel">
      <h3>{t('refContents')} ({items.length})</h3>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid">
          <thead>
            <tr>
              <th>{t('order')}</th><th>{t('refPos')}</th><th>REF</th>
              <th>{t('refDesc')}</th><th>{t('refQty')}</th>
              <th>{t('refNet')}</th><th>{t('refGross')}</th><th>{t('refVolume')}</th>
              {hasMarm && <th>{t('refVolumeMarm')}</th>}
              <th>{t('refShipDate')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}>
                <td className="mono">{item.order_number}</td>
                <td>{item.position}</td>
                <td className="mono">{item.material}</td>
                <td>{item.description}</td>
                <td>{formatNum(parseFloat(item.quantity), 2)} {item.unit}</td>
                <td>{formatNum(parseFloat(item.net_weight), 2)}</td>
                <td>{formatNum(parseFloat(item.gross_weight), 2)}</td>
                <td>{formatNum(parseFloat(item.volume), 2)} {item.volume_unit}</td>
                {hasMarm && (
                  <td>{item.computed_volume_m3 != null
                    ? `${formatNum(item.computed_volume_m3, 3)} m³` : '—'}</td>
                )}
                <td>{item.planned_ship_date && formatDate(item.planned_ship_date)}</td>
              </tr>
            ))}
            <tr style={{ fontWeight: 700, background: '#fafbfd' }}>
              <td colSpan={5}>{t('sumLbl')}</td>
              <td>{formatNum(sum('net_weight'), 2)}</td>
              <td>{formatNum(sum('gross_weight'), 2)}</td>
              <td>{formatNum(sum('volume'), 2)}</td>
              {hasMarm && <td>{formatNum(sumMarm, 3)} m³</td>}
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function SentLinksPanel({ container }: { container: Container }) {
  const t = useT()
  const { confirm } = useConfirm()
  const user = useUser()
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  // GET /sent-links = CommercialReaders: magazyn i agencja nie wołają API (audyt UI S10)
  const canRead = user?.role !== 'warehouse' && user?.role !== 'customs'
  const [links, setLinks] = useState<SentLink[]>([])
  const [orderNumber, setOrderNumber] = useState('')
  const [sentNumber, setSentNumber] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const fromText: string[] = container.order_numbers?.match(/\d{4,}/g) ?? []
  const orders = [...new Set(
    container.order_number ? [...fromText, container.order_number] : fromText)]

  const load = useCallback(() => {
    if (!canRead) return
    api.get<SentLink[]>(`/api/containers/${container.id}/sent-links`)
      .then(setLinks).catch(() => {})
  }, [container.id, canRead])
  useEffect(() => load(), [load])

  const add = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post(`/api/containers/${container.id}/sent-links`, {
        sent_number: sentNumber, order_number: orderNumber || orders[0],
      })
      setSentNumber('')
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number, sentNo: string) => {
    if (busy) return
    if (!(await confirm(`${t('confirmDeleteEntry')} „${sentNo}"?`, { danger: true }))) return
    // wspólny klient: sprawdza response.ok i odświeża sesję (bez cichej porażki DELETE)
    setBusy(true)
    try {
      await api.del(`/api/sent-links/${id}`)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (!canRead || (!canEdit && links.length === 0)) return null

  return (
    <div className="panel">
      <h3>{t('sentLinks')}</h3>
      {links.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('sentLinksEmpty')}</p>}
      {links.length > 0 && (
        <table className="grid">
          <thead>
            <tr><th>{t('sentLbl')}</th><th>{t('order')}</th><th></th></tr>
          </thead>
          <tbody>
            {links.map(link => (
              <tr key={link.id}>
                <td className="mono">{link.sent_number}</td>
                <td className="mono">{link.order_number}</td>
                <td>
                  {canEdit && (
                    <button className="btn small secondary" disabled={busy}
                            aria-label={t('delete')} onClick={() => remove(link.id, link.sent_number)}><XIcon size={14} /></button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && orders.length > 0 && (
        <form className="row" onSubmit={add} style={{ marginTop: 10 }}>
          <input aria-label={t('sentNumberLbl')} placeholder={t('sentNumberLbl')} value={sentNumber} required
                 onChange={e => setSentNumber(e.target.value)} style={{ flex: 1 }} />
          <select aria-label={t('order')} value={orderNumber} onChange={e => setOrderNumber(e.target.value)}>
            {orders.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <button className="btn small" disabled={busy}>{t('add')}</button>
        </form>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
