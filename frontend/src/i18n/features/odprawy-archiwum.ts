import { defineFeature } from '../feature'

// audyt PERF-003: tablica odpraw domyślnie bez zrealizowanych kontenerów
export default defineFeature({
  pl: { customsArchive: 'Archiwum (zrealizowane)', customsArchiveHint: 'Pokaż odprawy kontenerów już zrealizowanych — od najnowszych',
    poTruncated: 'Pokazano {shown} z {total} zamówień (najnowsze) — wpisz numer, aby znaleźć starsze.' },
  en: { customsArchive: 'Archive (completed)', customsArchiveHint: 'Show clearances of completed containers — newest first',
    poTruncated: 'Showing {shown} of {total} orders (newest) — type a number to find older ones.' },
  pt: { customsArchive: 'Arquivo (concluídos)', customsArchiveHint: 'Mostrar desalfandegamentos de contentores concluídos — mais recentes primeiro',
    poTruncated: 'A mostrar {shown} de {total} encomendas (mais recentes) — escreva o número para encontrar as antigas.' },
})
