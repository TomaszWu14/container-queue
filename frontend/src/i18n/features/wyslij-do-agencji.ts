import { defineFeature } from '../feature'

// „Wyślij dokumenty do agencji” — uczciwy podgląd: powiadomienie w aplikacji, odbiorcy, pliki
export default defineFeature({
  pl: {
    sendDocsInAppHint: 'Agencja dostanie powiadomienie w aplikacji z listą plików (to nie jest e-mail). Mail z plikami: „Przygotuj maila do agencji” w sekcji faktur.',
    sendDocsRecipients: 'Odbiorcy', sendDocsFiles: 'Pliki',
    sendDocsNoRecipients: 'agencja nie ma kont w aplikacji — powiadomienie do nikogo nie dotrze; wyślij mailem (Excel, kartoteka symboli, PDF-y)',
    sendDocsNeedExcel: 'Brak paczki faktur z aktualnym Excelem — zatwierdź faktury i wygeneruj Excel w sekcji faktur, potem przygotuj maila.',
  },
  en: {
    sendDocsInAppHint: 'The agency gets an in-app notification with the file list (this is not an e-mail). E-mail with files: “Prepare mail to the agency” in the invoices section.',
    sendDocsRecipients: 'Recipients', sendDocsFiles: 'Files',
    sendDocsNoRecipients: 'the agency has no accounts in the app — the notification reaches no one; send an e-mail instead (Excel, symbols file, PDFs)',
    sendDocsNeedExcel: 'No invoice batch with an up-to-date Excel — confirm the invoices and generate the Excel in the invoices section, then prepare the e-mail.',
  },
  pt: {
    sendDocsInAppHint: 'O despachante recebe uma notificação na aplicação com a lista de ficheiros (não é um e-mail). E-mail com ficheiros: “Preparar e-mail ao despachante” na secção de faturas.',
    sendDocsRecipients: 'Destinatários', sendDocsFiles: 'Ficheiros',
    sendDocsNoRecipients: 'o despachante não tem contas na aplicação — a notificação não chega a ninguém; envie por e-mail (Excel, ficheiro de símbolos, PDFs)',
    sendDocsNeedExcel: 'Não há lote de faturas com Excel atualizado — confirme as faturas e gere o Excel na secção de faturas, depois prepare o e-mail.',
  },
})
