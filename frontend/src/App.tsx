import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ErrorBoundary } from './ErrorBoundary'
import { Forbidden, LegacyRedirect, LEGACY_REDIRECTS, NotFound, canAccess, homeFor, seesKnowledge } from './routing'
import { api, logoutRequest } from './api'
import { setUploadLimitMb } from './uploadLimit'
import { SESSION_EXPIRED_EVENT } from './sessionEvents'
import { CSRF_HEADERS } from './csrf'
import GlobalSearch from './GlobalSearch'
import Onboarding from './Onboarding'
import Sidebar from './Sidebar'
import { Lang, LangContext, useT } from './i18n'
import { AppSkeleton, Skeleton, ToastProvider } from './feedback'
import { ConfirmProvider } from './ConfirmDialog'
import { ChangePasswordPage, ForgotPasswordPage, ResetPasswordPage } from './pages/AuthPages'
import DashboardPage from './pages/DashboardPage'
import QueuePage from './pages/QueuePage'
import { BulletinBanner } from './KnowledgePanel'
import type { User } from './types'
import { pullPrefs } from './prefs'
import { UserContext } from './userContext'
import { setThemeColors, type ThemeColors } from './themeColors'
import { leavePresence } from './PresenceBar'
import DeployWatch from './DeployWatch'

export { UserContext, useUser } from './userContext'

