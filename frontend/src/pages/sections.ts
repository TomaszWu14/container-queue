// Sekcje Administracji i Master data (2026-09-25): płaskie adresy /<obszar>/<slug>,
// grupy w menu bocznym i role per sekcja — jedno źródło prawdy dla menu, tras i 403.
// Role zachowują dotychczasowy dostęp: co było tylko w Administracji → tylko admin,
// co było w Master data (admin + logistyka) → admin + logistyka.
// `legacy` = stare klucze ?tab=… / #… obu ekranów, przekierowywane na nowy adres.
import type { Role } from '../types'

export type Area = 'admin' | 'md'

export interface Section {
  area: Area
  group: string    // klucz i18n nagłówka grupy
  slug: string
  label: string    // klucz i18n nazwy sekcji
  roles: Role[]
  legacy: string[]
}

const ADMIN: Role[] = ['admin']
const EDITORS: Role[] = ['admin', 'logistics']

const sec = (area: Area, group: string, slug: string, label: string, roles: Role[],
             ...legacy: string[]): Section => ({ area, group, slug, label, roles, legacy })

export const SECTIONS: Section[] = [
  sec('admin', 'secGroupOrg', 'uzytkownicy', 'users', ADMIN, 'users'),
  sec('admin', 'secGroupOrg', 'spolki', 'companies', ADMIN, 'companies'),
  sec('admin', 'secGroupOrg', 'agencje-celne', 'customsAgencies', ADMIN, 'customsAgencies'),
  sec('admin', 'secGroupOrg', 'spedytorzy', 'forwarders', ADMIN, 'forwarders'),
  sec('admin', 'secGroupSystem', 'ustawienia', 'settingsTab', ADMIN, 'settings'),
  sec('admin', 'secGroupSystem', 'system', 'sysTabTitle', ADMIN, 'system'),
  sec('admin', 'secGroupSystem', 'powiadomienia', 'notifRulesTab', ADMIN, 'notifRules'),
  sec('admin', 'secGroupSystem', 'sms', 'smsSettingsTab', ADMIN, 'sms'),
  sec('admin', 'secGroupSystem', 'log-logowan', 'authLogTitle', ADMIN, 'authLog'),
  sec('admin', 'secGroupSystem', 'kolory', 'colTitle', ADMIN, 'colors'),

  sec('md', 'secGroupFiles', 'dostawcy', 'suppliers', EDITORS, 'suppliers'),
  sec('md', 'secGroupFiles', 'klienci', 'customers', ADMIN, 'customers'),
  sec('md', 'secGroupFiles', 'materialy', 'materials', ADMIN, 'materials'),
  sec('md', 'secGroupFiles', 'jednostki-materialow', 'mdUnits', EDITORS, 'units'),
  sec('md', 'secGroupFiles', 'dane-materialowe-sp', 'spMatTitle', EDITORS),
  sec('md', 'secGroupFiles', 'armatorzy', 'carriers', ADMIN, 'carriers'),
  sec('md', 'secGroupFiles', 'porty', 'ports', EDITORS, 'ports'),
  sec('md', 'secGroupFiles', 'porty-kontenerowe', 'mdCPorts', EDITORS, 'cports'),
  sec('md', 'secGroupFiles', 'magazyny', 'warehouses', EDITORS, 'warehouses', 'dicts'),
  sec('md', 'secGroupFiles', 'punkty-kontroli', 'checklistPoints', ADMIN, 'checklist'),
  sec('md', 'secGroupFiles', 'zamowienia-sap', 'mdSapOrders', EDITORS, 'orders'),
  sec('md', 'secGroupFiles', 'cele-zapasu', 'pcTargetsTab', EDITORS, 'targets'),
  sec('md', 'secGroupDicts', 'statusy-sprawy-celnej', 'caseStatuses', EDITORS, 'caseStatuses'),
  sec('md', 'secGroupDicts', 'typy-dokumentow', 'documentTypes', EDITORS, 'documentTypes'),
  sec('md', 'secGroupDicts', 'szablony-wysylki', 'docTemplates', ADMIN, 'docTemplates'),
  sec('md', 'secGroupDicts', 'wzory-plikow-agencji', 'atplTitle', EDITORS),
  sec('md', 'secGroupDicts', 'problemy-dostaw', 'problemTypes', ADMIN, 'problems'),
  sec('md', 'secGroupImports', 'import-excel', 'importExcel', ADMIN, 'import'),
  sec('md', 'secGroupImports', 'import-po', 'poImportTitle', ADMIN, 'poImport'),
  sec('md', 'secGroupImports', 'import-marm', 'marmImportTitle', ADMIN, 'marmImport'),
  sec('md', 'secGroupImports', 'import-portow', 'cportImportTitle', ADMIN, 'cportImport'),
  sec('md', 'secGroupImports', 'import-dlt', 'dltImportTitle', ADMIN, 'dltImport'),
  sec('md', 'secGroupControl', 'jakosc-danych', 'mdQuality', EDITORS, 'quality'),
  sec('md', 'secGroupControl', 'dokumenty', 'docSearchTab', EDITORS, 'docs'),
  sec('md', 'secGroupControl', 'podejrzane-faktury', 'confReportTitle', EDITORS),
  sec('md', 'secGroupControl', 'mapowania-indeksow', 'smapTab', EDITORS, 'smap'),
  sec('md', 'secGroupControl', 'audyt', 'auditTab', ADMIN, 'audit'),
]

export const AREA_BASE: Record<Area, string> = { admin: '/administracja', md: '/master-data' }

export const pathOf = (s: Section) => `${AREA_BASE[s.area]}/${s.slug}`
export const canSee = (role: Role | undefined, s: Section) => !!role && s.roles.includes(role)
export const findSection = (key: string) =>
  SECTIONS.find(s => s.slug === key || s.legacy.includes(key))

// Stary adres (?tab=porty, ?zakladka=…, #porty) → nowy /<obszar>/<slug>; null = brak.
export function legacyTarget(search: string, hash: string): string | null {
  const params = new URLSearchParams(search)
  const key = params.get('tab') ?? params.get('zakladka') ?? decodeURIComponent(hash.replace(/^#/, ''))
  const found = key ? findSection(key) : undefined
  return found ? pathOf(found) : null
}
