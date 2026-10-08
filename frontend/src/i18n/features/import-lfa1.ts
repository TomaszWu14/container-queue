// Import dostawców z SAP (LFA1) z podglądem — zakładki, pola, pełny eksport, raport błędów
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    lfa1Tab_new: 'Nowi', lfa1Tab_changed: 'Zmienieni', lfa1Tab_disappeared: 'Zniknęli z SAP', lfa1Tab_errors: 'Błędy',
    lfa1Empty: 'Brak pozycji.', lfa1Row: 'wiersz', lfa1More: '+{n} więcej (pełna lista po zatwierdzeniu w raporcie/audycie)',
    lfa1FullExport: 'To pełny eksport LFA1 — oznacz {n} brakujących jako „nieaktywny w SAP”',
    lfa1DisappearedFull: 'Po zatwierdzeniu dostaną status „nieaktywny w SAP” (nie są kasowani).',
    lfa1DisappearedPartial: 'Bez „pełny eksport” zostaną bez zmian — plik może być częściowy.',
    lfa1ReportDone: 'Import zapisany; pominięte wiersze: {n}.', lfa1ReportBtn: 'Pobierz raport błędów (xlsx)',
    lfa1F_name: 'nazwa', lfa1F_country: 'kraj', lfa1F_street: 'ulica', lfa1F_city: 'miasto', lfa1F_zip: 'kod pocztowy',
    lfa1F_vat: 'VAT', lfa1F_address: 'adres', lfa1F_sap_status: 'status SAP', lfa1F_sap_code: 'kod SAP',
    lfa1S_active: 'aktywny', lfa1S_blocked: 'zablokowany', lfa1S_inactive_in_sap: 'nieaktywny w SAP',
  },
  en: {
    lfa1Tab_new: 'New', lfa1Tab_changed: 'Changed', lfa1Tab_disappeared: 'Gone from SAP', lfa1Tab_errors: 'Errors',
    lfa1Empty: 'Nothing here.', lfa1Row: 'row', lfa1More: '+{n} more (full list in the report/audit after confirming)',
    lfa1FullExport: 'This is a full LFA1 export — mark {n} missing as “inactive in SAP”',
    lfa1DisappearedFull: 'After confirming they get status “inactive in SAP” (never deleted).',
    lfa1DisappearedPartial: 'Without “full export” they stay unchanged — the file may be partial.',
    lfa1ReportDone: 'Import saved; skipped rows: {n}.', lfa1ReportBtn: 'Download error report (xlsx)',
    lfa1F_name: 'name', lfa1F_country: 'country', lfa1F_street: 'street', lfa1F_city: 'city', lfa1F_zip: 'postcode',
    lfa1F_vat: 'VAT', lfa1F_address: 'address', lfa1F_sap_status: 'SAP status', lfa1F_sap_code: 'SAP code',
    lfa1S_active: 'active', lfa1S_blocked: 'blocked', lfa1S_inactive_in_sap: 'inactive in SAP',
  },
  pt: {
    lfa1Tab_new: 'Novos', lfa1Tab_changed: 'Alterados', lfa1Tab_disappeared: 'Saíram do SAP', lfa1Tab_errors: 'Erros',
    lfa1Empty: 'Sem itens.', lfa1Row: 'linha', lfa1More: '+{n} mais (lista completa no relatório/auditoria após confirmar)',
    lfa1FullExport: 'Exportação LFA1 completa — marcar {n} em falta como “inativo no SAP”',
    lfa1DisappearedFull: 'Após confirmar recebem o estado “inativo no SAP” (nunca eliminados).',
    lfa1DisappearedPartial: 'Sem “exportação completa” ficam inalterados — o ficheiro pode ser parcial.',
    lfa1ReportDone: 'Importação guardada; linhas ignoradas: {n}.', lfa1ReportBtn: 'Descarregar relatório de erros (xlsx)',
    lfa1F_name: 'nome', lfa1F_country: 'país', lfa1F_street: 'rua', lfa1F_city: 'cidade', lfa1F_zip: 'código postal',
    lfa1F_vat: 'IVA', lfa1F_address: 'morada', lfa1F_sap_status: 'estado SAP', lfa1F_sap_code: 'código SAP',
    lfa1S_active: 'ativo', lfa1S_blocked: 'bloqueado', lfa1S_inactive_in_sap: 'inativo no SAP',
  },
})
