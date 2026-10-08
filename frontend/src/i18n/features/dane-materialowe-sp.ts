// Dane materiałowe SharePoint — kafelek Master data (pages/masterdata/SpMaterialsTab.tsx)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    spMatTitle: 'Dane materiałowe SharePoint',
    spMatHint: 'Wgraj cały plik SAP_Dane_materiałowe.xlsm — każda zakładka staje się osobną tabelą, a nazwy PL (krótkie) i kody CN z „Hierarchii produktów” trafiają do materiałów (faktury, Excel i kartoteka dla agencji).',
    spMatImport: 'Importuj plik', spMatUploading: 'Wysyłam plik…', spMatRunning: 'Import {file} w toku — to potrwa około minuty; możesz przejść gdzie indziej, wynik pojawi się tutaj.',
    spMatSheets: 'zakładki', spMatUpdated: 'zaktualizowane materiały',
    spMatEmpty: 'Brak danych — wgraj plik.', spMatPrev: '‹ Poprzednie', spMatSearch: 'Szukaj w zakładce (REF, nazwa, CN…)', spMatNext: 'Następne ›',
  },
  en: {
    spMatTitle: 'SharePoint material data',
    spMatHint: 'Upload the whole SAP_Dane_materiałowe.xlsm file — every sheet becomes a separate table, and Polish (short) names and CN codes from “Hierarchia produktów” update the materials (invoices, Excel and the agency catalogue).',
    spMatImport: 'Import file', spMatUploading: 'Uploading…', spMatRunning: 'Importing {file} — about a minute; you can leave this page, the result will show up here.',
    spMatSheets: 'sheets', spMatUpdated: 'materials updated',
    spMatEmpty: 'No data — upload the file.', spMatPrev: '‹ Previous', spMatSearch: 'Search this sheet (REF, name, CN…)', spMatNext: 'Next ›',
  },
  pt: {
    spMatTitle: 'Dados de materiais SharePoint',
    spMatHint: 'Carregue o ficheiro SAP_Dane_materiałowe.xlsm inteiro — cada folha torna-se uma tabela separada, e os nomes PL (curtos) e códigos CN da “Hierarchia produktów” atualizam os materiais (faturas, Excel e catálogo para a agência).',
    spMatImport: 'Importar ficheiro', spMatUploading: 'A enviar…', spMatRunning: 'A importar {file} — cerca de um minuto; pode sair desta página, o resultado aparecerá aqui.',
    spMatSheets: 'folhas', spMatUpdated: 'materiais atualizados',
    spMatEmpty: 'Sem dados — carregue o ficheiro.', spMatPrev: '‹ Anteriores', spMatSearch: 'Pesquisar na folha (REF, nome, CN…)', spMatNext: 'Seguintes ›',
  },
})
