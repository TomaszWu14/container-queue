import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import { useUser } from './App'
import { NEWS_CHANGED } from './pages/news/NewsFeed'
import { canAccess } from './routing'
import { useT } from './i18n'
import { formatDateTime } from './dates'
import type { Notification } from './types'
import { useVisibleInterval } from './useVisibleInterval'
import { Bell } from 'lucide-react'

type DropdownPos = { left: number; width: number; maxH: number; top?: number; bottom?: number }

const DD_W = 360, DD_GAP = 8, DD_MARGIN = 8, DD_MAX_H = 420, DD_MIN_H = 140

// Umieszcza panel powiadomień obok dzwonka w układzie współrzędnych okna:
// poziomo z prawej (sidebar jest po lewej), z odbiciem na drugą stronę i dociśnięciem
// do krawędzi; pionowo tam, gdzie więcej miejsca — dzwonek stoi na dole sidebara,
// więc otwieranie zawsze w dół wyjechałoby pod ekran.
function placeDropdown(r: DOMRect): DropdownPos {
  const vw = window.innerWidth, vh = window.innerHeight
  const width = Math.min(DD_W, vw - 2 * DD_MARGIN)

  let left = r.right + DD_GAP
  if (left + width > vw - DD_MARGIN) left = r.left - DD_GAP - width   // nie mieści się z prawej → z lewej
  left = Math.min(Math.max(DD_MARGIN, left), Math.max(DD_MARGIN, vw - DD_MARGIN - width))

  const below = vh - r.bottom - DD_GAP - DD_MARGIN
  const above = r.top - DD_GAP - DD_MARGIN
  const down = below >= above
  const maxH = Math.max(DD_MIN_H, Math.min(DD_MAX_H, down ? below : above))
  left = Math.round(left)   // pełne piksele: ułamkowa pozycja rozmywa tekst przy 125/150%
  return down
    ? { left, width, maxH, top: Math.round(r.bottom + DD_GAP) }
    : { left, width, maxH, bottom: Math.round(vh - r.top + DD_GAP) }
}


export default function NotificationsBell() {
  const t = useT()
  const navigate = useNavigate()
  const user = useUser()
  // Aktualności (spec 2026-10-01) żyją na Pulpicie — role bez Pulpitu: jak dawniej, do kontenera
  const hasNews = !!user && canAccess(user.role, 'dashboard')
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notification[]>([])
  const wrapRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<DropdownPos | null>(null)

  // Panel liczy pozycję sam i renderuje się jako position:fixed, bo dzwonek siedzi
  // w .sidebar, który ma overflow-y:auto — a to (wg CSS overflow) wymusza
  // overflow-x:auto i przycięłoby zwykły position:absolute do 252px sidebara.
  const place = useCallback(() => {
    const el = wrapRef.current
    if (!el) return
    setPos(placeDropdown(el.getBoundingClientRect()))
  }, [])

  const refreshCount = useCallback(() => {
    api.get<{ count: number }>('/api/notifications/unread-count')
      .then(r => setCount(r.count)).catch(() => {})
  }, [])

  useEffect(() => {
    refreshCount()
    window.addEventListener(NEWS_CHANGED, refreshCount)   // przeczytane w Aktualnościach
    return () => window.removeEventListener(NEWS_CHANGED, refreshCount)
  }, [refreshCount])
  useVisibleInterval(refreshCount, 60_000)   // ukryta karta nie odpytuje

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const toggle = async () => {
    if (!open) {
      place()
      const list = await api.get<Notification[]>('/api/notifications?limit=10').catch(() => [])
      setItems(list)
    }
    setOpen(o => !o)
  }

  // pozycja jest wyliczona, nie deklaratywna — po resize/scroll trzeba ją odświeżyć
  useEffect(() => {
    if (!open) return
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, place])

  const markAll = async () => {
    try {
      await api.post('/api/notifications/read', {})
      setCount(0)
      setItems(list => list.map(n => ({ ...n, is_read: true })))
    } catch { /* nieudane oznaczenie nie może wywrócić panelu */ }
  }

  const openItem = async (notification: Notification) => {
    // oznaczenie „przeczytane" jest best-effort — nawigacja musi zadziałać niezależnie
    await api.post(`/api/notifications/read?notification_id=${notification.id}`, {})
      .then(refreshCount).catch(() => {})
    setOpen(false)
    if (hasNews) navigate(`/pulpit?wiadomosc=${notification.id}`)   // panel czytania Aktualności
    else if (notification.container_id) navigate(`/kontenery/${notification.container_id}`)
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button type="button" className="tn-icon-btn" onClick={toggle} title={t('notifications')}
              aria-label={t('notifications')} style={{ position: 'relative' }}>
        <Bell size={20} aria-hidden="true" style={{ display: 'block' }} />
        {count > 0 && (
          <span style={{
            position: 'absolute', top: -6, right: -8, background: '#d92d20', color: '#fff',
            borderRadius: 10, fontSize: 11, padding: '1px 5px', fontWeight: 700,
          }}>{count > 99 ? '99+' : count}</span>
        )}
      </button>
      {open && pos && (
        <div style={{
          position: 'fixed', left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.width,
          background: '#fff', color: '#1c2733', borderRadius: 10, zIndex: 70,  // > .sidebar (60)
          boxShadow: '0 12px 40px rgba(0,0,0,0.3)', maxHeight: pos.maxH, overflow: 'auto',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '8px 12px', borderBottom: '1px solid #dde3ec' }}>
            <b>{t('notifications')}</b>
            <button className="btn small secondary" onClick={markAll}>{t('markAllRead')}</button>
          </div>
          {items.length === 0 && (
            <p style={{ padding: 12, color: 'var(--muted)', margin: 0 }}>{t('noNotifications')}</p>
          )}
          {items.map(notification => (
            <div key={notification.id} role="button" tabIndex={0}
                 onClick={() => openItem(notification)}
                 onKeyDown={e => {
                   if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openItem(notification) }
                 }} style={{
              padding: '8px 12px', borderBottom: '1px solid #eef2f7', cursor: 'pointer',
              background: notification.is_read ? '#fff' : '#eaf2ff', fontSize: 14,
            }}>
              <div style={{ fontWeight: notification.is_read ? 400 : 600 }}>{notification.title}</div>
              {notification.body && (
                <div style={{ color: 'var(--muted)', whiteSpace: 'pre-wrap' }}>
                  {notification.body.slice(0, 140)}
                </div>
              )}
              <div style={{ color: 'var(--muted)', fontSize: 12 }}>
                {formatDateTime(notification.created_at)}
              </div>
            </div>
          ))}
          {hasNews && (
            <button type="button" className="btn small secondary" style={{ display: 'block', margin: '8px auto' }}
                    onClick={() => { setOpen(false); navigate('/pulpit#aktualnosci') }}>{t('newsSeeAll')}</button>
          )}
        </div>
      )}
    </div>
  )
}
