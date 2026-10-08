import { defineFeature } from '../feature'

// Stany widoków (audyt UI PR 4): puste listy z podpowiedzią/CTA zależnym od roli
export default defineFeature({
  pl: {
    queueEmptyHint: 'Zmień zakres dat albo filtry, żeby zobaczyć więcej kontenerów.',
    queueEmptyShowAll: 'Pokaż wszystko',
    noOrdersHintForwarder: 'Tu pojawią się zlecenia przekazane Twojej firmie.',
    complaintsEmptyTitle: 'Brak reklamacji.',
    complaintsEmptyHint: 'Zgłoszenie tworzysz z karty kontenera → „Zgłoś problem”.',
    careNone: 'Brak zleceń specjalnych.',
    pcNone: 'Brak produktów do wywołania.',
  },
  en: {
    queueEmptyHint: 'Change the date range or filters to see more containers.',
    queueEmptyShowAll: 'Show all',
    noOrdersHintForwarder: 'Orders handed over to your company will appear here.',
    complaintsEmptyTitle: 'No complaints.',
    complaintsEmptyHint: 'Create one from the container card → “Report problem”.',
    careNone: 'No special orders.',
    pcNone: 'No products to call off.',
  },
  pt: {
    queueEmptyHint: 'Altere o intervalo de datas ou os filtros para ver mais contentores.',
    queueEmptyShowAll: 'Mostrar tudo',
    noOrdersHintForwarder: 'As ordens entregues à sua empresa aparecerão aqui.',
    complaintsEmptyTitle: 'Sem reclamações.',
    complaintsEmptyHint: 'Crie uma a partir da ficha do contentor → “Reportar problema”.',
    careNone: 'Sem pedidos especiais.',
    pcNone: 'Sem produtos para chamar.',
  },
})
