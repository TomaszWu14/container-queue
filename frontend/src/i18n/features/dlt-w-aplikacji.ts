import { defineFeature } from '../feature'

// Magazyn DLT (konto, rola warehouse) potwierdza wywołanie w aplikacji zamiast linku z maila (2026-10-07)
export default defineFeature({
  pl: {
    pcStatus_przygotowane: 'Przygotowane w DLT', pcStatus_wyslane_z_dlt: 'Wysłane z DLT',
    pcMarkPrepared: 'Przygotowane', pcMarkShipped: 'Wysłane z DLT',
  },
  en: {
    pcStatus_przygotowane: 'Prepared at DLT', pcStatus_wyslane_z_dlt: 'Shipped from DLT',
    pcMarkPrepared: 'Prepared', pcMarkShipped: 'Shipped from DLT',
  },
  pt: {
    pcStatus_przygotowane: 'Preparado no DLT', pcStatus_wyslane_z_dlt: 'Enviado do DLT',
    pcMarkPrepared: 'Preparado', pcMarkShipped: 'Enviado do DLT',
  },
})
