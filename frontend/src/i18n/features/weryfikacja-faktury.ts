import { defineFeature } from '../feature'

// okno weryfikacji faktury: podgląd oryginału i ostrzeżenie o pozycjach bez dopasowania (audyt #25/#26)
export default defineFeature({
  pl: {
    invOpenPdf: 'Otwórz PDF faktury',
    invUnmatchedWarn: '{n} pozycji bez dopasowania do master daty — w Excelu bez nazwy PL i kodu CN, a w kartotece symboli dla agencji ich nie będzie. Wpisz REF albo zatwierdź świadomie.',
  },
  en: {
    invOpenPdf: 'Open invoice PDF',
    invUnmatchedWarn: '{n} lines not matched to master data — no Polish name or CN code in the Excel, and they will be missing from the agency symbols file. Enter a REF or confirm knowingly.',
  },
  pt: {
    invOpenPdf: 'Abrir PDF da fatura',
    invUnmatchedWarn: '{n} linhas sem correspondência nos dados mestre — sem nome PL nem código CN no Excel e ausentes do ficheiro de símbolos para o despachante. Indique o REF ou confirme conscientemente.',
  },
})
