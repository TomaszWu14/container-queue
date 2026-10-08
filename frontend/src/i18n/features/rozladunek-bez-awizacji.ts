import { defineFeature } from '../feature'

// Magazyn potwierdza rozładunek kontenera bez awizacji — tylko z notatką (decyzja 2026-09-28)
export default defineFeature({
  pl: {
    markUnloadedNoAvizo: 'Ten kontener nie jest awizowany. Napisz, dlaczego przyjmujesz go mimo to (np. przyjechał bez awizacji):',
    markUnloadedNoteRequired: 'Bez notatki nie można potwierdzić rozładunku nieawizowanego kontenera.',
  },
  en: {
    markUnloadedNoAvizo: 'This container has no delivery booking. Explain why you accept it anyway (e.g. arrived without booking):',
    markUnloadedNoteRequired: 'A note is required to confirm unloading of a container without a booking.',
  },
  pt: {
    markUnloadedNoAvizo: 'Este contentor não tem marcação de entrega. Explique porque o aceita mesmo assim (ex.: chegou sem marcação):',
    markUnloadedNoteRequired: 'É necessária uma nota para confirmar a descarga de um contentor sem marcação.',
  },
})
