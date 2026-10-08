// Wymagane dokumenty per dostawca (RequiredDocsEditor.tsx, spec 2026-10-06 decyzja 16)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    rqdTitle: 'Wymagane dokumenty',
    rqdHint: 'Których kafelków brak jest „brakiem” u tego dostawcy (od etapu, na którym dokument powinien już być).',
    rqdDefault: 'domyślne', rqdCustom: 'własny zestaw',
    rqdSave: 'Zapisz wymagane', rqdReset: 'Przywróć domyślne', rqdSaved: 'Zapisano wymagane dokumenty',
  },
  en: {
    rqdTitle: 'Required documents',
    rqdHint: 'Which tiles count as missing for this supplier (from the stage the document is due).',
    rqdDefault: 'default', rqdCustom: 'custom set',
    rqdSave: 'Save required', rqdReset: 'Restore default', rqdSaved: 'Required documents saved',
  },
  pt: {
    rqdTitle: 'Documentos obrigatórios',
    rqdHint: 'Que mosaicos contam como em falta para este fornecedor (a partir da etapa em que o documento é devido).',
    rqdDefault: 'predefinido', rqdCustom: 'conjunto próprio',
    rqdSave: 'Guardar obrigatórios', rqdReset: 'Repor predefinição', rqdSaved: 'Documentos obrigatórios guardados',
  },
})
