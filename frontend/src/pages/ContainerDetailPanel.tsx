import { ChevronUpIcon, PhoneIcon } from 'lucide-react'
// Rozwijany panel szczegółów kontenera renderowany INLINE w kolejce (akordeon pod
// wierszem, jeden naraz). Kurowany podzbiór karty kontenera: droga (oś czasu),
// statusy + historia, dokumenty + pozycje, kontakt. Ciężka mapa/globus zostaje na
// pełnej karcie (link „Otwórz pełną kartę"). Spec:
// docs/superpowers/specs/2026-09-22-kolejka-inline-szczegoly-kontenera.md
import { useEffect, useState } from 'react'
import { useOpenFullCard } from './queue/fullCard'
import { api } from '../api'
import { useT } from '../i18n'
import { useUser } from '../App'
import { seesCustoms } from '../routing'
import ContainerTimeline from './tracking/ContainerTimeline'
import { MessagesPanel, AttachmentsPanel } from '../collaboration'
import { IntakePanel } from '../IntakeWaitingRoom'
import { ItemsPanel } from './ContainerItems'
import { formatDate, formatDateTime } from '../dates'
import type { AuditEntry, Container } from '../types'

export default function ContainerDetailPanel({ container, onOpenStatus, onClose }: {
  container: Container
  onOpenStatus?: (c: Container) => void
  onClose?: () => void
}) {
  const t = useT()
  const openFullCard = useOpenFullCard()   // „← Kolejka” na karcie wraca do tego widoku
  const user = useUser()
  const role = user?.role
  const canEdit = role === 'admin' || role === 'logistics'
  const isCustoms = role === 'customs'
  const isWarehouse = role === 'warehouse'

  // historia dobierana dopiero przy rozwinięciu (panel montuje się on-expand)
  const [history, setHistory] = useState<AuditEntry[] | null>(null)
  const [filesKey, setFilesKey] = useState(0)
  useEffect(() => {
    let cancelled = false
    api.get<AuditEntry[]>(`/api/containers/${container.id}/history`)
      .then(h => { if (!cancelled) setHistory(Array.isArray(h) ? h : []) })
      .catch(() => { if (!cancelled) setHistory([]) })   // brak historii nie może wywalić panelu
    return () => { cancelled = true }
  }, [container.id, container.updated_at])   // zmiana statusu podbija updated_at → świeża historia

  // Esc zwija panel (poza polami edycji — tam Esc należy do pola)
  useEffect(() => {
    if (!onClose) return
    const onKey = (e: KeyboardEvent) => {
      const el = e.target instanceof Element ? e.target : null
      if (e.key !== 'Escape' || el?.closest('input,textarea,select,[contenteditable]')) return
      onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const tel = (label: string, n?: string | null) => n
    ? <a className="cd-tel" href={`tel:${n.replace(/[^+\d]/g, '')}`}><PhoneIcon size={14} /> {label}: {n}</a>
    : null

  return (
    <div className="cont-detail" role="region" aria-label={container.container_no}>
      <div className="cd-head">
        <b className="mono">{container.container_no}</b>
        <span className="cd-head-actions">
          {(canEdit || isWarehouse) && onOpenStatus && (
            <button className="btn small secondary" onClick={() => onOpenStatus(container)}>
              {isWarehouse ? t('confirmUnload') : t('changeStatus')}
            </button>
          )}
          <button className="btn small" onClick={() => openFullCard(container.id, null)}>
            {t('cdOpenFull')} →
          </button>
          {onClose && (
            <button className="btn small secondary" onClick={onClose} aria-label={t('cdCollapse')} title={`${t('cdCollapse')} (Esc)`}>
              {t('cdCollapse')} <ChevronUpIcon size={14} />
            </button>
          )}
        </span>
      </div>

      <div className="cd-grid">
        <section className="cd-sec">
          <h4>{t('cdTimeline')}</h4>
          <ContainerTimeline containerId={container.id} refreshKey={Date.parse(container.updated_at) || 0} />
        </section>

        <section className="cd-sec">
          <h4>{t('cdStatusHistory')}</h4>
          <div className="cd-kv"><span>{t('status')}</span>
            <span className={`badge st-${container.status}`}>{t(`st_${container.status}`)}</span></div>
          {seesCustoms(role) && (
            <div className="cd-kv"><span>{t('customs')}</span><b>{container.customs_status || '—'}</b></div>)}
          <div className="cd-kv"><span>{t('eta')}</span>
            <b className="mono">{container.eta ? formatDate(container.eta)
              : container.eta_estimate
                ? <span className="muted" title={t('etaEstimateHint')}>
                    ~{formatDate(container.eta_estimate)} ({t('etaEstimate')})</span>
                : '—'}</b></div>
          <div className="cd-kv"><span>{t('notifyDate')}</span>
            <b className="mono">{container.notify_date ? formatDate(container.notify_date) : '—'}
              {container.slot_time ? ` · ${t('slotLabel')} ${container.slot_time}` : ''}</b></div>
          <div className="cd-kv"><span>{t('warehouse')}</span><b>{container.warehouse_name ?? '—'}</b></div>
          <div className="cd-history">
            {history === null ? <span className="muted">…</span>
              : history.length === 0 ? <span className="muted">{t('cdNoHistory')}</span>
                : history.slice(0, 10).map(h => (
                  <div key={h.id} className="cd-hist-row">
                    <span className="mono muted">{formatDateTime(h.created_at)}</span>
                    <span>{h.field}: <s className="muted">{h.old_value ?? '—'}</s> → <b>{h.new_value ?? '—'}</b></span>
                    {h.note && <span className="muted">· {h.note}</span>}
                    {h.user_login && <span className="muted">· {h.user_login}</span>}
                  </div>
                ))}
          </div>
        </section>

        <section className="cd-sec">
          <h4>{t('cdDocsItems')}</h4>
          {/* załączniki jak na pełnej karcie — nowe pliki tylko przez poczekalnię; pozycje ukryte dla celnej */}
          <IntakePanel containerId={container.id} onChanged={() => setFilesKey(k => k + 1)} />
          <AttachmentsPanel key={filesKey} container={container} />
          {!isCustoms && <ItemsPanel container={container} />}
        </section>

        <section className="cd-sec">
          <h4>{t('cdContact')}</h4>
          <div className="cd-contacts">
            <div className="cd-kv"><span>{t('forwarder')}</span><b>{container.forwarder_name ?? '—'}</b></div>
            {container.driver_name && (
              <div className="cd-kv"><span>{t('cdDriver')}</span><b>{container.driver_name}</b></div>
            )}
            {tel(t('cdDriver'), container.driver_phone)}
            {(container.truck_no || container.trailer_no) && (
              <div className="cd-kv"><span>{t('truckNo')} / {t('trailerNo')}</span>
                <b className="mono">{[container.truck_no, container.trailer_no].filter(Boolean).join(' / ')}</b></div>
            )}
            {tel(t('cdCustomsAgent'), container.customs_agent_phone)}
          </div>
          {/* wewnętrzny kanał/notatka + @wzmianki (kontakt ze spedytorem w apce) */}
          <MessagesPanel container={container} />
        </section>
      </div>
    </div>
  )
}
