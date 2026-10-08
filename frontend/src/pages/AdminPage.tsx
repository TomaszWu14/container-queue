import { useT } from '../i18n'
import CompaniesTab from './admin/CompaniesTab'
import CustomsAgenciesTab from './admin/CustomsAgenciesTab'
import NamedTab from './admin/NamedTab'
import NotificationRulesTab from './admin/NotificationRulesTab'
import SettingsTab from './admin/SettingsTab'
import SmsSettingsTab from './admin/SmsSettingsTab'
import UsersTab from './admin/UsersTab'
import SystemTab from './admin/SystemTab'
import AuthLogTab from './admin/AuthLogTab'
import ColorsTab from './admin/ColorsTab'
import DictionariesTab from './masterdata/DictionariesTab'
import SectionShell, { SectionMore } from './SectionShell'

// Administracja = organizacja i system. Dane podstawowe (kartoteki, słowniki, importy)
// są w Master data — patrz sections.ts. Stare ?tab=… przekierowuje SectionShell.
export default function AdminPage() {
  const t = useT()
  // szybka edycja w tabeli (CSV, historia zmian, usuwanie) — dawniej Master data → Słowniki
  const quick = (kind: 'companies' | 'agencies') => (
    <SectionMore label={t('secQuickEdit')}>
      <DictionariesTab kind={kind} companies={[]} />
    </SectionMore>
  )
  const render = (slug: string) => {
    switch (slug) {
      case 'uzytkownicy': return <UsersTab />
      case 'spolki': return <><CompaniesTab />{quick('companies')}</>
      case 'agencje-celne': return <><CustomsAgenciesTab />{quick('agencies')}</>
      case 'spedytorzy': return (
        <NamedTab endpoint="/api/forwarders" withEmail manageable
          extraFields={[{ key: 'contact_person', label: t('mdContact') },
            { key: 'contact_phone', label: t('mdPhone') },
            { key: 'address', label: t('mdAddress') }, { key: 'note', label: t('mdNote') },
            { key: 'language', label: t('forwarderLang'), options: ['pl', 'en'] }]} />
      )
      case 'ustawienia': return <SettingsTab />
      case 'system': return <SystemTab />
      case 'powiadomienia': return <NotificationRulesTab />
      case 'sms': return <SmsSettingsTab />
      case 'log-logowan': return <AuthLogTab />
      case 'kolory': return <ColorsTab />
      default: return null
    }
  }
  return <SectionShell area="admin" title={t('admin')} render={render} />
}
