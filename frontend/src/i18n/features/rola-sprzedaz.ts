import { defineFeature } from '../feature'

// Rola „sprzedaż” (2026-09-27): tylko odczyt kolejki, karty, kalendarza, śledzenia, Specjalnej troski
export default defineFeature({
  pl: { roleName_sales: 'Sprzedaż', careReadOnlyHint: 'Podgląd — zamówienia dodaje i edytuje logistyka.' },
  en: { roleName_sales: 'Sales', careReadOnlyHint: 'View only — orders are added and edited by logistics.' },
  pt: { roleName_sales: 'Vendas', careReadOnlyHint: 'Só leitura — as encomendas são criadas e editadas pela logística.' },
})
