// Centralny routing: mapa starych→nowych ścieżek (redirecty zachowujące zakładki),
// dostęp per widok wg roli (jedno źródło prawdy dla tras) oraz widoki 404/403.
// Wydzielone z App.tsx, by dało się to przetestować bez montowania całej aplikacji.
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { useT } from './i18n'
import type { Role } from './types'

// Stare ścieżki → nowe. :param jest przenoszony, query string zachowany.
// Dzięki temu zakładki i linki (np. /container/123?x=1) dalej działają (redirect).
export const LEGACY_REDIRECTS: Record<string, string> = {
  '/dashboard': '/',
  '/calendar': '/kalendarz',
  '/orders': '/zamowienia',
  '/orders/:id': '/zamowienia/:id',
  '/forwarding': '/spedycja',
  '/customs': '/odprawa',
  '/quotes': '/wyceny',
  '/tracking': '/sledzenie',
  '/complaints': '/reklamacje',
  '/complaints/archive': '/reklamacje/archiwum',
  '/complaints/:id': '/reklamacje/:id',
  '/archive': '/kolejka/archiwum',
  '/container/:id': '/kontenery/:id',
  '/admin': '/administracja',
  '/dzis': '/kolejka',   // zakładka „Co dziś” usunięta — plan dnia to kolejka
}

// Podstawia wartości parametrów (:id → 123) w szablonie ścieżki docelowej.
export function fillTarget(template: string, params: Record<string, string | undefined>): string {
  return template.replace(/:([A-Za-z0-9_]+)/g, (_m, key) => params[key] ?? `:${key}`)
}

// Redirect ze starej ścieżki na nową — zachowuje parametry ścieżki i query string.
export function LegacyRedirect({ to }: { to: string }) {
  const params = useParams()
  const { search } = useLocation()
  return <Navigate to={fillTarget(to, params) + search} replace />
}

// Klucze widoków chronionych rolą — jedno miejsce, w którym decyduje się dostęp.
export type ViewKey =
  | 'dashboard' | 'kolejka' | 'kolejka-arch' | 'kontener' | 'kalendarz'
  | 'zamowienia' | 'spedycja' | 'odprawa' | 'wyceny' | 'sledzenie'
  | 'reklamacje' | 'administracja' | 'awizo'

// Dostęp per widok — zachowuje DOTYCHCZASOWĄ semantykę tras (nie zmienia logiki biznesowej),
// tylko zamienia „trasa nie istnieje → cichy redirect" na jawne 403/404.
// Odprawa to wyłącznie agencja celna (decyzja 2026-09-28): spedytor nie widzi statusu odprawy
// (backend i tak maskuje pola — _FORWARDER_HIDDEN), więc UI chowa kolumny/plakietki zamiast „Brak”.
export const seesCustoms = (role?: Role | null): boolean => role !== 'forwarder'
// Baza wiedzy (ACL-001): bez partnerów zewnętrznych (backend InternalReaders), a sprzedaż
// tylko czyta — „+1” i „Zgłoś temat” to InternalWriters (bez sales)
export const seesKnowledge = (role?: Role | null): boolean => role !== 'forwarder' && role !== 'customs'
export const writesKnowledge = (role?: Role | null): boolean => seesKnowledge(role) && role !== 'sales'

export function canAccess(role: Role, key: ViewKey): boolean {
  if (role === 'sales') {
    // Sprzedaż (2026-09-27): JAWNA biała lista, tylko odczyt — kolejka, karta kontenera,
    // kalendarz, śledzenie (+ Specjalna troska i Wiedza poza ViewKey). Bez kosztów.
    return key === 'kolejka' || key === 'kontener' || key === 'kalendarz' || key === 'sledzenie'
  }
  if (role === 'purchasing') {
    // Dział zakupów: JAWNA biała lista — tylko kolejka, kontener (edycja statusu
    // zakupów), zamówienia i spedycja. Bez dziedziczenia z negatywnych bramek,
    // więc żadna Odprawa/Wyceny/Archiwum nie wpada tu po cichu.
    return key === 'kolejka' || key === 'kontener'
      || key === 'zamowienia' || key === 'spedycja'
  }
  const notCustoms = role !== 'customs'
  const notWhCustoms = role !== 'warehouse' && role !== 'customs'
  switch (key) {
    case 'kolejka':
    case 'kontener':
    case 'awizo':
      return true
    case 'zamowienia':
      // jak backend PurchasingReaders (admin, logistyka, zakupy — zakupy wyżej);
      // spedytor dostaje 403 na /api/orders od #957
      return role === 'admin' || role === 'logistics'
    case 'dashboard':
    case 'kolejka-arch':
    case 'spedycja':
    case 'wyceny':
      return notWhCustoms
    case 'kalendarz':
    case 'sledzenie':
    case 'reklamacje':
      return notCustoms
    case 'odprawa':
      return role === 'admin' || role === 'logistics'
    case 'administracja':
      return role === 'admin'
    default:
      return false
  }
}

// Strona startowa po zalogowaniu wg roli. Dział transportu (logistics) pracuje
// w kolejce, nie na pulpicie — pulpit zostaje dostępny pod /pulpit. Pozostałe
// role: pulpit jeśli mają dostęp, inaczej kolejka (dotychczasowe zachowanie).
export function homeFor(role: Role): string {
  if (role === 'logistics') return '/kolejka'
  return canAccess(role, 'dashboard') ? '/' : '/kolejka'
}

export function Forbidden() {
  const t = useT()
  return (
    <main className="page route-msg">
      <h1>{t('err403Title')}</h1>
      <p>{t('err403Body')}</p>
      <Link className="btn" to="/">{t('backHome')}</Link>
    </main>
  )
}

export function NotFound() {
  const t = useT()
  return (
    <main className="page route-msg">
      <h1>{t('err404Title')}</h1>
      <p>{t('err404Body')}</p>
      <Link className="btn" to="/">{t('backHome')}</Link>
    </main>
  )
}
