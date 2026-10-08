import { defineFeature } from '../feature'

// Wywołania DLT: jeden baner zamiast surowego „POWERBI_PROVIDER=off” (audyt UI B19)
export default defineFeature({
  pl: { pcPbiOff: 'Integracja Power BI jest wyłączona — dane stanów DLT są niedostępne. Skontaktuj się z administratorem.' },
  en: { pcPbiOff: 'Power BI integration is turned off — DLT stock data is unavailable. Contact your administrator.' },
  pt: { pcPbiOff: 'A integração Power BI está desativada — os dados de stock DLT não estão disponíveis. Contacte o administrador.' },
})
