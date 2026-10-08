// Odchudzenie kolejki: 2 wiersze nad tabelą (firmy + szukaj + akcje; widoki + filtry),
// menu Widok (gęstość + kolumny), przełącznik edycji, nagłówki grup w jednej linii
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    kqCompanies: 'Spółki', kqView: 'Widok', kqViewHint: 'Widok — gęstość i kolumny',
    kqDensityCompact: 'Kompaktowy', kqDensityComfort: 'Komfortowy',
    kqEdit: 'Edycja', kqEditOnHint: 'Edycja włączona — przeciągaj kontenery na dni',
    kqEditOffHint: 'Edycja wyłączona — kliknij, aby przeciągać kontenery na dni',
    kqAdd: 'Dodaj', kqContShort: '{n} kont.', kqSelectRow: 'Zaznacz kontener',
  },
  en: {
    kqCompanies: 'Companies', kqView: 'View', kqViewHint: 'View — density and columns',
    kqDensityCompact: 'Compact', kqDensityComfort: 'Comfortable',
    kqEdit: 'Editing', kqEditOnHint: 'Editing on — drag containers onto days',
    kqEditOffHint: 'Editing off — click to drag containers onto days',
    kqAdd: 'Add', kqContShort: '{n} cont.', kqSelectRow: 'Select container',
  },
  pt: {
    kqCompanies: 'Empresas', kqView: 'Vista', kqViewHint: 'Vista — densidade e colunas',
    kqDensityCompact: 'Compacta', kqDensityComfort: 'Confortável',
    kqEdit: 'Edição', kqEditOnHint: 'Edição ativa — arraste contentores para os dias',
    kqEditOffHint: 'Edição desativada — clique para arrastar contentores para os dias',
    kqAdd: 'Adicionar', kqContShort: '{n} cont.', kqSelectRow: 'Selecionar contentor',
  },
})
