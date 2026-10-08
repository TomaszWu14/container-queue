import { defineFeature } from '../feature'

// Logistyka akceptuje zlecenie transportowe w imieniu spedytora — z notatką (2026-09-28)
export default defineFeature({
  pl: { acceptOnBehalf: 'Zaakceptuj za spedytora', acceptOnBehalfPrompt: 'Dlaczego akceptujesz w imieniu spedytora? (np. potwierdził telefonicznie)', acceptOnBehalfNoteRequired: 'Akceptacja w imieniu spedytora wymaga notatki.' },
  en: { acceptOnBehalf: 'Accept for forwarder', acceptOnBehalfPrompt: 'Why are you accepting on behalf of the forwarder? (e.g. confirmed by phone)', acceptOnBehalfNoteRequired: 'Accepting on behalf of the forwarder requires a note.' },
  pt: { acceptOnBehalf: 'Aceitar pelo transitário', acceptOnBehalfPrompt: 'Porque aceita em nome do transitário? (ex.: confirmou por telefone)', acceptOnBehalfNoteRequired: 'Aceitar em nome do transitário requer uma nota.' },
})
