import { defineFeature } from '../feature'

// audyt DATA-002: lista kolejki obcięta limitem — informacja zamiast cichego gubienia rekordów
export default defineFeature({
  pl: { kqTruncated: 'Pokazano {shown} z {total} kontenerów — zawęź filtry albo pobierz eksport (zawiera wszystkie).' },
  en: { kqTruncated: 'Showing {shown} of {total} containers — narrow the filters or download the export (it has all of them).' },
  pt: { kqTruncated: 'A mostrar {shown} de {total} contentores — restrinja os filtros ou descarregue a exportação (contém todos).' },
})
