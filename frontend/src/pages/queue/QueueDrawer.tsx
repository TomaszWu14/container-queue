import { MailIcon, XIcon } from 'lucide-react'
// Kolejka Enterprise (plaster 2): prawa szuflada kontenera — Szczegóły / Historia,
// nawigacja ‹ › po bieżącej kolejności wierszy, ✕ / Esc zamyka. Tylko pola z API.
import { useContext, useEffect, useLayoutEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../../api'
import { formatDate, formatDateTime, formatDayLong, todayISO } from '../../dates'
import { LangContext, localeFor, useT } from '../../i18n'
import type { AuditEntry, Container } from '../../types'
import { idLabel } from './cells'
import { TransportBadge } from '../../TransportBadge'
import { CostsTab, DocumentsTab, MessagesTab, useDrawerData } from './DrawerTabs'
import ContainerSummary from './ContainerSummary'
import { DrawerDocumentTiles } from '../../DocumentTiles'
import { demurrageDaysLeft, DEMURRAGE_SOON_DAYS } from './enterprise'

type Tab = 'details' | 'docs' | 'messages' | 'costs' | 'history'

export default function QueueDrawer({ c, fill, onPrev, onNext, onClose, onStatus, statusLabel,
  onAvizo, onFull, watchReason }: {
  c: Container
  fill: number | null | undefined
  onPrev: (() => void) | null
  onNext: (() => void) | null
  onClose: () => void
  onStatus: (() => void) | null    // null = rola bez prawa zmiany statusu
  statusLabel: string
  onAvizo: (() => void) | null     // null = rola bez awizacji
  onFull: () => void
  watchReason?: string             // undefined = nie obserwujesz; '' = ★ bez powodu
}) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const [tab, setTab] = useState<Tab>('details')
  const [history, setHistory] = useState<AuditEntry[] | null>(null)
  const d = useDrawerData(c.id)

  // historia z audytu (GET /containers/{id}/history — izolacja po stronie backendu)
  useEffect(() => {
    let cancelled = false
    setHistory(null)
    api.get<AuditEntry[]>(`/api/containers/${c.id}/history`)
      .then(h => { if (!cancelled) setHistory(Array.isArray(h) ? h : []) })
      .catch(() => { if (!cancelled) setHistory([]) })
    return () => { cancelled = true }
  }, [c.id, c.updated_at])

  // Esc zamyka, strzałki ← → przechodzą między wierszami (poza polami formularzy).
  // Layout, nie zwykły efekt: nasłuch musi istnieć od commitu, w którym szuflada jest w DOM —
  // efekt pasywny scheduler może odłożyć i wcześniejsze Esc przepada (flaky test pod obciążeniem).
  useLayoutEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.closest?.('input,textarea,select,[role="dialog"]')) return
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft' && onPrev) onPrev()
      else if (e.key === 'ArrowRight' && onNext) onNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, onPrev, onNext])

  const locale = localeFor(lang)
  const longDate = (iso: string) => formatDayLong(iso, locale)
  const left = demurrageDaysLeft(c, todayISO())
  // liczba dni jak w makiecie; data terminu w nawiasie (i w title)
  const deadline = formatDate(c.demurrage_deadline ?? null)
  const free = left === null ? null : (
    <span title={deadline}>
      <b className={left <= 0 ? 'kq-late' : left <= DEMURRAGE_SOON_DAYS ? 'kq-dem soon' : undefined}>
        {left < 0 ? t('kqdOverBy').replace('{n}', String(-left)) : t('kqDaysLeft').replace('{n}', String(left))}
      </b>{' '}<span className="kq-dim">({deadline})</span>
    </span>
  )
  const fieldLabel = (f: string) => { const k = `histField_${f}`; const v = t(k); return v === k ? f : v }

  const sections: [string, [string, ReactNode][]][] = [
    [t('kqdSecDelivery'), [
      [t('kqColDelivery'), c.notify_date ? <b>{longDate(c.notify_date)}</b> : '—'],
      [t('warehouse'), c.warehouse_name ? c.warehouse_name : <b className="kq-late">{t('kqdNoWarehouse')}</b>],
      [t('transport'), c.transport_type || c.on_carriage || c.forwarder_name ? <>
        {c.transport_type && <TransportBadge type={c.transport_type} />}
        {c.transport_type && c.on_carriage && ' → '}{c.on_carriage && <TransportBadge type={c.on_carriage} />}
        {(c.transport_type || c.on_carriage) && c.forwarder_name && ' · '}{c.forwarder_name}
      </> : '—'],
      ...(c.slot_time ? [[t('slotLabel'), <span className="mono">{c.slot_time}</span>] as [string, ReactNode]] : []),
    ]],
    [t('kqdSecSea'), [
      [t('vessel'), c.vessel ? <b>{c.vessel}</b> : '—'],
      [t('kqdPort'), c.port_name || '—'],
      [t('eta'), <span className="mono">{formatDate(c.eta ?? c.eta_estimate ?? null)}</span>],
      [t('kqdFreeUntil'), free ?? '—'],
    ]],
    [t('kqdSecCargo'), [
      [t('kqdType'), <span className="mono">{c.container_size || '—'}</span>],
      ...(c.pallet_count != null ? [[t('kqdPallets'), String(c.pallet_count)] as [string, ReactNode]] : []),
      ...(fill != null ? [[t('kqColFill'), `${Math.round(fill)}%`] as [string, ReactNode]] : []),
    ]],
  ]

  // zakładki (makieta): Koszty tylko dla ról z dostępem do faktur frachtowych (403 → brak)
  const tabs: [Tab, string, number | null | undefined][] = [
    ['details', t('details'), undefined],
    ['docs', t('kqdDocs'), d.files?.length ?? null],
    ['messages', t('messages'), d.messages?.length ?? null],
    ...(d.costs === 'forbidden' ? [] : [['costs', t('kqdCosts'), undefined] as [Tab, string, undefined]]),
    ['history', t('kqdHistory'), history?.length ?? null],
  ]

  return (
    <aside className="kq-drawer" aria-label={`${t('kqdTitle')} ${idLabel(c)}`}>
      <div className="kq-dr-top">
        <div className="kq-dr-row">
          <span className="kq-ct">{t('kqdTitle')}</span>
          <span className="spacer" />
          <button type="button" className="kq-dr-ico" aria-label={t('kqdPrev')} title={t('kqdPrev')}
                  disabled={!onPrev} onClick={() => onPrev?.()}>‹</button>
          <button type="button" className="kq-dr-ico" aria-label={t('kqdNext')} title={t('kqdNext')}
                  disabled={!onNext} onClick={() => onNext?.()}>›</button>
          <button type="button" className="kq-dr-ico" aria-label={t('close')} title={t('close')}
                  onClick={onClose}><XIcon size={14} /></button>
        </div>
        <ContainerSummary c={c} watchReason={watchReason} />
        {/* kafelki dokumentów w wersji kompaktowej (spec 2026-10-01) — klik = zakładka Dokumenty */}
        <DrawerDocumentTiles containerId={c.id} onOpen={() => setTab('docs')} />
        <div className="kq-dr-tabs" role="tablist">
          {tabs.map(([key, label, n]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key}
                    className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
              {label}{n !== undefined && <> <span className="kq-tab-n mono">{n ?? '…'}</span></>}
            </button>
          ))}
        </div>
      </div>

      <div className="kq-dr-body">
        {tab === 'docs' && <DocumentsTab containerId={c.id} d={d} />}
        {tab === 'messages' && <MessagesTab containerId={c.id} d={d} />}
        {tab === 'costs' && Array.isArray(d.costs) && <CostsTab rows={d.costs} />}
        {tab === 'details' && sections.map(([title, rows]) => (
          <section key={title}>
            <div className="kq-ct">{title}</div>
            <dl className="kq-dr-kv">
              {rows.map(([k, v]) => <div key={k} className="kq-dr-pair"><dt>{k}</dt><dd>{v}</dd></div>)}
            </dl>
          </section>
        ))}
        {tab === 'history' && (history === null ? <span className="kq-dim">…</span>
          : history.length === 0 ? <span className="kq-dim">{t('cdNoHistory')}</span>
            : <ol className="kq-dr-hist">
              {history.map((h, i) => (
                <li key={h.id}>
                  <i className={i === 0 ? 'new' : ''} />
                  <div>
                    <div><b>{h.user_login ?? t('kqdSystem')}</b> {fieldLabel(h.field)}:{' '}
                      <s className="kq-dim">{h.old_value ?? '—'}</s> → <b>{h.new_value ?? '—'}</b></div>
                    <div className="kq-dr-meta mono">
                      {formatDateTime(h.created_at)}{h.note ? ` · ${h.note}` : ''}
                    </div>
                  </div>
                </li>
              ))}
            </ol>)}
      </div>

      <div className="kq-dr-foot">
        {onStatus && <button type="button" className="btn small secondary" onClick={onStatus}>{statusLabel}</button>}
        {onAvizo && <button type="button" className="btn small avizo-btn" onClick={onAvizo}><MailIcon size={14} /> {t('kqdAvizo')}</button>}
        <span className="spacer" />
        <button type="button" className="btn small" onClick={onFull}>{t('kqdFull')}</button>
      </div>
    </aside>
  )
}
