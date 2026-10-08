import { defineFeature } from '../feature'

// Formularz kontenera: agencja celna tylko ze słownika; stary wolny tekst do odczytu (audyt UI A25)
export default defineFeature({
  pl: { customsAgencyLegacy: 'Stary wpis agencji (tekst): {name} — przypisz agencję ze słownika w sekcji „Odprawa celna (agencja)”.' },
  en: { customsAgencyLegacy: 'Legacy agency entry (text): {name} — assign an agency from the list in the “Customs clearance (agency)” section.' },
  pt: { customsAgencyLegacy: 'Registo antigo da agência (texto): {name} — atribua uma agência da lista na secção «Desalfandegamento (agência)».' },
})
