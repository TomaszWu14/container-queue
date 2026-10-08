import { ClipboardListIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useUser } from '../App'
import { api } from '../api'
import { formatDate } from '../dates'
import { useT } from '../i18n'

// Zamówienia zakupowe (ETD) bez kontenera — wczesny etap kolejki. Zwijana sekcja
// nad tabelą kolejki; pusta lista → nic nie renderuje.
interface PurchaseOrder {
  id: number
  order_no: string
  supplier: string
  products: string
  cbm: number | null
  container_type: string
  etd: string | null
  ready_date: string
  port_of_departure: string
  forwarder: string
}

// role z dostępem do GET /api/purchase-orders (PurchasingReaders) — spedytor, magazyn
// i agencja nie widzą panelu i nie wołają API (audyt UI S10)
const PO_ROLES = ['admin', 'logistics', 'purchasing']

export default function PurchaseOrdersPanel({ companyCode }: { companyCode: string }) {
  const t = useT()
  const allowed = PO_ROLES.includes(useUser()?.role ?? '')
  const [orders, setOrders] = useState<PurchaseOrder[]>([])

  useEffect(() => {
    if (!companyCode || !allowed) { setOrders([]); return }
    api.get<PurchaseOrder[]>(`/api/purchase-orders?company_code=${encodeURIComponent(companyCode)}`)
      .then(setOrders).catch(() => setOrders([]))
  }, [companyCode, allowed])

  if (orders.length === 0) return null

  return (
    <details className="panel po-panel" open>
      <summary className="po-summary">
        <ClipboardListIcon size={14} /> {t('etdSection')} <span className="badge st-W_TRANSPORCIE">{orders.length}</span>
        <span className="po-hint">{t('etdSectionHint')}</span>
      </summary>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid" style={{ minWidth: 720 }}>
          <thead>
            <tr>
              <th>{t('order')}</th><th>{t('supplier')}</th><th>{t('poProducts')}</th>
              <th>{t('poEtd')}</th><th>{t('poType')}</th><th>{t('poCbm')}</th>
              <th>{t('poReady')}</th><th>{t('forwarder')}</th>
            </tr>
          </thead>
          <tbody>
            {orders.map(o => (
              <tr key={o.id}>
                <td className="mono">{o.order_no}</td>
                <td>{o.supplier}</td>
                <td>{o.products}</td>
                <td>{formatDate(o.etd ?? '')}</td>
                <td>{o.container_type}</td>
                <td>{o.cbm ?? ''}</td>
                <td>{formatDate(o.ready_date)}</td>
                <td>{o.forwarder}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
