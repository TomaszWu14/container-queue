import { defineFeature } from '../feature'

// usuwanie i podmiana wgranego dokumentu (AttachmentActions.tsx)
export default defineFeature({
  pl: {
    attDelete: 'Usuń', attReplace: 'Podmień',
    attReplaceHint: 'Wgraj poprawny plik w miejsce tego (ten sam typ dokumentu).',
    attDeleteConfirm: 'Usunąć „{name}”? Wpis zostanie w historii kontenera.',
    attReplaceReason: 'Dokumenty były już wysłane do agencji — podaj powód podmiany:',
  },
  en: {
    attDelete: 'Delete', attReplace: 'Replace',
    attReplaceHint: 'Upload the correct file in place of this one (same document type).',
    attDeleteConfirm: 'Delete “{name}”? The action is kept in the container history.',
    attReplaceReason: 'Documents were already sent to the agency — give the reason for replacing:',
  },
  pt: {
    attDelete: 'Eliminar', attReplace: 'Substituir',
    attReplaceHint: 'Carregar o ficheiro correto no lugar deste (mesmo tipo de documento).',
    attDeleteConfirm: 'Eliminar “{name}”? A ação fica no histórico do contentor.',
    attReplaceReason: 'Os documentos já foram enviados ao despachante — indique o motivo da substituição:',
  },
})
