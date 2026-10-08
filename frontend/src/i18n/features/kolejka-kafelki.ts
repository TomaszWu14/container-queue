// Mini-kafelki dokumentów w kolejce + zakładki „Braki dokumentów” / „Czeka w poczekalni”
// (pages/queue/docTiles.tsx, spec 2026-10-06-dokumenty-dostaw decyzja 28)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    kqColDocs: 'Dokumenty', kqDocSad: 'SAD (draft → PZ → PW)',
    kqDocIntake: '{n} części czeka w poczekalni na potwierdzenie',
    kqView_docsMissing: 'Braki dokumentów', kqView_intake: 'Czeka w poczekalni',
  },
  en: {
    kqColDocs: 'Documents', kqDocSad: 'SAD (draft → PZ → PW)',
    kqDocIntake: '{n} parts waiting for confirmation in the intake',
    kqView_docsMissing: 'Missing documents', kqView_intake: 'Waiting in intake',
  },
  pt: {
    kqColDocs: 'Documentos', kqDocSad: 'SAD (rascunho → PZ → PW)',
    kqDocIntake: '{n} partes aguardam confirmação na sala de espera',
    kqView_docsMissing: 'Documentos em falta', kqView_intake: 'Na sala de espera',
  },
})
