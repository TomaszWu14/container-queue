import { defineFeature } from '../feature'

// Master data → Zamówienia SAP: lista z limitem (X-Total-Count) — informacja zamiast cichego obcięcia
export default defineFeature({
  pl: { sapPoTruncated: 'Pokazano {shown} z {total} zamówień — zawęź wyszukiwanie, spółkę albo daty.' },
  en: { sapPoTruncated: 'Showing {shown} of {total} orders — narrow the search, company or dates.' },
  pt: { sapPoTruncated: 'A mostrar {shown} de {total} encomendas — restrinja a pesquisa, a empresa ou as datas.' },
})
