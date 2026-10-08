// Zamówienie SAP z faktury bez kontenera — podpowiedź zamiast cichego przypięcia
// (InvoiceReviewModal.tsx, spec 2026-10-01-bramka-dokument-dostawa, PR 1)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    invOrdersToLink: 'Zamówienie z faktury bez kontenera: {v}',
    invLinkOrders: 'Przypnij do tego kontenera',
  },
  en: {
    invOrdersToLink: 'Order on the invoice has no container: {v}',
    invLinkOrders: 'Link to this container',
  },
  pt: {
    invOrdersToLink: 'Pedido da fatura sem contentor: {v}',
    invLinkOrders: 'Associar a este contentor',
  },
})
