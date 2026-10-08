import { defineFeature } from '../feature'

// Wybór pliku w języku aplikacji zamiast natywnego „Choose File / No file chosen” (audyt UI B24)
export default defineFeature({
  pl: { filePick: 'Wybierz plik', fileNone: 'Nie wybrano pliku' },
  en: { filePick: 'Choose file', fileNone: 'No file chosen' },
  pt: { filePick: 'Escolher ficheiro', fileNone: 'Nenhum ficheiro escolhido' },
})
