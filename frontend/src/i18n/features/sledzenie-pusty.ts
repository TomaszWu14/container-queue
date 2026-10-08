import { defineFeature } from '../feature'

// Śledzenie: pusty stan zamiast pełnego globusa bez danych (audyt UI C30 / UX-038)
export default defineFeature({
  pl: {
    mapEmptyHint: 'Mapa pojawi się, gdy kontener w drodze dostanie pozycję (statek AIS lub zdarzenie trackingu).',
    mapShowAnyway: 'Pokaż mapę',
  },
  en: {
    mapEmptyHint: 'The map appears once a container in transit gets a position (AIS vessel or tracking event).',
    mapShowAnyway: 'Show map',
  },
  pt: {
    mapEmptyHint: 'O mapa aparece quando um contentor em trânsito tiver posição (navio AIS ou evento de tracking).',
    mapShowAnyway: 'Mostrar mapa',
  },
})
