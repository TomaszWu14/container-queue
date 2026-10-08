// Poczekalnia dokumentów — plaster 2 (spec 2026-10-06-dokumenty-dostaw §1 decyzje 1–4, 12, 20; §3):
// jedno „Dodaj dokumenty” (pliki / folder / ZIP / upuszczenie) → okno „Sprawdź i potwierdź” z częściami
// (typ, kontener, bramka, odrzuć) → „Potwierdź” wpuszcza do dostawy. Zamknięcie okna = czeka bez limitu;
// pasek „N dokumentów czeka” otwiera najstarsze wgranie. API: routers/intake.py.
import { useCallback, useEffect, useState } from 'react'
import type { DragEvent } from 'react'
import { CheckIcon, ExternalLinkIcon, FolderIcon, InboxIcon, UploadIcon } from 'lucide-react'
import { useUser } from './App'
import { api, errorMessage } from './api'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './feedback'
import { FileButton } from './FilePicker'
import { Modal } from './Modal'
import { TILE_META } from './DocumentTiles'
import { useT } from './i18n'
import './intake.css'

export const DOC_TYPES = ['CI', 'PI', 'PL', 'BL', 'SAD_DRAFT', 'SAD_PZ', 'SAD_PW', 'CMR', 'MAIL', 'OTHER'] as const
type Gate = 'ok' | 'uncertain' | 'conflict' | 'duplicate' | 'unreadable'
export interface IntakeItem {
  id: number; original_name: string; page_from: number; page_to: number; pages: number
  doc_type: string; target_container_id: number | null; target_container_no: string | null
  gate_status: Gate; gate_message: string; decision: 'pending' | 'accepted' | 'rejected'
  found_containers: { container_no: string; container_id: number | null }[]
}
export interface IntakeBatch { id: number; container_id: number; status: string; items: IntakeItem[]; skipped?: string[] }
interface ConfirmResult { containers: Record<string, { invoices: number; attachments: number }>; skipped: string[] }

const fill = (s: string, vars: Record<string, string | number>) =>
  Object.entries(vars).reduce((acc, [k, v]) => acc.replace(`{${k}}`, String(v)), s)
const items = (b: unknown): IntakeItem[] => (Array.isArray((b as IntakeBatch)?.items) ? (b as IntakeBatch).items : [])

