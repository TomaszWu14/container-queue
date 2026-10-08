import { defineFeature } from '../feature'

// kolejka: filtry w nagłówkach kolumn „jak w Excelu" (lista unikalnych wartości z licznikami)
export default defineFeature({
  pl: {
    cfFilterBy: 'Filtruj', cfSearch: 'Szukaj', cfSelectAll: '(Zaznacz wszystko)', cfEmpty: '(Puste)',
    cfOk: 'OK', cfCancel: 'Anuluj', cfClear: 'Wyczyść filtr', cfExcept: 'oprócz',
    cfMore: 'Pokazano {n} z {m} — zawęź wyszukiwaniem', cfNone: 'Brak wartości',
  },
  en: {
    cfFilterBy: 'Filter', cfSearch: 'Search', cfSelectAll: '(Select all)', cfEmpty: '(Blanks)',
    cfOk: 'OK', cfCancel: 'Cancel', cfClear: 'Clear filter', cfExcept: 'except',
    cfMore: 'Showing {n} of {m} — narrow with search', cfNone: 'No values',
  },
  pt: {
    cfFilterBy: 'Filtrar', cfSearch: 'Pesquisar', cfSelectAll: '(Selecionar tudo)', cfEmpty: '(Vazias)',
    cfOk: 'OK', cfCancel: 'Cancelar', cfClear: 'Limpar filtro', cfExcept: 'exceto',
    cfMore: 'A mostrar {n} de {m} — restrinja com a pesquisa', cfNone: 'Sem valores',
  },
})
