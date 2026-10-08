import { defineFeature } from '../feature'

// Instancja portfolio: podpowiedź konta demo na ekranie logowania (tylko podgląd)
export default defineFeature({
  pl: { demoLoginHint: 'Konto demo (tylko podgląd)' },
  en: { demoLoginHint: 'Demo account (read-only)' },
  pt: { demoLoginHint: 'Conta de demonstração (só leitura)' },
})
