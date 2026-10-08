import { defineFeature } from '../feature'

// podgląd importu z 0 zmian — powód zamiast samego zablokowanego „Importuj (0)”
export default defineFeature({
  pl: {
    importNoChanges: 'Brak zmian względem ostatniego importu i stanu w aplikacji — nie ma czego importować.',
    queueSkippedOldHint: 'Wiersze z rozładunkiem przed {date} są pominięte — wyczyść albo cofnij datę, żeby je sprawdzić.',
  },
  en: {
    importNoChanges: 'No changes compared with the last import and the app — nothing to import.',
    queueSkippedOldHint: 'Rows unloaded before {date} are skipped — clear or move the date back to check them.',
  },
  pt: {
    importNoChanges: 'Sem alterações face à última importação e ao estado da aplicação — nada a importar.',
    queueSkippedOldHint: 'Linhas com descarga antes de {date} são ignoradas — limpe ou recue a data para as verificar.',
  },
})
