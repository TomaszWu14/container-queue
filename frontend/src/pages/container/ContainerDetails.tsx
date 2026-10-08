import { AnchorIcon, TriangleAlertIcon } from 'lucide-react'
// Zakładka „Szczegóły” pełnej karty (2026-09-30): wszystko z dawnej karty poza dokumentami,
// wiadomościami i historią — pola nagłówkowe, śledzenie, zlecenia/odprawa/kierowca, pozycje,
// zamówienie, pakowanie, klient, zakupy, obserwujący, reklamacje, checklista, linki SENT.
// Siatka paneli: 1 kolumna na telefonie, 2–3 na szerokim ekranie (fullCard.css).
import { Suspense, lazy, useState } from 'react'
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../../App'
import { api } from '../../api'
import { CustomsAgencyPanel, DriverPanel, TransportOrdersPanel } from '../../collaboration'
import { CustomsBadge, DocumentBadge, PurchasingBadge, StatusBadge } from '../../components'
import { formatDate, parseServerTs } from '../../dates'
import { useT } from '../../i18n'
import { canAccess, seesCustoms } from '../../routing'
import { TransportBadge } from '../../TransportBadge'
import type { Container } from '../../types'
import { ChecklistPanel } from '../ChecklistPanel'
import { ComplaintsPanel } from '../ComplaintsPanel'
import { ItemsPanel, SentLinksPanel } from '../ContainerItems'
import { CustomerPortalPanel, PurchasingPanel, TransitCustomerPanel } from '../ContainerSidePanels'
import OrderLinesPanel from '../OrderLinesPanel'
import ContainerTimeline from '../tracking/ContainerTimeline'
import VesselMiniMap from '../tracking/VesselMiniMap'
import WatchersPanel from '../watch/WatchersPanel'
// leniwie: three.js (scena 3D wypełnienia) nie może wejść do głównego chunku
const ContainerPackingPanel = lazy(() => import('../ContainerPacking'))

// 0 to poprawna wartość (np. 0 dni demurrage) — pustką jest tylko null/undefined/''/false
const isEmpty = (value: ReactNode) => value === null || value === undefined || value === '' || value === false

