import { defineFeature } from '../feature'

// ARCH-004: faktury przetwarzane w tle (cięcie, OCR, ekstrakcja) — lista odświeża się sama
export default defineFeature({
  pl: { invProcessingInBackground: 'Przetwarzanie w tle (cięcie, OCR, odczyt pozycji) — lista odświeży się sama.' },
  en: { invProcessingInBackground: 'Processing in the background (split, OCR, line items) — the list refreshes automatically.' },
  pt: { invProcessingInBackground: 'Processamento em segundo plano (divisão, OCR, itens) — a lista atualiza-se sozinha.' },
})
