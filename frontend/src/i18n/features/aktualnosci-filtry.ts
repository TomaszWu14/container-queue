import { defineFeature } from '../feature'

// Aktualności: filtry statusu / ważności / kategorii i status przeczytania na karcie (2026-10-06)
export default defineFeature({
  pl: {
    newsStatusAll: 'Wszystkie', newsStatusRead: 'Przeczytane', newsStatusNew: 'Nowa',
    newsFilterStatus: 'Status', newsFilterPriority: 'Ważność', newsFilterCats: 'Kategorie',
    newsPrioAll: 'Każda ważność', newsPrio_urgent: 'Pilne', newsPrio_normal: 'Ważne', newsPrio_info: 'Informacyjne',
    newsMarkRead: 'Oznacz jako przeczytaną',
  },
  en: {
    newsStatusAll: 'All', newsStatusRead: 'Read', newsStatusNew: 'New',
    newsFilterStatus: 'Status', newsFilterPriority: 'Priority', newsFilterCats: 'Categories',
    newsPrioAll: 'Any priority', newsPrio_urgent: 'Urgent', newsPrio_normal: 'Important', newsPrio_info: 'Informational',
    newsMarkRead: 'Mark as read',
  },
  pt: {
    newsStatusAll: 'Todas', newsStatusRead: 'Lidas', newsStatusNew: 'Nova',
    newsFilterStatus: 'Estado', newsFilterPriority: 'Prioridade', newsFilterCats: 'Categorias',
    newsPrioAll: 'Qualquer prioridade', newsPrio_urgent: 'Urgente', newsPrio_normal: 'Importante', newsPrio_info: 'Informativa',
    newsMarkRead: 'Marcar como lida',
  },
})
