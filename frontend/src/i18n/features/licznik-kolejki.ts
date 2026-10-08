import { defineFeature } from '../feature'

// Podpowiedź licznika przy „Kolejce” w nawigacji (audyt UI C14/A17)
export default defineFeature({
  pl: { navQueueCountHint: 'Wszystkie aktywne kontenery w Twoim zakresie (niezależnie od filtrów kolejki)' },
  en: { navQueueCountHint: 'All active containers in your scope (regardless of queue filters)' },
  pt: { navQueueCountHint: 'Todos os contentores ativos no seu âmbito (independentemente dos filtros da fila)' },
})
