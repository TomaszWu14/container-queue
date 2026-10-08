// Kolumna tematu Aktualności (kanban): nagłówek (ikona, nazwa, licznik nieprzeczytanych),
// własna przewijana lista kart-wątków i „Załaduj starsze” tej kategorii. Pusta = wąski pasek.
import { formatDateTime, todayISO } from '../../dates'
import { useT } from '../../i18n'
import { CATEGORY_ICON } from './newsMeta'
import { localDay } from './newsModel'
import type { NewsCard, NewsCategory } from './newsModel'

function yesterdayISO(): string {
  const d = new Date(`${todayISO()}T12:00:00`)
  d.setDate(d.getDate() - 1)
  return localDay(d.toISOString())
}

/** Karta-wątek: dzień jako „Dziś/Wczoraj HH:MM” albo pełna data z godziną. */
export function NewsCardView({ card, active, showCat, onOpen, onToggleRead }: {
  card: NewsCard
  active: boolean
  showCat?: boolean     // kategoria na karcie tylko w pasku przypiętych (w kolumnie to nagłówek)
  onOpen: (id: number) => void
  onToggleRead?: (card: NewsCard) => void   // przełącznik obok karty (bez otwierania szuflady)
}) {
  const t = useT()
  const { item, earlier, unread } = card
  const Icon = CATEGORY_ICON[item.category]
  const day = localDay(item.created_at)
  const at = formatDateTime(item.created_at)
  const when = day === todayISO() ? `${t('newsToday')} ${at.slice(-5)}`
    : day === yesterdayISO() ? `${t('newsYesterday')} ${at.slice(-5)}` : at
  return (
    <li className="news-li">
      <button type="button" className={`news-card pr-${item.priority}${unread ? ' unread' : ''}${active ? ' active' : ''}`}
              aria-current={active} onClick={() => onOpen(item.id)}>
        <span className="news-card-top">
          {showCat && <span className={`news-cat nc-${item.category}`}><Icon size={12} aria-hidden="true" /> {t(`newsCat_${item.category}`)}</span>}
          <span className="muted mono">{when}</span>
          {unread && <span className="news-new">{t('newsStatusNew')}</span>}
        </span>
        <span className="news-card-title">{item.title}</span>
        {item.body && <span className="news-card-body">{item.body}</span>}
        {earlier > 0 && <span className="news-earlier">+{earlier} {t('newsEarlier')}</span>}
      </button>
      {onToggleRead && (
        <button type="button" className={`news-read-toggle${unread ? ' unread' : ''}`}
                aria-label={t(unread ? 'newsMarkRead' : 'newsMarkUnread')}
                title={t(unread ? 'newsMarkRead' : 'newsMarkUnread')}
                onClick={() => onToggleRead(card)}><span aria-hidden="true" /></button>
      )}
    </li>
  )
}

export default function NewsColumn({ cat, cards, unread, hasMore, busy, loaded, selectedId, onOpen, onMore, onToggleRead }: {
  cat: NewsCategory
  cards: NewsCard[]
  unread: number
  hasMore: boolean
  busy: boolean
  loaded: boolean
  selectedId: number | null
  onOpen: (id: number) => void
  onMore: () => void
  onToggleRead: (card: NewsCard) => void
}) {
  const t = useT()
  const Icon = CATEGORY_ICON[cat]
  const name = t(`newsCat_${cat}`)
  if (loaded && cards.length === 0 && !hasMore) {
    return (
      <section className={`news-col collapsed nc-${cat}`} aria-label={`${name}: 0`} data-testid={`news-col-${cat}`}>
        <Icon size={14} aria-hidden="true" />
        <span className="news-col-vname">{name}</span>
        <span className="news-col-count">0</span>
      </section>
    )
  }
  return (
    <section className={`news-col nc-${cat}`} aria-labelledby={`news-col-h-${cat}`} data-testid={`news-col-${cat}`}>
      <h3 id={`news-col-h-${cat}`} className="news-col-head">
        <Icon size={14} aria-hidden="true" /> <span>{name}</span>
        {unread > 0 && <span className="news-col-count" aria-label={`${unread} ${t('newsUnreadCount')}`}>{unread}</span>}
      </h3>
      <div className="news-col-list">
        <ul>{cards.map(c => <NewsCardView key={c.item.id} card={c} active={selectedId === c.item.id} onOpen={onOpen}
                                                   onToggleRead={onToggleRead} />)}</ul>
        {hasMore && (
          <button type="button" className="btn small secondary news-more" disabled={busy} onClick={onMore}>{t('newsLoadOlder')}</button>
        )}
      </div>
    </section>
  )
}
