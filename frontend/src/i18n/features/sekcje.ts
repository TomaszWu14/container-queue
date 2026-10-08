// Menu sekcji Administracji i Master data (pages/SectionShell.tsx, pages/sections.ts)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    secGroupOrg: 'Organizacja', secGroupSystem: 'System', secGroupFiles: 'Kartoteki',
    secGroupDicts: 'Słowniki', secGroupImports: 'Importy', secGroupControl: 'Kontrola danych',
    secStart: 'Wszystkie sekcje', secPick: 'Sekcja',
    secQuickEdit: 'Szybka edycja w tabeli (CSV, historia zmian, usuwanie)',
    secPortsMore: 'Profil sezonowy transit time i scalanie duplikatów',
    secWarehousesMore: 'Adres, kontakt, instrukcja wjazdu i okna awizacji',
  },
  en: {
    secGroupOrg: 'Organisation', secGroupSystem: 'System', secGroupFiles: 'Records',
    secGroupDicts: 'Dictionaries', secGroupImports: 'Imports', secGroupControl: 'Data control',
    secStart: 'All sections', secPick: 'Section',
    secQuickEdit: 'Quick table editing (CSV, change history, delete)',
    secPortsMore: 'Seasonal transit time profile and duplicate merging',
    secWarehousesMore: 'Address, contact, entry instructions and booking slots',
  },
  pt: {
    secGroupOrg: 'Organização', secGroupSystem: 'Sistema', secGroupFiles: 'Cadastros',
    secGroupDicts: 'Dicionários', secGroupImports: 'Importações', secGroupControl: 'Controlo de dados',
    secStart: 'Todas as secções', secPick: 'Secção',
    secQuickEdit: 'Edição rápida em tabela (CSV, histórico, eliminar)',
    secPortsMore: 'Perfil sazonal de transit time e fusão de duplicados',
    secWarehousesMore: 'Morada, contacto, instruções de entrada e janelas de aviso',
  },
})
