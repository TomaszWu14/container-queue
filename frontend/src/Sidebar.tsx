import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from './api'
import WorldClock from './clock'
import ThemeToggle from './ThemeToggle'
import NotificationsBell from './NotificationsBell'
import KnowledgePanel from './KnowledgePanel'
import { LANGS, Lang, LangContext, useT } from './i18n'
import { UserContext } from './userContext'
import { Archive, Calendar, ChartColumn, ChevronDown, DollarSign, FileText, Languages, LayoutDashboard, LogOut, MapPin, Menu, Palette, Rows3, Settings, ShieldCheck, TriangleAlert, Truck, X, type LucideIcon } from 'lucide-react'
import { formatDate } from './dates'
import { PRESENCE_ROLES, PresenceBar } from './PresenceBar'
import FullscreenToggle from './FullscreenToggle'
import { seesKnowledge } from './routing'
import { useVisibleInterval } from './useVisibleInterval'

// ikony menu: jedna biblioteka (lucide-react, inline SVG — zgodne z CSP), 16 px
const NAV_ICONS: Record<string, LucideIcon> = {
  queue: Rows3, dashboard: LayoutDashboard, calendar: Calendar, orders: FileText,
  forwarding: Truck, quotes: DollarSign, tracking: MapPin, complaints: TriangleAlert,
  archive: Archive, customs: ShieldCheck, admin: Settings, analytics: ChartColumn,
}
function NavIcon({ n }: { n: string }) {
  const I = NAV_ICONS[n]
  return <I className="nav-ico" size={16} strokeWidth={1.9} aria-hidden="true" />
}

