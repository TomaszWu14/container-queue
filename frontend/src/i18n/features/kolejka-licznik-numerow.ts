// Licznik „› N” w komórkach wielu numerów (PO, nr dostaw) + „rozwiń wszystkie” w nagłówku
// kolumny (pages/queue/cells.tsx MultiCell, EnterpriseTable.tsx), 2026-10-01
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { expandAllValues: 'Rozwiń wszystkie numery w kolumnie', collapseAllValues: 'Zwiń wszystkie numery w kolumnie' },
  en: { expandAllValues: 'Expand all numbers in the column', collapseAllValues: 'Collapse all numbers in the column' },
  pt: { expandAllValues: 'Expandir todos os números da coluna', collapseAllValues: 'Recolher todos os números da coluna' },
})
