// Poczekalnia dokumentów (spec 2026-10-06-dokumenty-dostaw §3): „Dodaj dokumenty”, okno
// „Sprawdź i potwierdź” i pasek „N dokumentów czeka na potwierdzenie”.
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    inqAdd: 'Dodaj dokumenty', inqAddFolder: 'Folder', inqDrop: 'albo upuść tu pliki, folder lub ZIP',
    inqUploading: 'Wgrywanie…', inqWaiting: '{n} dokumentów czeka na potwierdzenie', inqReview: 'Sprawdź',
    inqTitle: 'Sprawdź i potwierdź', inqPart: 'Dokument', inqPages: 'str. {a}–{b}', inqType: 'Typ',
    inqTarget: 'Kontener', inqGate: 'Bramka', inqOpen: 'Podgląd', inqMoveTo: 'Przenieś do {v}',
    inqReject: 'Odrzuć', inqRestore: 'Przywróć',
    inqConfirm: 'Potwierdź', inqDiscard: 'Odrzuć całość', inqLater: 'Zamknij — wrócę później',
    inqDiscardAsk: 'Odrzucić całe wgranie? Żaden dokument nie trafi do dostawy.',
    inqDone: 'Dodano: {v}', inqDoneItem: '{c}: faktury {i}, załączniki {a}', inqSkipped: 'Pominięte: {v}',
    inqType_CMR: 'CMR', inqType_MAIL: 'Korespondencja (mail)', inqType_OTHER: 'Inny dokument',
    inqGate_ok: '✓ OK', inqGate_uncertain: 'niepewny', inqGate_duplicate: 'dubel',
    inqGate_conflict: 'inny kontener', inqGate_unreadable: 'nieczytelny',
  },
  en: {
    inqAdd: 'Add documents', inqAddFolder: 'Folder', inqDrop: 'or drop files, a folder or a ZIP here',
    inqUploading: 'Uploading…', inqWaiting: '{n} documents waiting for confirmation', inqReview: 'Review',
    inqTitle: 'Review and confirm', inqPart: 'Document', inqPages: 'p. {a}–{b}', inqType: 'Type',
    inqTarget: 'Container', inqGate: 'Check', inqOpen: 'Preview', inqMoveTo: 'Move to {v}',
    inqReject: 'Reject', inqRestore: 'Restore',
    inqConfirm: 'Confirm', inqDiscard: 'Discard all', inqLater: 'Close — come back later',
    inqDiscardAsk: 'Discard the whole upload? No document will be added to the delivery.',
    inqDone: 'Added: {v}', inqDoneItem: '{c}: invoices {i}, attachments {a}', inqSkipped: 'Skipped: {v}',
    inqType_CMR: 'CMR', inqType_MAIL: 'Correspondence (e-mail)', inqType_OTHER: 'Other document',
    inqGate_ok: '✓ OK', inqGate_uncertain: 'uncertain', inqGate_duplicate: 'duplicate',
    inqGate_conflict: 'other container', inqGate_unreadable: 'unreadable',
  },
  pt: {
    inqAdd: 'Adicionar documentos', inqAddFolder: 'Pasta', inqDrop: 'ou largue aqui ficheiros, uma pasta ou um ZIP',
    inqUploading: 'A carregar…', inqWaiting: '{n} documentos aguardam confirmação', inqReview: 'Verificar',
    inqTitle: 'Verificar e confirmar', inqPart: 'Documento', inqPages: 'p. {a}–{b}', inqType: 'Tipo',
    inqTarget: 'Contentor', inqGate: 'Verificação', inqOpen: 'Pré-visualizar', inqMoveTo: 'Mover para {v}',
    inqReject: 'Rejeitar', inqRestore: 'Repor',
    inqConfirm: 'Confirmar', inqDiscard: 'Rejeitar tudo', inqLater: 'Fechar — volto mais tarde',
    inqDiscardAsk: 'Rejeitar todo o carregamento? Nenhum documento será adicionado à entrega.',
    inqDone: 'Adicionado: {v}', inqDoneItem: '{c}: faturas {i}, anexos {a}', inqSkipped: 'Ignorados: {v}',
    inqType_CMR: 'CMR', inqType_MAIL: 'Correspondência (e-mail)', inqType_OTHER: 'Outro documento',
    inqGate_ok: '✓ OK', inqGate_uncertain: 'incerto', inqGate_duplicate: 'duplicado',
    inqGate_conflict: 'outro contentor', inqGate_unreadable: 'ilegível',
  },
})