// Data builda (ISO z obrazu) → "gg:mm:ss / dd.mm.rrrr" w czasie lokalnym.
function formatBuildTime(raw: string): string {
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return raw   // stary format / "unknown" — pokaż jak jest
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} / `
    + formatDate(`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`)
}


// Suma aktywnych kontenerów w zakresie roli (/api/containers/counts jest już zawężone).
// „DLT” w odpowiedzi to magazyn — podzbiór kontenerów Acme, nie spółka: bez pomijania
// liczył się dwa razy (admin: 288 Acme + 96 DLT = 384 zamiast 288).
export function activeTotal(counts: Record<string, number>): number {
  return Object.entries(counts).reduce((sum, [key, n]) => (key === 'DLT' ? sum : sum + n), 0)
}

export default function Sidebar({ onLogout }: { onLogout: () => void }) {
  const t = useT()
  const { user, reload } = useContext(UserContext)
  const { lang, setLang } = useContext(LangContext)
  const toggleWatchOnly = () => {
    api.patch('/api/auth/me/settings',
      { watch_only_notifications: !user?.watch_only_notifications }).then(reload)
  }
  const { pathname, search } = useLocation()
  // Wiedza kontekstowa (📘) mieszka w górnym pasku — scope wg bieżącej trasy.
  // Ekrany o stałym scope; karta kontenera ma własny, dynamiczny panel (zostaje inline).
  const kbScope = ([
    ['/kolejka', 'kolejka'], ['/odprawa', 'odprawa'],
    ['/spedycja', 'spedycja'], ['/wywolania-dlt', 'wywolania'],
  ] as const).find(([p]) => pathname === p || pathname.startsWith(`${p}/`))?.[1]
  const [total, setTotal] = useState<number | null>(null)
  const navRef = useRef<HTMLElement>(null)
  // menu górne: klik-sterowane (jedno otwarte naraz) zamiast CSS :hover, który
  // otwierał kilka naraz i nie działał na dotyku/kliku
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  // pozycja rozwijanego menu względem OKNA (position: fixed): .tn-menu przewija się w bok
  // (overflow-x: auto), a przewijany kontener przycinał menu absolutne — było niewidoczne
  const [dropAt, setDropAt] = useState<{ top: number; left: number } | null>(null)
  // telefon (≤ 900 px): menu jako panel pod paskiem, otwierany hamburgerem (audyt A14 C19 S9)
  const [mobileOpen, setMobileOpen] = useState(false)
  useEffect(() => { setOpenMenu(null); setMobileOpen(false) }, [pathname])  // zamknij po nawigacji
  useEffect(() => {
    if (!mobileOpen) return
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileOpen(false) }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [mobileOpen])
  useEffect(() => {   // pozycja z otwarcia nie pasuje po zmianie rozmiaru okna — zamknij
    const close = () => setOpenMenu(null)
    window.addEventListener('resize', close)
    return () => window.removeEventListener('resize', close)
  }, [])
  useEffect(() => {
    if (!openMenu) return
    const close = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) setOpenMenu(null)
    }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenMenu(null) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', onEsc)
    }
  }, [openMenu])

  // górny pasek jest sticky → sticky elementy kolejki muszą przyklejać się PONIŻEJ niego;
  // --topbar-h niesie realną wysokość paska (zmienia się przy zawijaniu na wąskich ekranach)
  useEffect(() => {
    const el = navRef.current
    if (!el) return
    const apply = () =>
      document.documentElement.style.setProperty('--topbar-h', `${el.offsetHeight}px`)
    apply()
    // ResizeObserver bywa niedostępny w środowisku testowym (jsdom) — wtedy sama wartość startowa
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(apply)
    observer.observe(el)
    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty('--topbar-h')
    }
  }, [])

  // sumaryczny licznik aktywnych kontenerów (karta statusu + plakietka „Kolejka")
  // dotąd pobierany raz po zalogowaniu — teraz w rytmie dzwonka (60 s, tylko widoczna karta)
  const refreshTotal = useCallback(() => {
    api.get<Record<string, number>>('/api/containers/counts')
      .then(c => setTotal(activeTotal(c)))
      .catch(() => setTotal(null))
  }, [])
  useEffect(() => { refreshTotal() }, [refreshTotal])
  useVisibleInterval(refreshTotal, 60_000)

  // znacznik wersji/builda — żeby było widać, czy panel chodzi na świeżym obrazie
  const [build, setBuild] = useState<{ version: string; built_at: string } | null>(null)
  useEffect(() => {
    api.get<{ version?: string; built_at?: string }>('/api/health')
      .then(h => setBuild({ version: h.version || 'dev', built_at: h.built_at || '' }))
      .catch(() => {})
  }, [])

  const initials = (user?.full_name || user?.login || '?')
    .split(/\s+/).map(s => s[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()

  const role = user?.role
  const not = (...roles: string[]) => !roles.includes(role || '')
  const some = (...roles: string[]) => roles.includes(role || '')

  // Menu: najczęstsze ekrany jako GŁÓWNE linki (jedno kliknięcie), reszta w dwóch
  // grupach rozwijanych. Link renderuje się tylko, gdy rola ma dostęp.
  type NavItem = { to: string; end?: boolean; icon: string; label: string; show: boolean }
  const primary: NavItem[] = [
    // /pulpit zamiast '/': dla ról startujących w kolejce '/' robi redirect
    { to: '/pulpit', icon: 'dashboard', label: t('dashboard'), show: not('warehouse', 'customs', 'purchasing', 'sales') },
    { to: '/kalendarz', icon: 'calendar', label: t('calendar'), show: not('customs', 'purchasing') },
    { to: '/sledzenie', icon: 'tracking', label: t('trackingMap'), show: not('customs', 'purchasing') },
    { to: '/spedycja', icon: 'forwarding', label: t('forwarding'), show: not('warehouse', 'customs', 'sales') },
  ]
  const sections: { label: string; links: NavItem[] }[] = [
    { label: 'Operacje', links: [
      { to: '/zamowienia', icon: 'orders', label: t('orders'), show: not('forwarder', 'warehouse', 'customs', 'sales') },
      { to: '/zlecenia-spedycyjne', icon: 'forwarding', label: t('fwqTitle'), show: some('admin', 'logistics') },
      { to: '/koszyk', icon: 'orders', label: t('koszykTitle'), show: some('admin', 'logistics', 'purchasing') },
      { to: '/awizacje/moje', icon: 'calendar', label: t('myAvizosTitle'), show: some('forwarder') },
      { to: '/awizacje/propozycje', icon: 'calendar', label: t('avrTitle'), show: some('admin', 'logistics') },
      { to: '/brama', icon: 'forwarding', label: t('gateTitle'), show: some('admin', 'logistics', 'warehouse') },
      { to: '/odprawa', icon: 'customs', label: t('customsModule'), show: some('admin', 'logistics') },
      { to: '/import-sad', icon: 'customs', label: t('sadImpNav'), show: some('admin', 'logistics', 'purchasing') },
      { to: '/specjalna-troska', icon: 'complaints', label: t('careModule'), show: some('admin', 'logistics', 'sales') },
      { to: '/wywolania-dlt', icon: 'orders', label: 'Wywołania-DLT', show: some('admin', 'logistics', 'warehouse') },
      { to: '/reklamacje', icon: 'complaints', label: t('complaints'), show: not('customs', 'purchasing', 'sales') },
    ] },
    { label: 'Analiza', links: [
      // „Analiza rozładunków" = zakładka analysis kolejki (tylko konta widzące wszystkie spółki)
      { to: '/kolejka?spolka=analysis', icon: 'analytics', label: t('moduleAnalysis'),
        show: role === 'admin' || !!user?.view_all_companies },
      { to: '/analityka', icon: 'analytics', label: 'Analityka', show: some('admin', 'logistics') },
      { to: '/wyceny', icon: 'quotes', label: t('navQuotes'), show: not('warehouse', 'customs', 'purchasing', 'sales') },
      { to: '/dziennik-zmian', icon: 'archive', label: t('changesFeedTitle'), show: some('admin', 'logistics') },
      { to: '/kolejka/archiwum', icon: 'archive', label: t('archive'), show: not('warehouse', 'customs', 'purchasing', 'sales') },
      { to: '/master-data', icon: 'archive', label: t('masterData'), show: some('admin', 'logistics') },
      // Wiedza: role wewnętrzne (ACL-001) — spedytor/agencja celna dostawali 403 jako „Brak tematów”
      { to: '/wiedza', icon: 'orders', label: t('kbModule'), show: seesKnowledge(role) },
    ] },
  ]
  const userOpen = openMenu === '__user'

  return (
    <header className={`topnav${mobileOpen ? ' mobile-open' : ''}`} ref={navRef}>
      <div className="tn-brand">
        <span className="sb-logo">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.8" aria-hidden="true">
            <rect x="1" y="8" width="15" height="9" rx="1" />
            <path d="M4 8v9M7.5 8v9M11 8v9M16 11h4l3 3v3h-2.5" />
            <circle cx="6" cy="19.5" r="1.6" /><circle cx="18.5" cy="19.5" r="1.6" />
          </svg>
        </span>
        <span className="sb-brand-txt"><b>KOLEJKA</b><small>CONTAINER FLOW</small></span>
      </div>

      <nav className="tn-menu" id="tn-menu">
        {role === 'customs' ? (
          <NavLink to="/kolejka" end className="tn-link tn-primary"
                   title={t('customsModule')} aria-label={t('customsModule')}>
            <NavIcon n="customs" /><span className="tn-label">{t('customsModule')}</span>
            {total != null && <span className="sb-badge" title={t('navQueueCountHint')}>{total}</span>}
          </NavLink>
        ) : (
          <NavLink to="/kolejka" className="tn-link tn-primary" data-tour="kolejka"
                   title={t('queue')} aria-label={t('queue')}>
            <NavIcon n="queue" /><span className="tn-label">{t('queue')}</span>
            {total != null && <span className="sb-badge" title={t('navQueueCountHint')}>{total}</span>}
          </NavLink>
        )}

        {primary.filter(l => l.show).map(l => (
          <NavLink key={l.to} to={l.to} end={l.end} className="tn-link"
                   title={l.label} aria-label={l.label}
                   data-tour={l.to === '/sledzenie' ? 'sledzenie' : undefined}>
            <NavIcon n={l.icon} /><span className="tn-label">{l.label}</span>
          </NavLink>
        ))}

        {sections.map(sec => {
          const links = sec.links.filter(l => l.show)
          if (!links.length) return null
          const open = openMenu === sec.label
          // B14: na stronie z grupy („Zamówienia” w Operacjach) grupa jest podświetlona jak aktywny link
          const current = links.some(l => {
            const [path, query] = l.to.split('?')
            return (pathname === path || pathname.startsWith(`${path}/`)) && (!query || search.includes(query))
          })
          return (
            <div className={`tn-group${open ? ' open' : ''}${current ? ' has-active' : ''}`} key={sec.label}>
              <button type="button" className="tn-group-btn" aria-expanded={open}
                      onClick={e => {
                        const r = e.currentTarget.getBoundingClientRect()
                        setDropAt({ top: Math.round(r.bottom + 4), left: Math.round(r.left) })  // pełne px = ostry tekst
                        setOpenMenu(open ? null : sec.label)
                      }}>
                {sec.label}<ChevronDown className="tn-caret" size={16} aria-hidden="true" />
              </button>
              <div className="tn-drop"
                   style={open && dropAt ? { position: 'fixed', top: dropAt.top, left: dropAt.left } : undefined}>
                {links.map(l => (
                  <NavLink key={l.to} to={l.to} end={l.end}
                           // NavLink porównuje tylko ścieżkę — link z ?query aktywny tylko przy tym query
                           className={({ isActive }) => `tn-drop-link${isActive
                             && (!l.to.includes('?') || search.includes(l.to.split('?')[1])) ? ' active' : ''}`}
                           onClick={() => setOpenMenu(null)}>
                    <NavIcon n={l.icon} /><span>{l.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          )
        })}

        {role === 'admin' && (
          <NavLink to="/administracja" className="tn-link" title={t('admin')} aria-label={t('admin')}>
            <NavIcon n="admin" /><span className="tn-label">{t('admin')}</span>
          </NavLink>
        )}
      </nav>

      <div className="tn-right">
        {/* pigułki firm usunięte — wybór spółki jest w wierszu „Wybór firmy" w kolejce
            (karty z licznikami), duplikat na pasku był zbędny */}
        {user && PRESENCE_ROLES.includes(user.role) && <PresenceBar userId={user.id} />}
        <span className="tn-status" title={total != null ? `${total} ${t('sbInQueue')}` : t('sbStatus')}>
          <span className="sb-dot" /><span className="tn-online">online</span>
        </span>
        {kbScope && <KnowledgePanel variant="topbar" scopes={[{ scope_type: 'screen', scope_key: kbScope }]} />}
        <WorldClock />
        <FullscreenToggle />
        <NotificationsBell />
        {/* menu użytkownika: profil, preferencje i wylogowanie w jednym miejscu —
            wcześniej 5 kontrolek w pasku zawijało nagłówek do dwóch linii */}
        <div className={`tn-group tn-usermenu${userOpen ? ' open' : ''}`}>
          <button type="button" className="tn-user" aria-expanded={userOpen}
                  title={[user?.full_name || user?.login,
                          build && `${t('buildStamp')} · v${build.version} · ${formatBuildTime(build.built_at)}`]
                    .filter(Boolean).join(' — ')}
                  onClick={() => setOpenMenu(userOpen ? null : '__user')}>
            <span className="sb-avatar">{initials}</span>
            <span className="sb-user-txt">
              <b>{user?.full_name || user?.login}</b>
              {/* rola zamiast czasu builda (brak BUILD_TIME dawał surowe „unknown”); build w podpowiedzi */}
              {user?.role && <small>{t('roleName_' + user.role)}</small>}
            </span>
            <ChevronDown className="tn-caret" size={16} aria-hidden="true" />
          </button>
          <div className="tn-drop tn-drop-right">
            {/* C25: kto jest zalogowany (pod 1600 px przycisk pokazuje sam awatar); pozycje z ikoną
                i tekstem. „Tylko obserwowane” to preferencja POWIADOMIEŃ konta, nie filtr kolejki. */}
            <div className="tn-drop-head">
              <b>{user?.full_name || user?.login}</b>
              {user?.role && <small>{t('roleName_' + user.role)}</small>}
            </div>
            <NavLink to="/profil" className="tn-drop-link" onClick={() => setOpenMenu(null)}>
              <ShieldCheck size={16} aria-hidden="true" /><span>{t('profileSecurity')}</span>
            </NavLink>
            <NavLink to="/moje-kolory" className="tn-drop-link" onClick={() => setOpenMenu(null)}>
              <Palette size={16} aria-hidden="true" /><span>{t('colMyTitle')}</span>
            </NavLink>
            <label className="tn-drop-link tn-watch-only" title={t('watchOnlyNotificationsHint')}>
              <input type="checkbox" checked={!!user?.watch_only_notifications}
                     onChange={toggleWatchOnly} />
              <span>{t('umWatchOnly')}</span>
            </label>
            <label className="tn-drop-link tn-lang">
              <Languages size={16} aria-hidden="true" /><span>{t('umLanguage')}</span>
              <select className="sb-lang" value={lang} aria-label={t('umLanguage')}
                      onChange={e => setLang(e.target.value as Lang)}>
                {LANGS.map(l => <option key={l} value={l}>{l.toUpperCase()}</option>)}
              </select>
            </label>
            <ThemeToggle labelled />
            <button className="tn-drop-link tn-logout-item" onClick={onLogout}>
              <LogOut size={16} aria-hidden="true" />{t('logout')}
            </button>
          </div>
        </div>
        <button type="button" className="tn-icon-btn tn-burger" aria-controls="tn-menu"
                aria-expanded={mobileOpen} aria-label={t(mobileOpen ? 'navMenuClose' : 'navMenuOpen')}
                onClick={() => setMobileOpen(o => !o)}>
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </header>
  )
}
