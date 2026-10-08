import { defineFeature } from '../feature'

// Raport błędnych wierszy importów SAP (REF/EKPO, MARM) — DATA-003
export default defineFeature({
  pl: { importRowErrors: 'Wiersze pominięte — popraw w pliku ({n})', importErrRow: 'wiersz' },
  en: { importRowErrors: 'Skipped rows — fix them in the file ({n})', importErrRow: 'row' },
  pt: { importRowErrors: 'Linhas ignoradas — corrija no ficheiro ({n})', importErrRow: 'linha' },
})
