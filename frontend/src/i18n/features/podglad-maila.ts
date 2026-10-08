import { defineFeature } from '../feature'

// podgląd maila do agencji przed pobraniem szkicu .eml (AgencyMailPreviewModal)
export default defineFeature({
  pl: {
    mailPrevTitle: 'Mail do agencji — sprawdź przed wysłaniem', mailPrevAgency: 'Agencja', mailPrevTo: 'Do',
    mailPrevCc: 'DW', mailPrevSubject: 'Temat', mailPrevWarnings: 'Sprawdź przed wysłaniem',
    mailPrevAllOk: 'Komplet — nic nie wypada z maila.', mailPrevFiles: 'Załączniki', mailPrevOpen: 'Otwórz',
    mailPrevKind_excel: 'zestawienie faktur', mailPrevKind_symbols: 'kartoteka symboli (WinSAD)',
    mailPrevKind_invoice: 'faktura PDF', mailPrevKind_packing_list: 'packing lista', mailPrevKind_bl: 'konosament (B/L)',
    mailPrevBody: 'Treść maila', mailPrevDownload: 'Pobierz szkic .eml (Outlook)',
  },
  en: {
    mailPrevTitle: 'Mail to the agency — check before sending', mailPrevAgency: 'Agency', mailPrevTo: 'To',
    mailPrevCc: 'CC', mailPrevSubject: 'Subject', mailPrevWarnings: 'Check before sending',
    mailPrevAllOk: 'Complete — nothing is left out of the mail.', mailPrevFiles: 'Attachments', mailPrevOpen: 'Open',
    mailPrevKind_excel: 'invoice summary', mailPrevKind_symbols: 'symbols file (WinSAD)',
    mailPrevKind_invoice: 'invoice PDF', mailPrevKind_packing_list: 'packing list', mailPrevKind_bl: 'bill of lading (B/L)',
    mailPrevBody: 'Mail text', mailPrevDownload: 'Download .eml draft (Outlook)',
  },
  pt: {
    mailPrevTitle: 'E-mail ao despachante — verifique antes de enviar', mailPrevAgency: 'Despachante', mailPrevTo: 'Para',
    mailPrevCc: 'CC', mailPrevSubject: 'Assunto', mailPrevWarnings: 'Verifique antes de enviar',
    mailPrevAllOk: 'Completo — nada fica de fora do e-mail.', mailPrevFiles: 'Anexos', mailPrevOpen: 'Abrir',
    mailPrevKind_excel: 'resumo de faturas', mailPrevKind_symbols: 'ficheiro de símbolos (WinSAD)',
    mailPrevKind_invoice: 'fatura PDF', mailPrevKind_packing_list: 'lista de embalagem', mailPrevKind_bl: 'conhecimento de embarque (B/L)',
    mailPrevBody: 'Texto do e-mail', mailPrevDownload: 'Descarregar rascunho .eml (Outlook)',
  },
})
