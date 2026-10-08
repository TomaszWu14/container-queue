// Aktualności na Pulpicie (spec 2026-10-01-aktualnosci-pulpit) — czysta logika bez Reacta:
// typy feedu, karty-wątki (jedna karta na kontener / statek), dzień lokalny, akcje wg rodzaju.
import { parseServerTs } from '../../dates'
import type { Notification } from '../../types'

export type NewsCategory = 'vessels' | 'customs' | 'orders' | 'deliveries' | 'messages' | 'system'
export const NEWS_CATEGORIES: NewsCategory[] = ['vessels', 'customs', 'orders', 'deliveries', 'messages', 'system']

export interface NewsItem extends Notification {
  category: NewsCategory
  priority: 'urgent' | 'normal' | 'info'
  thread_key: string
  containers: { id: number; container_no: string }[]
}
export interface FeedPage { items: NewsItem[]; pinned: NewsItem[]; has_more: boolean }

export const isFeedPage = (data: unknown): data is FeedPage =>
  !!data && typeof data === 'object' && Array.isArray((data as FeedPage).items)
    && Array.isArray((data as FeedPage).pinned)

/** Karta listy = wątek: najnowsza wiadomość + ile wcześniejszych z tego samego wątku. */
export interface NewsCard { item: NewsItem; earlier: number; unread: boolean }

export function toCards(items: NewsItem[], skip: ReadonlySet<number> = new Set()): NewsCard[] {
  const cards = new Map<string, NewsCard>()
  // najnowsze na górze także gdy kolejność id ≠ kolejność czasu (import, ręczne wpisy)
  const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))
  for (const item of sorted) {   // od najnowszych — pierwsze wystąpienie = karta
    if (skip.has(item.id)) continue
    const card = cards.get(item.thread_key)
    if (card) {
      card.earlier += 1
      card.unread ||= !item.is_read
    } else {
      cards.set(item.thread_key, { item, earlier: 0, unread: !item.is_read })
    }
  }
  return [...cards.values()]
}

// created_at z backendu to naiwny UTC — dzień liczymy w strefie przeglądarki (parseServerTs)
export function localDay(iso: string): string {
  const d = parseServerTs(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Przycisk akcji w panelu czytania: [klucz i18n, adres] wg rodzaju (null = brak akcji). */
export function newsAction(item: NewsItem): [string, string] | null {
  const vessel = /^Statek (.+?) (?:w |stoi )/.exec(item.title)?.[1]
  if (vessel) return ['newsActQueue', `/kolejka?q=${encodeURIComponent(vessel)}`]
  switch (item.category) {
    case 'customs': return ['newsActCustoms', '/odprawa']
    case 'orders': return item.kind.startsWith('freight') ? ['newsActForwarding', '/spedycja'] : ['newsActOrders', '/zamowienia']
    case 'deliveries': return ['newsActCalendar', '/kalendarz']
    case 'messages': return item.kind.startsWith('complaint') ? ['newsActComplaints', '/reklamacje'] : null
    default:
      if (item.kind === 'stale-import' || item.kind === 'marm') return ['newsActMasterData', '/master-data']
      if (item.kind === 'system-error') return ['newsActSystem', '/administracja/system']
      return null
  }
}
