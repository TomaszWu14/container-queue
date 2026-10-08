// Panel czytania Aktualności: pełna treść, kontenery z treści (linki), akcja wg rodzaju,
// mini-karta kontenera (gdy jeden), oś zdarzeń wątku (ten sam kontener / statek).
// NewsDrawer = ta sama treść w szufladzie wysuwanej z prawej (jak w kolejce).
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { XIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { formatDate, formatDateTime } from '../../dates'
import { useT } from '../../i18n'
import type { Container } from '../../types'
import { CATEGORY_ICON } from './newsMeta'
import { newsAction } from './newsModel'
import type { NewsItem } from './newsModel'

function MiniCard({ id }: { id: number }) {
  const t = useT()
  const [c, setC] = useState<Container | null>(null)
  useEffect(() => {
    api.get<Container>(`/api/containers/${id}`)
      .then(r => setC(r && typeof r === 'object' && 'container_no' in r ? r : null)).catch(() => setC(null))
  }, [id])
  if (!c) return null
  return (
    <Link to={`/kontenery/${c.id}`} className="news-mini">
      <b className="mono">{c.container_no}</b>
      <span className={`badge st-${c.status}`}>{t(`st_${c.status}`)}</span>
      <span className="muted">{[c.supplier_name, c.vessel, c.eta && `ETA ${formatDate(c.eta)}`, c.warehouse_name]
        .filter(Boolean).join(' · ')}</span>
    </Link>
  )
}

export default function NewsReader({ item, onSelect, onUnread }: {
  item: NewsItem
  onSelect: (id: number) => void
  onUnread: (item: NewsItem) => void
}) {
  const t = useT()
  const [thread, setThread] = useState<NewsItem[]>([])
  useEffect(() => {
    api.get<{ items: NewsItem[] }>(`/api/notifications/${item.id}/thread`)
      .then(r => setThread(Array.isArray(r?.items) ? r.items : [])).catch(() => setThread([]))
  }, [item.id])
  const Icon = CATEGORY_ICON[item.category]
  const action = newsAction(item)
  const single = item.containers.length === 1 ? item.containers[0].id : item.container_id
  const related = thread.filter(r => r.id !== item.id)
  return (
    <article className={`news-reader pr-${item.priority}`} aria-labelledby="news-reader-title">
      <div className="news-meta">
        <span className={`news-cat nc-${item.category}`}><Icon size={14} aria-hidden="true" /> {t(`newsCat_${item.category}`)}</span>
        {item.priority === 'urgent' && <span className="badge delayed">{t('newsUrgent')}</span>}
        <span className="muted">{formatDateTime(item.created_at)}</span>
        <span className="spacer" />
        <button type="button" className="btn small secondary" onClick={() => onUnread(item)}>{t('newsMarkUnread')}</button>
      </div>
      <h2 id="news-reader-title" className="news-title">{item.title}</h2>
      {item.body && <p className="news-body">{item.body}</p>}
      {item.containers.length > 0 && (
        <div className="news-chips" aria-label={t('newsContainers')}>
          {item.containers.map(c => (
            <Link key={c.id} to={`/kontenery/${c.id}`} className="news-chip mono">{c.container_no}</Link>
          ))}
        </div>
      )}
      {action && <Link to={action[1]} className="btn small news-action">{t(action[0])}</Link>}
      {single && <MiniCard id={single} />}
      {related.length > 0 && (
        <section className="news-thread">
          <h3>{t('newsThread')} ({related.length})</h3>
          <ol>
            {related.map(r => (
              <li key={r.id}>
                <button type="button" className={`news-thread-item${r.is_read ? '' : ' unread'}`} onClick={() => onSelect(r.id)}>
                  <span className="muted mono">{formatDateTime(r.created_at)}</span> {r.title}
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  )
}

/** Szuflada z prawej nad kolumnami: ✕ / Esc / klik w tło zamyka; fokus na ✕, po zamknięciu wraca. */
export function NewsDrawer({ item, onClose, onSelect, onUnread }: {
  item: NewsItem
  onClose: () => void
  onSelect: (id: number) => void
  onUnread: (item: NewsItem) => void
}) {
  const t = useT()
  const closeBtn = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const back = document.activeElement as HTMLElement | null
    closeBtn.current?.focus()
    return () => back?.focus?.()
  }, [])
  // layout — nasłuch istnieje od commitu z szufladą (wzór QueueDrawer, inaczej Esc bywa gubione)
  useLayoutEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer news-drawer" role="dialog" aria-modal="true" aria-labelledby="news-reader-title">
        <div className="drawer-head">
          <span className="muted">{t('newsTitle')}</span>
          <button ref={closeBtn} type="button" className="btn small secondary" onClick={onClose} aria-label={t('newsClose')}>
            <XIcon size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="drawer-body">
          <NewsReader item={item} onSelect={onSelect} onUnread={onUnread} />
        </div>
      </aside>
    </>
  )
}
