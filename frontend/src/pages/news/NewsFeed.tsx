// Aktualności na Pulpicie (spec 2026-10-01-aktualnosci-pulpit) jako kolumny tematów (kanban):
// Statki | Odprawa | Zamówienia | Dostawy | Wiadomości | System — każda z własną listą wątków
// i „załaduj starsze” (6 zapytań feedu równolegle, po kategorii). Filtry „tylko nieprzeczytane”
// i szukaj działają na wszystkie kolumny; pilne nieprzeczytane jako pasek nad kolumnami.
// Klik w kartę / `?wiadomosc=<id>` (dzwonek) otwiera szufladę z prawej. Przeczytana = otwarta.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import NewsColumn, { NewsCardView } from './NewsColumn'
import { isFeedPage, NEWS_CATEGORIES, toCards } from './newsModel'
import type { NewsCard, NewsCategory, NewsItem } from './newsModel'
import { NewsDrawer } from './NewsReader'

/** Dzwonek odświeża licznik, gdy Aktualności zmienią stan przeczytania. */
export const NEWS_CHANGED = 'news:changed'
const changed = () => window.dispatchEvent(new Event(NEWS_CHANGED))

type Status = 'all' | 'unread' | 'read'
type Priority = '' | 'urgent' | 'normal' | 'info'
const STATUSES: [Status, string][] = [['all', 'newsStatusAll'], ['unread', 'newsUnreadOnly'], ['read', 'newsStatusRead']]

interface Col { items: NewsItem[]; hasMore: boolean; busy: boolean }
type Cols = Record<NewsCategory, Col>
const emptyCols = (): Cols =>
  Object.fromEntries(NEWS_CATEGORIES.map(c => [c, { items: [], hasMore: false, busy: false }])) as unknown as Cols

