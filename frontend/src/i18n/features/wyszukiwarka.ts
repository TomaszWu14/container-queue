// Globalna wyszukiwarka — podpowiedzi
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    sugContainer: 'Kontener',
    sugPo: 'PO',
    sugVessel: 'Statek',
    sugSupplier: 'Dostawca',
    sugNone: 'Brak wyników dla „{q}”',
    searchTrimmed: 'Skrócono do {n} znaków',
  },
  en: {
    sugContainer: 'Container',
    sugPo: 'PO',
    sugVessel: 'Vessel',
    sugSupplier: 'Supplier',
    sugNone: 'No results for “{q}”',
    searchTrimmed: 'Shortened to {n} characters',
  },
  pt: {
    sugContainer: 'Contentor',
    sugPo: 'PO',
    sugVessel: 'Navio',
    sugSupplier: 'Fornecedor',
    sugNone: 'Sem resultados para “{q}”',
    searchTrimmed: 'Encurtado para {n} caracteres',
  },
})
