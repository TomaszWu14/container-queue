// Kto jest teraz w aplikacji — awatary w górnym pasku, jak w plikach SharePoint (backend: app/presence.py).
// Karta co 30 s (i przy zmianie ekranu) wysyła sygnał: ekran + czy był ruch od poprzedniego sygnału.
// Widać tylko osoby online (ruch ≤ 5 min) — bez czasu bezczynności (decyzja 2026-10-01).
// Tylko role wewnętrzne — konta zewnętrzne ani nie widzą paska, ani nie wysyłają sygnału.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from './api'
import { useT } from './i18n'
import UserAvatar from './pages/watch/UserAvatar'
import { useVisibleInterval } from './useVisibleInterval'

export const PRESENCE_ROLES = ['admin', 'logistics', 'purchasing', 'sales']
const EVERY_MS = 30_000
const SHOWN = 5

export interface Here {
  user_id: number; name: string; role: string; path: string
  has_avatar: boolean
}

// ekran z adresu → etykieta (klucze i18n menu); dłuższe prefiksy najpierw
const SCREENS: [string, string][] = [
  ['/kolejka/archiwum', 'archive'], ['/kolejka', 'queue'], ['/pulpit', 'dashboard'],
  ['/kalendarz', 'calendar'], ['/sledzenie', 'trackingMap'], ['/spedycja', 'forwarding'],
  ['/zamowienia', 'orders'], ['/odprawa', 'customsModule'], ['/kontenery', 'pbContainer'],
  ['/administracja', 'admin'], ['/master-data', 'masterData'], ['/reklamacje', 'complaints'],
  ['/wiedza', 'kbModule'],
]

const valid = (rows: unknown): Here[] =>
  Array.isArray(rows) ? rows.filter((r): r is Here => !!r && typeof (r as Here).user_id === 'number') : []

export function PresenceBar({ userId }: { userId: number }) {
  const t = useT()
  const { pathname } = useLocation()
  const [rows, setRows] = useState<Here[]>([])
  const moved = useRef(true)

  useEffect(() => {
    const mark = () => { moved.current = true }
    const events = ['pointerdown', 'keydown', 'wheel', 'mousemove', 'touchstart'] as const
    events.forEach(e => window.addEventListener(e, mark, { passive: true }))
    return () => events.forEach(e => window.removeEventListener(e, mark))
  }, [])

  const send = useCallback(() => {
    const active = moved.current
    moved.current = false
    // Promise.resolve().then: także błąd synchroniczny (np. mock api bez post w testach stron) → catch
    Promise.resolve().then(() => api.post<Here[]>('/api/presence', { path: pathname, active }))
      .then(r => setRows(valid(r))).catch(() => { /* brak sieci — zostaje ostatni stan */ })
  }, [pathname])

  useEffect(() => {
    moved.current = true           // wejście na ekran to też aktywność
    send()
  }, [send])
  useVisibleInterval(send, EVERY_MS)   // ukryta karta nie pinguje; powrót = od razu

  const screen = (path: string) => {
    const hit = SCREENS.find(([p]) => path === p || path.startsWith(p + '/'))
    return hit ? t(hit[1]) : path
  }
  const describe = (r: Here) => [r.name, t('roleName_' + r.role), screen(r.path)].join(' · ')

  const others = rows.filter(r => r.user_id !== userId)
  if (!others.length) return null
  const shown = others.slice(0, SHOWN)
  const rest = others.slice(SHOWN)
  return (
    <ul className="pb-bar" aria-label={t('pbTitle')}>
      {shown.map(r => (
        <li key={r.user_id} className="pb-user on" title={describe(r)}>
          <UserAvatar userId={r.user_id} name={r.name} hasAvatar={r.has_avatar} size={28} />
          <span className="pb-dot" aria-hidden="true" />
          <span className="sr-only">{describe(r)}</span>
        </li>
      ))}
      {rest.length > 0 && (
        <li className="pb-user pb-more" title={rest.map(describe).join('\n')}>
          +{rest.length}<span className="sr-only">{rest.map(describe).join('; ')}</span>
        </li>
      )}
    </ul>
  )
}

/** Wylogowanie: zniknij z paska od razu (nie po 15 min). Błąd = trudno, wygaśnie sam. */
export const leavePresence = () =>
  Promise.resolve().then(() => api.post('/api/presence/leave', {})).catch(() => {})
