import { defineFeature } from '../feature'

// Widoczne etykiety pól (audyt UI C33/B26/C22): odprawa na karcie kontenera (dwa pola „Uwagi”
// rozróżnione), Specjalna troska, formularz kontenera
export default defineFeature({
  pl: {
    flAssignNote: 'Uwaga do zlecenia agencji', flStatusNote: 'Komentarz do zmiany statusu',
    flCustomsStatus: 'Status odprawy', flCustomsStatusBtn: 'Zmień status odprawy',
    careRefsHint: 'Kilka numerów oddziel przecinkiem lub nową linią', frmDocsComplete: 'Dokumenty kompletne',
  },
  en: {
    flAssignNote: 'Note for the agency order', flStatusNote: 'Comment on status change',
    flCustomsStatus: 'Customs status', flCustomsStatusBtn: 'Change customs status',
    careRefsHint: 'Separate several numbers with a comma or new line', frmDocsComplete: 'Documents complete',
  },
  pt: {
    flAssignNote: 'Nota para o pedido à agência', flStatusNote: 'Comentário à mudança de estado',
    flCustomsStatus: 'Estado do desalfandegamento', flCustomsStatusBtn: 'Mudar estado do desalfandegamento',
    careRefsHint: 'Separe vários números com vírgula ou nova linha', frmDocsComplete: 'Documentos completos',
  },
})
