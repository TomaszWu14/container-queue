import { defineFeature } from '../feature'

// Master data → Jakość danych: reguły kontenerów bez PO / bez ETA (master_quality.py)
export default defineFeature({
  pl: {
    qContainersNoPo: 'Kontenery w obiegu bez numeru zamówienia (PO)',
    qContainersNoEta: 'Kontenery w transporcie/porcie bez ETA',
  },
  en: {
    qContainersNoPo: 'Active containers without a purchase order (PO)',
    qContainersNoEta: 'Containers in transit/port without ETA',
  },
  pt: {
    qContainersNoPo: 'Contentores ativos sem encomenda de compra (PO)',
    qContainersNoEta: 'Contentores em trânsito/porto sem ETA',
  },
})