export default function ContainerDetails({ container, setContainer, load, vesselNearPort }: {
  container: Container
  setContainer: Dispatch<SetStateAction<Container | null>>
  load: () => void
  vesselNearPort: string
}) {
  const t = useT()
  const user = useUser()
  const navigate = useNavigate()
  const [showEmpty, setShowEmpty] = useState(false)   // A26: puste pola nagłówka zwinięte

  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const isWarehouse = user?.role === 'warehouse'
  const isForwarder = user?.role === 'forwarder'
  const isCustoms = user?.role === 'customs'
  const isPurchasing = user?.role === 'purchasing'
  // sprzedaż: tylko odczyt — nagłówek, oś czasu, zawartość REF; bez paneli z API zamkniętym dla roli
  const isSales = user?.role === 'sales'

  const item = (label: string, value: ReactNode) => (
    <div className="item" key={label}><b>{label}</b>{isEmpty(value) ? '—' : value}</div>
  )
  // A26: kolejność — status, ETA, awizacja, magazyn, dostawca, potem reszta (stała na każdej szerokości)
  const csDays = (container.customs_status === 'ZLECONA' || container.customs_status === 'REWIZJA')
    && container.customs_assigned_at
    && t('customsDaysOpen').replace('{n}', String(Math.max(0, Math.floor(
      (Date.now() - parseServerTs(container.customs_assigned_at).getTime()) / 86400000))))
  const fields = ([
    [t('status'), <StatusBadge status={container.status} />],
    [t('eta'), container.eta && formatDate(container.eta)],
    [t('notifyDate'), container.notify_date && formatDate(container.notify_date)],
    [t('warehouse'), container.warehouse_name],
    [t('supplier'), container.supplier_name],
    seesCustoms(user?.role) && [t('customs'), <CustomsBadge status={container.customs_status} />],
    csDays && [t('csTerm'), csDays],
    [t('purchasing'), <PurchasingBadge status={container.purchasing_status} />],
    [t('company'), container.company_name],
    // link tylko dla ról z dostępem do /zamowienia (spedytor/agencja dostałyby 403)
    [t('order'), container.order_id && user && canAccess(user.role, 'zamowienia')
      ? <a href={`/zamowienia/${container.order_id}`}
           onClick={e => { e.preventDefault(); navigate(`/zamowienia/${container.order_id}`) }}>
          {container.order_number}
        </a>
      : container.order_number],
    [t('atd'), container.atd && formatDate(container.atd)],
    [t('forwarder'), container.forwarder_name],
    [t('port'), container.port_name],
    [t('vessel'), container.vessel],
    [t('transport'), container.transport_type && <TransportBadge type={container.transport_type} size="md" />],
    [t('onCarriage'), container.on_carriage && <TransportBadge type={container.on_carriage} size="md" />],
    [t('size'), container.container_size],
    [t('documentStatus'), <DocumentBadge status={container.document_status} />],
    [t('documents'), container.documents_ok ? t('yes') : t('no')],
    // A25: źródło prawdy = słownik (customs_agency_id); wolny tekst tylko dla starych danych
    [t('customsAgency'), container.customs_agency_name || container.customs_agency],
    [t('demurrage'), container.demurrage_free_days],
    [t('incomingDeliveryNo'), container.incoming_delivery_no],
    [t('rfNumber'), container.rf_number],
    [t('notes'), container.notes],
  ] as ([string, ReactNode] | false | null | undefined | '')[])
    .filter((f): f is [string, ReactNode] => !!f)
  const emptyCount = fields.filter(([, v]) => isEmpty(v)).length

  return (
    <div className="ct-details">
      <section className="panel ct-wide" aria-label={t('details')}>
        {/* A26: kluczowe pola zawsze na początku; puste zwinięte za „Pokaż puste pola (N)” */}
        <div className="detail-grid">
          {fields.filter(([, v]) => showEmpty || !isEmpty(v)).map(([label, v]) => item(label, v))}
        </div>
        {emptyCount > 0 && (
          <button type="button" className="detail-toggle" onClick={() => setShowEmpty(e => !e)}>
            {showEmpty ? t('ctHideEmpty') : t('ctShowEmpty').replace('{n}', String(emptyCount))}
          </button>
        )}
      </section>

      <div className="panel ct-wide">
        <h3 style={{ margin: 0 }}>{t('tracking')}</h3>
        {vesselNearPort && container.status === 'W_TRANSPORCIE' && canEdit && (
          <div className="suggest-bar">
            <AnchorIcon size={14} /> {t('suggestInPort')} <b>{vesselNearPort}</b>
            <button className="btn small" style={{ marginLeft: 10 }}
                    onClick={() => api.post<Container>(`/api/containers/${container.id}/status`,
                      { status: 'W_PORCIE' }).then(c => setContainer(c)).catch(() => {})}>
              {t('suggestSetInPort')}
            </button>
          </div>
        )}
        {container.vessel_mismatch && (
          <p className="error" style={{ marginTop: 6 }}><TriangleAlertIcon size={14} /> {t('transshipmentWarn')}</p>
        )}
        <ContainerTimeline containerId={container.id} />
        {container.vessel && <VesselMiniMap vesselName={container.vessel} />}
      </div>

      {/* kotwica #akcja-avizo bez zmian (deep-linki z Wieży) */}
      {!isCustoms && !isSales && <TransportOrdersPanel container={container} />}
      {(canEdit || isCustoms) && <CustomsAgencyPanel container={container} onSaved={load} />}
      {(canEdit || isForwarder) && <div id="akcja-avizo"><DriverPanel container={container} onSaved={load} /></div>}
      {isWarehouse && <div id="akcja-avizo"><DriverPanel container={container} onSaved={load} readOnly /></div>}
      {container.is_transit && (
        <TransitCustomerPanel container={container} canEdit={canEdit}
          onSaved={updated => setContainer(updated)} />
      )}
      {canEdit && (
        <CustomerPortalPanel container={container}
          onSaved={updated => setContainer(updated)} />
      )}
      {(canEdit || isPurchasing) && <PurchasingPanel container={container} onSaved={load} />}
      <WatchersPanel baseUrl={`/api/containers/${container.id}`} />
      {!isCustoms && !isSales && <ComplaintsPanel container={container} />}
      {!isCustoms && !isSales && <ChecklistPanel containerId={container.id} editable={false} framed />}
      {!isCustoms && !isSales && <SentLinksPanel container={container} />}
      {!isCustoms && <div className="ct-wide"><ItemsPanel container={container} /></div>}
      {!isCustoms && !isSales && (
        <div className="ct-wide">
          <OrderLinesPanel container={container} />
        </div>
      )}
      {!isCustoms && !isWarehouse && !isSales && (
        <div className="ct-wide">
          <Suspense fallback={null}>
            <ContainerPackingPanel containerId={container.id} />
          </Suspense>
        </div>
      )}
    </div>
  )
}
