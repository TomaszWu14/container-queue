import { defineFeature } from '../feature'

// Etykiety pól dla czytników ekranu (audyt UI S1) — tam, gdzie widoczny tekst nie nazywa pola
export default defineFeature({
  pl: { fieldFile: 'Plik', fieldMonth: 'Miesiąc', fieldCustomer: 'Klient', fieldSelectRow: 'Zaznacz wiersz' },
  en: { fieldFile: 'File', fieldMonth: 'Month', fieldCustomer: 'Customer', fieldSelectRow: 'Select row' },
  pt: { fieldFile: 'Ficheiro', fieldMonth: 'Mês', fieldCustomer: 'Cliente', fieldSelectRow: 'Selecionar linha' },
})