export default function NewsFeed() {
  const t = useT()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState<Status>('all')
  const [priority, setPriority] = useState<Priority>('')
  const [hidden, setHidden] = useState<ReadonlySet<NewsCategory>>(new Set())
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [cols, setCols] = useState<Cols>(emptyCols)
  const [pinned, setPinned] = useState<NewsItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<NewsItem | null>(null)
  const section = useRef<HTMLElement>(null)
  const seq = useRef(0)   // starsze odpowiedzi (zmiana filtrów w trakcie) nie nadpisują nowszych

  const url = useCallback((cat: NewsCategory, before?: number) => {
    const p = new URLSearchParams({ limit: '50', category: cat })
    if (status !== 'all') p.set('status', status)
    if (priority) p.set('priority', priority)
    if (query) p.set('q', query)
    if (before) p.set('before_id', String(before))
    return `/api/notifications/feed?${p}`
  }, [status, priority, query])

  const loadAll = useCallback(() => {
    const my = ++seq.current
    setError('')
    Promise.all(NEWS_CATEGORIES.map(c => api.get(url(c)))).then(pages => {
      if (my !== seq.current) return
      const next = emptyCols()
      pages.forEach((r, i) => {
        if (isFeedPage(r)) next[NEWS_CATEGORIES[i]] = { items: r.items, hasMore: r.has_more, busy: false }
      })
      setCols(next)
      if (isFeedPage(pages[0])) setPinned(pages[0].pinned)
      setLoaded(true)
    }).catch(e => { if (my === seq.current) setError(errorMessage(e)) })
  }, [url])
  useEffect(() => loadAll(), [loadAll])

  const loadMore = (cat: NewsCategory) => {
    const col = cols[cat]
    const my = seq.current
    setCols(prev => ({ ...prev, [cat]: { ...prev[cat], busy: true } }))
    api.get(url(cat, col.items[col.items.length - 1]?.id)).then(r => {
      if (my !== seq.current || !isFeedPage(r)) return
      setCols(prev => ({ ...prev, [cat]: { items: [...prev[cat].items, ...r.items], hasMore: r.has_more, busy: false } }))
    }).catch(e => {
      setError(errorMessage(e))
      setCols(prev => ({ ...prev, [cat]: { ...prev[cat], busy: false } }))
    })
  }

  const patch = (id: number, is_read: boolean) => {
    const fix = (list: NewsItem[]) => list.map(n => (n.id === id ? { ...n, is_read } : n))
    setCols(prev => Object.fromEntries(NEWS_CATEGORIES.map(c => [c, { ...prev[c], items: fix(prev[c].items) }])) as unknown as Cols)
    setPinned(fix)
  }

  const open = useCallback(async (id: number) => {
    let item = [...pinned, ...NEWS_CATEGORIES.flatMap(c => cols[c].items)].find(n => n.id === id) ?? null
    if (!item) {   // spoza załadowanej strony (link z dzwonka) — wątek ją zawiera
      const r = await api.get<{ items: NewsItem[] }>(`/api/notifications/${id}/thread`).catch(() => null)
      item = r?.items?.find(n => n.id === id) ?? null
    }
    if (!item) return
    setSelected({ ...item, is_read: true })
    if (!item.is_read) {
      // optymistycznie „przeczytane”; błąd zapisu → przywróć, inaczej po odświeżeniu wraca nieprzeczytane
      api.post(`/api/notifications/read?notification_id=${id}`, {}).then(changed).catch(() => patch(id, false))
      patch(id, true)
    }
  }, [cols, pinned])
  const close = useCallback(() => setSelected(null), [])

  // „Zobacz wszystkie” z dzwonka: /pulpit#aktualnosci → przewiń do sekcji
  const { hash } = useLocation()
  useEffect(() => {
    if (hash === '#aktualnosci') section.current?.scrollIntoView?.({ block: 'start' })
  }, [hash])

  // klik w dymku dzwonka: /pulpit?wiadomosc=<id> → przewiń do sekcji i otwórz szufladę
  const linked = Number(params.get('wiadomosc')) || null
  useEffect(() => {
    if (!linked) return
    open(linked).then(() => section.current?.scrollIntoView?.({ block: 'start' }))
    params.delete('wiadomosc')
    setParams(params, { replace: true })
  }, [linked])   // eslint-disable-line react-hooks/exhaustive-deps

  const markUnread = (item: NewsItem) => {
    api.post(`/api/notifications/unread?notification_id=${item.id}`, {}).then(changed).catch(() => {})
    patch(item.id, false)
    setSelected(null)
  }
  // przełącznik na karcie bez otwierania: „przeczytana” obejmuje cały załadowany wątek karty
  const toggleRead = (card: NewsCard) => {
    if (card.unread) {
      const ids = [...pinned, ...NEWS_CATEGORIES.flatMap(c => cols[c].items)]
        .filter(n => n.thread_key === card.item.thread_key && !n.is_read).map(n => n.id)
      new Set(ids).forEach(id => {
        patch(id, true)
        api.post(`/api/notifications/read?notification_id=${id}`, {}).then(changed).catch(() => patch(id, false))
      })
    } else {
      patch(card.item.id, false)
      api.post(`/api/notifications/unread?notification_id=${card.item.id}`, {}).then(changed)
        .catch(() => patch(card.item.id, true))
    }
  }
  const toggleCat = (c: NewsCategory) => setHidden(prev => {
    const next = new Set(prev)
    if (!next.delete(c)) next.add(c)
    return next
  })

  const markAll = () => {
    api.post('/api/notifications/read', {}).then(() => { changed(); loadAll() }).catch(e => setError(errorMessage(e)))
  }

  const pinnedUnread = useMemo(() => pinned.filter(p => !p.is_read), [pinned])
  const pinnedIds = useMemo(() => new Set(pinnedUnread.map(p => p.id)), [pinnedUnread])
  const selectedId = selected?.id ?? null

  return (
    <section ref={section} id="aktualnosci" className="panel news" aria-labelledby="news-h">
      <div className="dash-card-head news-head">
        <h2 id="news-h" className="dash-card-title">{t('newsTitle')}</h2>
        <span className="spacer" />
        <div className="news-seg" role="group" aria-label={t('newsFilterStatus')}>
          {STATUSES.map(([value, key]) => (
            <button key={value} type="button" aria-pressed={status === value}
                    onClick={() => setStatus(value)}>{t(key)}</button>
          ))}
        </div>
        <select className="news-prio" aria-label={t('newsFilterPriority')} value={priority}
                onChange={e => setPriority(e.target.value as Priority)}>
          <option value="">{t('newsPrioAll')}</option>
          {(['urgent', 'normal', 'info'] as const).map(p => <option key={p} value={p}>{t(`newsPrio_${p}`)}</option>)}
        </select>
        <input type="search" className="news-search" value={q} placeholder={t('newsSearch')} aria-label={t('newsSearch')}
               onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') setQuery(q.trim()) }}
               onBlur={() => setQuery(q.trim())} />
        <button type="button" className="btn small secondary" onClick={markAll}>{t('markAllRead')}</button>
      </div>
      <div className="news-chips" role="group" aria-label={t('newsFilterCats')}>
        {NEWS_CATEGORIES.map(c => (
          <button key={c} type="button" className={`news-chip nc-${c}`} aria-pressed={!hidden.has(c)}
                  onClick={() => toggleCat(c)}>{t(`newsCat_${c}`)}</button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {pinnedUnread.length > 0 && (
        <div className="news-pinned" role="group" aria-label={t('newsPinned')}>
          <h3 className="news-pinned-h">{t('newsPinned')}</h3>
          <ul>{pinnedUnread.map(item => (
            <NewsCardView key={item.id} card={{ item, earlier: 0, unread: true }} showCat
                          active={selectedId === item.id} onOpen={open} onToggleRead={toggleRead} />
          ))}</ul>
        </div>
      )}
      <div className="news-cols">
        {NEWS_CATEGORIES.filter(c => !hidden.has(c)).map(c => {
          const { items, hasMore, busy } = cols[c]
          return (
            <NewsColumn key={c} cat={c} cards={toCards(items, pinnedIds)} unread={items.filter(n => !n.is_read).length}
                        hasMore={hasMore} busy={busy} loaded={loaded} selectedId={selectedId}
                        onOpen={open} onMore={() => loadMore(c)} onToggleRead={toggleRead} />
          )
        })}
      </div>
      {selected && <NewsDrawer item={selected} onClose={close} onSelect={open} onUnread={markUnread} />}
    </section>
  )
}