// PERF-006: strony poza startowymi (pulpit, kolejka) ładowane na żądanie —
// osobne chunki zamiast jednego index.js 1,36 MB; w trakcie ładowania szkielet strony
const LoginPage = lazy(() => import('./pages/LoginPage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const AnalitykaPage = lazy(() => import('./pages/AnalitykaPage'))
const ChangesFeedPage = lazy(() => import('./pages/ChangesFeedPage'))
const MasterDataPage = lazy(() => import('./pages/MasterDataPage'))
const AvizoFormPage = lazy(() => import('./pages/AvizoFormPage'))
const AvizoDriverFormPage = lazy(() => import('./pages/AvizoDriverFormPage'))
const DltPage = lazy(() => import('./pages/DltPage'))
const QuotesPage = lazy(() => import('./pages/QuotesPage'))
const PalletCallsPage = lazy(() => import('./pages/PalletCallsPage'))
const ComplaintsPage = lazy(() => import('./pages/ComplaintsPage'))
const ComplaintDetailPage = lazy(() => import('./pages/ComplaintDetailPage'))
const ComplaintStatsPage = lazy(() => import('./pages/ComplaintStatsPage'))
const CalendarPage = lazy(() => import('./pages/CalendarPage'))
const ContainerPage = lazy(() => import('./pages/ContainerPage'))
const SupplierPage = lazy(() => import('./pages/SupplierPage'))
const KartaRozladunkuPage = lazy(() => import('./pages/KartaRozladunkuPage'))
const GatePage = lazy(() => import('./pages/GatePage'))
const AvizoProposalsPage = lazy(() => import('./pages/AvizoProposalsPage'))
const MyAvizosPage = lazy(() => import('./pages/MyAvizosPage'))
const MyAvizoAnswer = lazy(() => import('./pages/MyAvizosPage').then(m => ({ default: m.MyAvizoAnswer })))
const CustomsPage = lazy(() => import('./pages/CustomsPage'))
const LandingPage = lazy(() => import('./pages/LandingPage'))
const ForwardingPage = lazy(() => import('./pages/ForwardingPage'))
const SpecialCarePage = lazy(() => import('./pages/SpecialCarePage'))
const ForwardingRequestsPage = lazy(() => import('./pages/ForwardingRequestsPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const MyColorsPage = lazy(() => import('./pages/MyColorsPage'))
const Enroll2FAPage = lazy(() => import('./pages/Enroll2FAPage'))
const OrdersPage = lazy(() => import('./pages/OrdersPage'))
const OrderDetailPage = lazy(() => import('./pages/OrdersPage').then(m => ({ default: m.OrderDetailPage })))
const WarehouseQueuePage = lazy(() => import('./pages/WarehouseQueuePage'))
const TrackingPage = lazy(() => import('./pages/TrackingPage'))
const WiedzaPage = lazy(() => import('./pages/WiedzaPage'))
const KoszykPage = lazy(() => import('./pages/KoszykPage'))
const SadImportPage = lazy(() => import('./pages/SadImportPage'))
const pageFallback = <main className="page"><Skeleton rows={6} /></main>

// Sticky pasek trybu podglądu (impersonacja roli przez admina) — wyjście przywraca
// normalny token przez POST /api/auth/refresh i przeładowuje aplikację.
function ImpersonationBanner({ role }: { role: string }) {
  const t = useT()
  const exit = async () => {
    await fetch('/api/auth/refresh', { method: 'POST', headers: CSRF_HEADERS }).catch(() => {})
    window.location.reload()
  }
  return (
    <div data-testid="impersonation-banner" style={{
      position: 'sticky', top: 0, zIndex: 100, display: 'flex', alignItems: 'center',
      justifyContent: 'center', gap: 12, padding: '6px 12px', background: '#8a5c00',
      color: '#fff', fontWeight: 600, fontSize: 14,
    }}>
      <span>{t('impersonationInfo').replace('{role}', t('roleName_' + role))}</span>
      <button className="btn small" onClick={exit}
              style={{ background: '#fff', color: '#8a5c00' }}>
        {t('impersonationExit')}
      </button>
    </div>
  )
}

// Widok chroniony rolą: brak dostępu → jawne 403 (zamiast cichego redirectu jak dawniej).
function Guarded({ ok, children }: { ok: boolean; children: ReactElement }) {
  return ok ? children : <Forbidden />
}

// Strona główna „/": dashboard (dla ról, które go mają) albo redirect do kolejki.
// Zachowuje stare deep-linki kolejki z rootu (/?firm=acme, /?date=…), które kiedyś
// otwierały kolejkę pod „/" — przenosi je na /kolejka z zachowaniem query.
function Home({ role }: { role: User['role'] }) {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  if (params.has('firm') || params.has('date')) {
    return <Navigate to={`/kolejka${search}`} replace />
  }
  const home = homeFor(role)
  return home === '/' ? <DashboardPage /> : <Navigate to={home} replace />
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('timporye_lang') as Lang) || 'pl')
  const [user, setUser] = useState<User | null>(null)
  const [checked, setChecked] = useState(false)
  const navigate = useNavigate()
  const { pathname } = useLocation()

  const reload = useCallback(() => {
    api.get<User>('/api/auth/me')
      // profil widoku (kolumny/gęstość/zapisane widoki) zasiewamy PRZED renderem
      // stron — QueuePage czyta localStorage przy mount
      .then(async u => {
        await pullPrefs()
        // kolory motywów z Administracji — w tle; błąd = zostają domyślne / ostatnio zapamiętane
        api.get<ThemeColors>('/api/theme-colors').then(setThemeColors).catch(() => {})
        // limit wielkości pliku z backendu (max_upload_mb) — sprawdzany przed uploadem
        api.get<{ max_upload_mb?: number }>('/api/ui-config')
          .then(c => setUploadLimitMb(c?.max_upload_mb)).catch(() => {})
        setUser(u)
      })
      .catch(() => setUser(null))
      .finally(() => setChecked(true))
  }, [])

  useEffect(() => reload(), [reload])
  // sesja wygasła (401 po nieudanym odświeżeniu) → ekran logowania pod TYM SAMYM adresem
  // (logowanie nie zmienia URL, więc wracamy tam, gdzie byliśmy); drzewo zalogowanego
  // odmontowuje się razem z jego odpytywaniem w tle
  useEffect(() => {
    const expired = () => setUser(null)
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  }, [])
  useEffect(() => localStorage.setItem('timporye_lang', lang), [lang])

  const logout = async () => {
    await leavePresence()          // zniknij z paska obecności od razu
    await logoutRequest()
    setUser(null)
    // wspólny terminal: następna osoba startuje od „/”, nie na stronie (lub 403) poprzednika
    navigate('/', { replace: true })
  }

  if (!checked) return <AppSkeleton />

  return (
    <ToastProvider>
    <LangContext.Provider value={{ lang, setLang }}>
      <DeployWatch />
      <ConfirmProvider>
      <UserContext.Provider value={{ user, reload }}>
        {user && user.must_change_password ? (
          <ChangePasswordPage onDone={reload} />
        ) : user && user.must_enroll_2fa ? (
          <Suspense fallback={<AppSkeleton />}><Enroll2FAPage onDone={reload} onLogout={logout} /></Suspense>
        ) : user ? (
          <div className="app-shell" data-tour="ctrlk">
            {user.impersonated && <ImpersonationBanner role={user.role} />}
            <GlobalSearch />
            <Onboarding />
            <Sidebar onLogout={logout} />
            <BulletinBanner />
            <div className="app-main">
            <ErrorBoundary resetKey={pathname} fallback={
              <main className="page" style={{ textAlign: 'center', padding: '3rem 1rem' }}>
                <h2 style={{ marginBottom: 8 }}>Coś poszło nie tak</h2>
                <p className="muted">Wystąpił nieoczekiwany błąd na tej stronie.</p>
                <button className="btn" onClick={() => window.location.reload()}>Odśwież stronę</button>
              </main>
            }>
            <Suspense fallback={pageFallback}>
            <Routes>
              {/* Start = dashboard (z rozgałęzieniem ról); kolejka ma własny adres /kolejka */}
              <Route path="/" element={<Home role={user.role} />} />
              {/* pulpit pod jawnym adresem — role startujące w kolejce (transport)
                  nadal mogą go otworzyć */}
              <Route path="/pulpit" element={
                <Guarded ok={canAccess(user.role, 'dashboard')}><DashboardPage /></Guarded>} />
              <Route path="/kolejka" element={
                user.role === 'warehouse' ? <WarehouseQueuePage />
                : user.role === 'customs' ? <CustomsPage />
                : <QueuePage />} />
              <Route path="/kolejka/archiwum" element={
                <Guarded ok={canAccess(user.role, 'kolejka-arch')}><QueuePage archive /></Guarded>} />
              <Route path="/profil" element={<ProfilePage />} />
              <Route path="/moje-kolory" element={<MyColorsPage />} />
              <Route path="/kontenery/:id" element={<ContainerPage />} />
              <Route path="/dostawcy/:id" element={<SupplierPage />} />
              <Route path="/kontenery/:id/karta" element={<KartaRozladunkuPage />} />
              <Route path="/brama" element={
                <Guarded ok={['admin', 'logistics', 'warehouse'].includes(user.role)}>
                  <GatePage /></Guarded>} />
              <Route path="/awizacje/moje" element={
                <Guarded ok={['admin', 'logistics', 'forwarder'].includes(user.role)}>
                  <MyAvizosPage /></Guarded>} />
              <Route path="/awizacje/moje/:id" element={
                <Guarded ok={['admin', 'logistics', 'forwarder'].includes(user.role)}>
                  <MyAvizoAnswer /></Guarded>} />
              <Route path="/awizacje/propozycje" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <AvizoProposalsPage /></Guarded>} />
              <Route path="/kalendarz" element={
                <Guarded ok={canAccess(user.role, 'kalendarz')}><CalendarPage /></Guarded>} />
              <Route path="/zamowienia" element={
                <Guarded ok={canAccess(user.role, 'zamowienia')}><OrdersPage /></Guarded>} />
              <Route path="/zamowienia/:id" element={
                <Guarded ok={canAccess(user.role, 'zamowienia')}><OrderDetailPage /></Guarded>} />
              <Route path="/spedycja" element={
                <Guarded ok={canAccess(user.role, 'spedycja')}><ForwardingPage /></Guarded>} />
              <Route path="/zlecenia-spedycyjne" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <ForwardingRequestsPage /></Guarded>} />
              <Route path="/specjalna-troska" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics' || user.role === 'sales'}>
                  <SpecialCarePage /></Guarded>} />
              <Route path="/koszyk" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics' || user.role === 'purchasing'}>
                  <KoszykPage /></Guarded>} />
              <Route path="/import-sad" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics' || user.role === 'purchasing'}>
                  <SadImportPage /></Guarded>} />

              <Route path="/odprawa" element={
                <Guarded ok={canAccess(user.role, 'odprawa')}><CustomsPage /></Guarded>} />
              <Route path="/wyceny" element={
                <Guarded ok={canAccess(user.role, 'wyceny')}><QuotesPage /></Guarded>} />
              <Route path="/wywolania-dlt" element={
                <Guarded ok={['admin', 'logistics', 'warehouse'].includes(user.role)}>
                  <PalletCallsPage /></Guarded>} />
              <Route path="/analityka" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <AnalitykaPage /></Guarded>} />
              <Route path="/dziennik-zmian" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <ChangesFeedPage /></Guarded>} />
              <Route path="/master-data/:section?" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <MasterDataPage /></Guarded>} />
              <Route path="/sledzenie" element={
                <Guarded ok={canAccess(user.role, 'sledzenie')}><TrackingPage /></Guarded>} />
              <Route path="/reklamacje" element={
                <Guarded ok={canAccess(user.role, 'reklamacje')}><ComplaintsPage /></Guarded>} />
              <Route path="/reklamacje/statystyki" element={
                <Guarded ok={canAccess(user.role, 'reklamacje')}><ComplaintStatsPage /></Guarded>} />
              <Route path="/reklamacje/archiwum" element={
                <Guarded ok={canAccess(user.role, 'reklamacje')}><ComplaintsPage archive /></Guarded>} />
              <Route path="/reklamacje/:id" element={
                <Guarded ok={canAccess(user.role, 'reklamacje')}><ComplaintDetailPage /></Guarded>} />
              <Route path="/wiedza" element={
                <Guarded ok={seesKnowledge(user.role)}><WiedzaPage /></Guarded>} />
              <Route path="/administracja/:section?" element={
                <Guarded ok={canAccess(user.role, 'administracja')}><AdminPage /></Guarded>} />
              <Route path="/avizo/driver/:token" element={<AvizoDriverFormPage />} />
              <Route path="/avizo/:token" element={<AvizoFormPage />} />
              <Route path="/dlt/:token" element={<DltPage />} />
              {/* redirecty ze starych ścieżek — zakładki i linki dalej działają */}
              {Object.entries(LEGACY_REDIRECTS).map(([oldPath, newPath]) => (
                <Route key={oldPath} path={oldPath} element={<LegacyRedirect to={newPath} />} />
              ))}
              {/* Trasy tylko dla gościa (login/reset) — zalogowany trafia na nie tuż po
                  logowaniu (URL zostaje na /login); bez tego łapie je „*" → mylące 404. */}
              {['/login', '/forgot-password', '/reset-password'].map(path => (
                <Route key={path} path={path} element={<Navigate to="/" replace />} />
              ))}
              <Route path="*" element={<NotFound />} />
            </Routes>
            </Suspense>
            </ErrorBoundary>
            </div>
          </div>
        ) : (
          <Suspense fallback={pageFallback}>
          <Routes>
            <Route path="/avizo/driver/:token" element={<AvizoDriverFormPage />} />
            <Route path="/avizo/:token" element={<AvizoFormPage />} />
            <Route path="/dlt/:token" element={<DltPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            {/* ekran wejścia 2b jest jednocześnie stroną startową; stary marketingowy
                landing zostaje pod /o-systemie dla linków zewnętrznych */}
            <Route path="/" element={<LoginPage onLogin={reload} />} />
            <Route path="/o-systemie" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage onLogin={reload} />} />
            <Route path="*" element={<LoginPage onLogin={reload} />} />
          </Routes>
          </Suspense>
        )}
      </UserContext.Provider>
      </ConfirmProvider>
    </LangContext.Provider>
    </ToastProvider>
  )
}
