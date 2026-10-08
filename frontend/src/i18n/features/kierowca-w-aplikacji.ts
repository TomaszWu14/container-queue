import { defineFeature } from '../feature'

// Spóźnienie kierowcy wpisane na bramie (kierowca dzwoni) — zamiast strony z linku (2026-10-07)
export default defineFeature({
  pl: { gateDelayBtn: 'Spóźnienie', gateDelayPrompt: 'Kierowca spóźni się — o której będzie? (GG:MM)' },
  en: { gateDelayBtn: 'Delay', gateDelayPrompt: 'The driver is late — expected arrival time? (HH:MM)' },
  pt: { gateDelayBtn: 'Atraso', gateDelayPrompt: 'O motorista está atrasado — hora prevista? (HH:MM)' },
})