/** Okno „Sprawdź i potwierdź” jednego wgrania. `onDone` = potwierdzone albo odrzucone w całości. */
export function IntakeModal({ batch, onClose, onDone }: {
  batch: IntakeBatch; onClose: () => void; onDone: () => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const [rows, setRows] = useState(batch.items)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const typeLabel = (code: string) =>
    code in TILE_META ? t(`dtName_${code}`) : t(`inqType_${code}`)

  const patch = async (id: number, body: Record<string, unknown>) => {
    setBusy(true); setError('')
    try {
      const next = await api.patch<IntakeItem>(`/api/intake/items/${id}`, body)
      setRows(rs => rs.map(r => (r.id === id ? { ...r, ...next } : r)))
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const submit = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.post<ConfirmResult>(`/api/intake/${batch.id}/confirm`, {})
      const done = Object.entries(r?.containers ?? {}).map(([c, v]) =>
        fill(t('inqDoneItem'), { c, i: v.invoices, a: v.attachments })).join('; ')
      showToast([fill(t('inqDone'), { v: done || '0' }),
                 r?.skipped?.length ? fill(t('inqSkipped'), { v: r.skipped.join('; ') }) : ''].filter(Boolean).join(' · '))
      onDone()
    } catch (err) { setError(errorMessage(err)); setBusy(false) }   // 409: okno zostaje z komunikatem
  }
  const discard = async () => {
    if (!(await confirm(t('inqDiscardAsk'), { danger: true, confirmLabel: t('inqDiscard') }))) return
    setBusy(true); setError('')
    try {
      await api.post(`/api/intake/${batch.id}/discard`, {})
      onDone()
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }

  return (
    <Modal title={t('inqTitle')} onClose={onClose} busy={busy} width={1040} className="inq-modal">
      <div className="inq-scroll">
        <table className="grid inq-table">
          <thead><tr>
            <th>{t('inqPart')}</th><th>{t('inqType')}</th><th>{t('inqTarget')}</th><th>{t('inqGate')}</th><th />
          </tr></thead>
          <tbody>
            {rows.map(r => {
              const rejected = r.decision === 'rejected'
              const moves = r.gate_status === 'conflict'
                ? r.found_containers.filter(f => f.container_id && f.container_id !== r.target_container_id) : []
              return (
                <tr key={r.id} className={rejected ? 'inq-rejected' : undefined}>
                  <td>
                    <b className="inq-name" title={r.original_name}>{r.original_name}</b>
                    {r.pages > 0 && <small className="muted"> · {fill(t('inqPages'), { a: r.page_from, b: r.page_to })}</small>}
                    <div><button type="button" className="link-btn"
                                 onClick={() => window.open(`/api/intake/items/${r.id}/file`, '_blank', 'noopener')}>
                      <ExternalLinkIcon size={12} aria-hidden="true" /> {t('inqOpen')}</button></div>
                  </td>
                  <td>
                    <select aria-label={`${t('inqType')}: ${r.original_name}`} value={r.doc_type}
                            disabled={busy || rejected} onChange={e => patch(r.id, { doc_type: e.target.value })}>
                      {DOC_TYPES.map(c => <option key={c} value={c}>{c.replace('_', '-')} — {typeLabel(c)}</option>)}
                    </select>
                  </td>
                  <td>
                    <span className="mono">{r.target_container_no ?? '—'}</span>
                    {moves.map(f => (
                      <div key={f.container_no}>
                        <button type="button" className="btn small secondary" disabled={busy || rejected}
                                onClick={() => patch(r.id, { target_container_id: f.container_id })}>
                          {fill(t('inqMoveTo'), { v: f.container_no })}</button>
                      </div>
                    ))}
                  </td>
                  <td>
                    <span className={`badge inq-g-${r.gate_status}`}>{t(`inqGate_${r.gate_status}`)}</span>
                    {r.gate_status !== 'ok' && r.gate_message && <div className="inq-msg">{r.gate_message}</div>}
                  </td>
                  <td>
                    <button type="button" className="btn small secondary" disabled={busy}
                            onClick={() => patch(r.id, { decision: rejected ? 'accepted' : 'rejected' })}>
                      {rejected ? t('inqRestore') : t('inqReject')}</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {batch.skipped?.length ? <p className="muted">{fill(t('inqSkipped'), { v: batch.skipped.join('; ') })}</p> : null}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button type="button" className="btn secondary" disabled={busy} onClick={discard}>{t('inqDiscard')}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={onClose}>{t('inqLater')}</button>
        <button type="button" className="btn" disabled={busy} onClick={submit} data-autofocus>
          <CheckIcon size={14} aria-hidden="true" /> {t('inqConfirm')}</button>
      </div>
    </Modal>
  )
}

/** „Dodaj dokumenty” + pasek oczekujących + okno. Magazyn i sprzedaż nie wgrywają (jak dotąd). */
export function IntakePanel({ containerId, onChanged }: { containerId: number; onChanged?: () => void }) {
  const t = useT()
  const user = useUser()
  const allowed = !!user && user.role !== 'warehouse' && user.role !== 'sales'
  const [pending, setPending] = useState<IntakeBatch[]>([])
  const [open, setOpen] = useState<IntakeBatch | null>(null)
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get<IntakeBatch[]>(`/api/containers/${containerId}/intake?status=pending`)
      .then(r => setPending(Array.isArray(r) ? r.filter(b => items(b).length) : [])).catch(() => setPending([]))
  }, [containerId])
  useEffect(() => { if (allowed) load() }, [allowed, load])

  const upload = async (files: File[]) => {
    if (!files.length) return
    setBusy(true); setError('')
    try {
      const batch = await api.upload<IntakeBatch>(`/api/containers/${containerId}/intake`, files, 'files')
      setOpen(batch)
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const drop = (e: DragEvent) => {
    e.preventDefault(); setOver(false)
    upload(Array.from(e.dataTransfer.files ?? []))
  }

  if (!allowed) return null
  const waiting = pending.reduce((n, b) => n + items(b).length, 0)
  return (
    <section className="panel inq-panel" aria-label={t('inqAdd')}>
      {waiting > 0 && (
        <div className="inq-bar" role="status">
          <InboxIcon size={16} aria-hidden="true" />
          <span>{fill(t('inqWaiting'), { n: waiting })}</span>
          <button type="button" className="btn small" onClick={() => setOpen(pending[0])}>{t('inqReview')}</button>
        </div>
      )}
      <div className={`inq-drop${over ? ' over' : ''}`}
           onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={drop}>
        <FileButton className="btn small" multiple disabled={busy} onFiles={upload}>
          <UploadIcon size={14} aria-hidden="true" /> {busy ? t('inqUploading') : t('inqAdd')}
        </FileButton>
        <FileButton directory disabled={busy} onFiles={upload} title={t('inqAddFolder')}>
          <FolderIcon size={14} aria-hidden="true" /> {t('inqAddFolder')}
        </FileButton>
        <span className="muted">{t('inqDrop')}</span>
      </div>
      {error && <p className="error">{error}</p>}
      {open && (
        <IntakeModal key={open.id} batch={open} onClose={() => { setOpen(null); load() }}
                     onDone={() => { setOpen(null); load(); onChanged?.() }} />
      )}
    </section>
  )
}
