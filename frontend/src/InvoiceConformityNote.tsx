import { useT } from './i18n'

/** Zgodność dokumentu z kontenerem paczki (GET /api/invoice-jobs/{id}/conformity,
 *  spec 2026-10-01-bramka-dokument-dostawa). */
export interface Conformity {
  status: 'ok' | 'uncertain' | 'conflict'
  signals: { key: 'container' | 'orders' | 'supplier' | 'materials'; ok: boolean | null; detail: string }[]
  overage: boolean
  to_link: string[]
  move_to: { id: number; container_no: string }[]
  also_in?: { id: number; container_no: string; has_copy: boolean }[]   // faktura na kilka kontenerów
  ack: { reason: string; by: string; at: string } | null
}

export const isConformity = (data: unknown): data is Conformity =>
  !!data && typeof data === 'object' && Array.isArray((data as Conformity).signals)

/** Sprzeczna: co nie pasuje i do którego kontenera pasuje. Niepewna: pole powodu
 *  (wymagane do zatwierdzenia, raz). PO bez kontenera: przycisk „przypnij”.
 *  Sprzeczna z wykrytym właściwym kontenerem: „Przenieś do X” (2b). Faktura na kilka
 *  kontenerów: „Dodaj też do X” (PR 3). */
export function InvoiceConformityNote({ conformity, reason, onReason, onLink, onMove, onCopy }: {
  conformity: Conformity
  reason: string
  onReason: (value: string) => void
  onLink: () => void
  onMove?: (containerId: number) => void
  onCopy?: (containerId: number) => void
}) {
  const t = useT()
  const label = (key: Conformity['signals'][number]['key']) => t(`confSig_${key}`)
  const bad = conformity.signals.filter(s => s.ok === false)
  const unknown = conformity.signals.filter(s => s.ok === null).map(s => label(s.key))
  if (conformity.overage) unknown.push(t('confOverage'))
  return (
    <>
      {conformity.status === 'ok' && <span className="badge st-DOSTARCZONY">{t('confOk')}</span>}
      {conformity.status === 'conflict' && (
        <p className="error" role="alert">
          {t('confConflict')} {bad.map(s => s.detail ? `${label(s.key)}: ${s.detail}` : label(s.key)).join('; ')}
          {conformity.move_to.length > 0
            && ` — ${t('confFitsTo')} ${conformity.move_to.map(c => c.container_no).join(', ')}`}
        </p>
      )}
      {conformity.status === 'conflict' && onMove && conformity.move_to.map(c => (
        <button key={c.id} type="button" className="btn small" onClick={() => onMove(c.id)}>
          {t('confMoveTo')} {c.container_no}
        </button>
      ))}
      {onCopy && (conformity.also_in ?? []).length > 0 && (
        <p className="row" style={{ gap: 8, alignItems: 'center', fontSize: 13, flexWrap: 'wrap' }}>
          <span>{t('confAlsoIn')}</span>
          {(conformity.also_in ?? []).map(c => c.has_copy
            ? <span key={c.id} className="badge st-DOSTARCZONY">{c.container_no} ✓</span>
            : <button key={c.id} type="button" className="btn small secondary" onClick={() => onCopy(c.id)}>
                {t('confCopyTo')} {c.container_no}
              </button>)}
        </p>
      )}
      {conformity.status === 'uncertain' && conformity.ack && (
        <p className="muted" style={{ fontSize: 13 }}>
          {t('confAcked')}: {conformity.ack.reason} ({conformity.ack.by})
        </p>
      )}
      {conformity.status === 'uncertain' && !conformity.ack && (
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, flexWrap: 'wrap' }}>
          {t('confUncertain')} {unknown.join(', ')}.
          <input value={reason} onChange={e => onReason(e.target.value)} placeholder={t('confReason')}
                 aria-label={t('confReason')} maxLength={500} style={{ minWidth: 260 }} />
        </label>
      )}
      {conformity.to_link.length > 0 && (
        <p className="row" style={{ gap: 8, alignItems: 'center', fontSize: 13 }}>
          <span>{t('invOrdersToLink').replace('{v}', conformity.to_link.join(', '))}</span>
          <button type="button" className="btn small secondary" onClick={onLink}>{t('invLinkOrders')}</button>
        </p>
      )}
    </>
  )
}
