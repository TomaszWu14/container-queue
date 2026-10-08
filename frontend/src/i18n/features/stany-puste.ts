import { defineFeature } from '../feature'

// Stany i komunikaty (audyt UI A24, B22): oś zdarzeń — okno wolnych dni w formacie aplikacji;
// Analityka — puste wykresy i listy mówią, że brak danych, zamiast zostawiać pustkę
export default defineFeature({
  pl: {
    ctFreeFrom: 'od {date}', ctFreeDays: '+ {n} dni', ctFreeDays_one: '+ {n} dzień',
    anThroughputEmpty: 'Brak dostarczonych kontenerów w tym okresie.',
    anSuppliersEmpty: 'Brak danych o dostawcach.', anWarehousesEmpty: 'Brak danych o magazynach.',
  },
  en: {
    ctFreeFrom: 'from {date}', ctFreeDays: '+ {n} days', ctFreeDays_one: '+ {n} day',
    anThroughputEmpty: 'No containers delivered in this period.',
    anSuppliersEmpty: 'No supplier data.', anWarehousesEmpty: 'No warehouse data.',
  },
  pt: {
    ctFreeFrom: 'desde {date}', ctFreeDays: '+ {n} dias', ctFreeDays_one: '+ {n} dia',
    anThroughputEmpty: 'Nenhum contentor entregue neste período.',
    anSuppliersEmpty: 'Sem dados de fornecedores.', anWarehousesEmpty: 'Sem dados de armazéns.',
  },
})
