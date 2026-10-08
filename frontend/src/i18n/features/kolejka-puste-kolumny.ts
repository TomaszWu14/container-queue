import { defineFeature } from '../feature'

// Kolejka: kolumny puste w całej widocznej tabeli są ukryte — stopka mówi które (UX-022)
export default defineFeature({
  pl: { kqHiddenEmptyCols: 'Puste kolumny ukryte: {cols}' },
  en: { kqHiddenEmptyCols: 'Empty columns hidden: {cols}' },
  pt: { kqHiddenEmptyCols: 'Colunas vazias ocultas: {cols}' },
})
