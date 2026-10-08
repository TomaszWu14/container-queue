// Panel „Przyjęcie / porównanie" na karcie kontenera: pozycje zamówień (OrderItem)
// zestawione 3-way — zamówiono vs przyjęto vs zafakturowano + status. Tylko do odczytu:
// ilości nie wpisuje się ręcznie (decyzja 2026-09-30) — zafakturowano liczone z faktur,
// przyjęto z istniejących zapisów przyjęć (źródło automatyczne/SAP w przyszłości).
// Kolumna „Przyjęto” znika, gdy żadna pozycja jej nie ma. API: /api/containers/{id}/order-lines.
import { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import type { Container } from '../types'

interface OrderLine {
  order_number: string
  position: string
  material: string
  description: string
  ordered_qty: string
  received_qty: string
  invoiced_qty: string
  receipt_id: number | null
  status: string
  status_invoice: string
}

// status → klasa koloru komórki (ok zielony, partial bursztyn, over czerwony, none/unknown szary)
const STATUS_CLASS: Record<string, string> = {
  ok: 'ol-ok', partial: 'ol-warn', over: 'ol-over', none: 'ol-none', unknown: 'ol-none',
}

export default function OrderLinesPanel({ container }: { container: Container }) {
  const t = useT()
  const [lines, setLines] = useState<OrderLine[] | null>(null)
  const [error, setError] = useState('')
  // numer żądania: przy szybkim przełączaniu kontenerów wolna odpowiedź poprzedniego
  // nie może pokazać jego pozycji na karcie bieżącego
  const seq = useRef(0)
  const load = () => {
    const my = ++seq.current
    return api.get<OrderLine[]>(`/api/containers/${container.id}/order-lines`)
      .then(rows => {
        if (my !== seq.current) return
        setError('')
        setLines(Array.isArray(rows) ? rows : [])
      })
      .catch(err => { if (my === seq.current) setError(errorMessage(err)) })
  }
  useEffect(() => { setLines(null); setError(''); load() }, [container.id])   // eslint-disable-line react-hooks/exhaustive-deps

  // błąd pokazujemy zamiast chować panel — ukryty panel udawałby „brak pozycji"
  if (error && !lines?.length) return (
    <div className="panel order-lines">
      <h3>{t('olTitle')}</h3>
      <p className="error">{error}</p>
    </div>
  )
  if (lines === null) return null              // ładowanie — bez migotania
  if (lines.length === 0) return null          // brak pozycji zamówień → panel się nie pokazuje

  const showReceived = lines.some(l => l.received_qty)

  return (
    <div className="panel order-lines">
      <h3>{t('olTitle')}</h3>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="table-scroll">
        <table className="grid ol-grid">
          <thead>
            <tr>
              <th>{t('olOrder')}</th>
              <th>{t('olMaterial')}</th>
              <th>{t('olOrdered')}</th>
              {showReceived && <th>{t('olReceived')}</th>}
              <th>{t('olInvoiced')}</th>
            </tr>
          </thead>
          <tbody>
            {lines.map(l => (
              <tr key={`${l.order_number}|${l.position}`}>
                <td className="mono">
                  {l.order_number}{l.position && <small className="muted"> /{l.position}</small>}
                  {l.description && <div className="muted ol-desc">{l.description}</div>}
                </td>
                <td className="mono">{l.material || '—'}</td>
                <td>{l.ordered_qty || '—'}</td>
                {showReceived && (
                  <td className={STATUS_CLASS[l.status] ?? ''}>{l.received_qty || '—'}</td>
                )}
                <td className={STATUS_CLASS[l.status_invoice] ?? ''}>{l.invoiced_qty || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
