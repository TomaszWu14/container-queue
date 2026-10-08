import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { api, errorMessage } from './api'
import { useToast } from './feedback'
import { useT } from './i18n'
import { useDiscardGuard } from './formGuard'
import { useBusy } from './useBusy'
import { Modal } from './Modal'
export { Modal, useEscClose } from './Modal'
import { ON_CARRIAGE_TYPES, TRANSPORT_TYPES, TransportBadge, type OnCarriage, type TransportType } from './TransportBadge'
import type {
  Container, ContainerStatus, CustomsStatus, DocumentStatus, Named, PurchasingStatus,
  Supplier, Warehouse,
} from './types'
import { CUSTOMS_STATUSES, DOCUMENT_STATUSES, CONTAINER_STATUSES as STATUSES } from './types'

// Wspólny kafelek KPI (Pulpit / Dostawca / Kalendarz). `variant="inline"` = wariant
// Kalendarza: mniejsza wartość mono w jednej linii z jednostką (.cal-kpi-row).
export function Kpi({ label, value, unit, color, variant = 'default' }: {
  label: ReactNode
  value: ReactNode
  unit?: ReactNode
  color?: string
  variant?: 'default' | 'inline'
}) {
  const style = color ? { color } : undefined
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      {variant === 'inline' ? (
        <div className="cal-kpi-row">
          <span className="mono cal-kpi-value" style={style}>{value}</span>
          {unit != null && <span className="kpi-unit">{unit}</span>}
        </div>
      ) : (
        <>
          <div className="kpi-value" style={style}>{value}</div>
          {unit != null && <span className="kpi-unit">{unit}</span>}
        </>
      )}
    </div>
  )
}

export function StatusBadge({ status, ageDays }: { status: ContainerStatus; ageDays?: number | null }) {
  const t = useT()
  // #27: wiek statusu — kropka żółta >7 dni, czerwona >14 (kontener „utknął")
  const age = ageDays ?? null
  const ageClass = age == null ? '' : age > 14 ? ' age-red' : age > 7 ? ' age-amber' : ''
  return (
    <span className={`badge st-${status}`}>
      {t(`st_${status}`)}
      {ageClass && <span className={`age-dot${ageClass}`}
                         title={`${age} ${t('daysAbbrev')} ${t('inStatus')}`} />}
    </span>
  )
}

/** Mini-track cyklu życia (makieta „Kolejka — hybryda A+E"): 8 segmentów,
 *  zaliczone zielone, bieżący teal z kropką (czerwony gdy opóźniony), przyszłe wygaszone.
 *  Tooltip każdego segmentu = nazwa etapu; całość ma title z bieżącym etapem. */
export function StageTrack({ status, delayed }: { status: ContainerStatus; delayed?: boolean }) {
  const t = useT()
  const idx = STATUSES.indexOf(status)
  return (
    <span className="stage-track" title={t(`st_${status}`)} data-testid="stage-track">
      {STATUSES.map((s, i) => (
        <i key={s}
           className={i < idx ? 'done' : i === idx ? `cur${delayed ? ' late' : ''}` : ''}
           title={t(`st_${s}`)} />
      ))}
    </span>
  )
}

export function CustomsBadge({ status }: { status: CustomsStatus }) {
  const t = useT()
  return <span className={`badge cs-${status}`}>{t(`cs_${status}`)}</span>
}

export function DocumentBadge({ status }: { status: DocumentStatus }) {
  const t = useT()
  return <span className={`badge ds-${status}`}>{t(`ds_${status}`)}</span>
}

export function PurchasingBadge({ status }: { status: PurchasingStatus }) {
  const t = useT()
  return <span className={`badge ps-${status}`}>{t(`ps_${status}`)}</span>
}

export interface Dicts {
  suppliers: Supplier[]
  forwarders: Named[]
  warehouses: Warehouse[]
  ports: Named[]
  carriers: Named[]
}

export function useDicts(): Dicts {
  const { showToast } = useToast()
  const [dicts, setDicts] = useState<Dicts>({
    suppliers: [], forwarders: [], warehouses: [], ports: [], carriers: [],
  })
  useEffect(() => {
    // każdy słownik osobno: 403 jednego (np. dostawcy dla agencji celnej) nie zeruje reszty
    const get = <T,>(path: string) => api.get<T[]>(path).catch((err: unknown) => {
      // 403 = rola bez tego słownika → pusta lista; inny błąd nie znika bez śladu
      if ((err as { status?: number })?.status !== 403) showToast(errorMessage(err), 'error')
      return [] as T[]
    })
    Promise.all([
      get<Supplier>('/api/suppliers'),
      get<Named>('/api/forwarders'),
      get<Warehouse>('/api/warehouses'),
      get<Named>('/api/ports'),
      get<Named>('/api/carriers'),
    ]).then(([suppliers, forwarders, warehouses, ports, carriers]) =>
      setDicts({ suppliers, forwarders, warehouses, ports, carriers }))
  }, [showToast])
  return dicts
}

interface ContainerFormProps {
  dicts: Dicts
  initial?: Container
  companyOptions?: Named[]
  onSaved: (c: Container) => void
  onClose: () => void
}

export function ContainerFormModal({ dicts, initial, companyOptions, onSaved, onClose }: ContainerFormProps) {
  const t = useT()
  const { showToast } = useToast()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    container_no: initial?.container_no ?? '',
    company_id: initial?.company_id ?? companyOptions?.[0]?.id ?? null,
    order_number: initial?.order_number ?? '',
    supplier_id: initial?.supplier_id ?? null,
    forwarder_id: initial?.forwarder_id ?? null,
    warehouse_id: initial?.warehouse_id ?? null,
    port_id: initial?.port_id ?? null,
    carrier_id: initial?.carrier_id ?? null,
    vessel: initial?.vessel ?? '',
    eta: initial?.eta ?? '',
    atd: initial?.atd ?? '',
    notify_date: initial?.notify_date ?? '',
    transport_type: initial?.transport_type ?? '',
    on_carriage: initial?.on_carriage ?? '',
    container_size: initial?.container_size ?? '',
    documents_ok: initial?.documents_ok ?? false,
    is_transit: initial?.is_transit ?? false,
    document_status: initial?.document_status ?? 'BRAK',
    customs_status: initial?.customs_status ?? 'BRAK',
    customs_agency: initial?.customs_agency ?? '',
    demurrage_free_days: initial?.demurrage_free_days ?? '',
    incoming_delivery_no: initial?.incoming_delivery_no ?? '',
    rf_number: initial?.rf_number ?? '',
    notes: initial?.notes ?? '',
    materials_list: initial?.materials_list ?? '',
    palletization_note: initial?.palletization_note ?? '',
    pallet_count: initial?.pallet_count ?? '',
    change_note: '',
  })

  const set = (key: string, value: unknown) => setForm(f => ({ ...f, [key]: value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    const payload: Record<string, unknown> = {
      ...form,
      eta: form.eta || null,
      atd: form.atd || null,
      notify_date: form.notify_date || null,
      transport_type: form.transport_type || null,
      on_carriage: form.on_carriage || null,
      demurrage_free_days: form.demurrage_free_days === '' ? null : Number(form.demurrage_free_days),
      pallet_count: form.pallet_count === '' ? null : Number(form.pallet_count),
    }
    try {
      let saved: Container
      if (initial) {
        delete payload.company_id
        delete payload.order_number
        // blokada optymistyczna (audyt DB-005): ktoś zapisał w międzyczasie → 409 zamiast nadpisania
        payload.expected_updated_at = initial.updated_at
        saved = await api.patch<Container>(`/api/containers/${initial.id}`, payload)
        if (saved?.docs_warning) showToast(saved.docs_warning, 'error')   // status odprawy mimo braków
      } else {
        delete payload.change_note
        saved = await api.post<Container>('/api/containers', payload)
      }
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const select = (key: keyof typeof form, items: Named[], allLabel: string) => (
    <select aria-label={allLabel} value={String(form[key] ?? '')}
            onChange={e => set(key, e.target.value ? Number(e.target.value) : null)}>
      <option value="">{allLabel}</option>
      {items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
  )

  const [pristine] = useState(() => JSON.stringify(form))
  const close = useDiscardGuard(JSON.stringify(form) !== pristine, onClose)

  return (
    <Modal title={initial ? `${t('edit')}: ${initial.container_no}` : t('addContainer')} onClose={close} busy={busy}>
      <form onSubmit={submit} data-testid="container-form">
        <div className="form-grid">
          <label>{t('containerNo')} *
            <input value={form.container_no} required data-testid="container-no-input"
                   onChange={e => set('container_no', e.target.value.toUpperCase())}
                   placeholder="MSDU0806613" />
          </label>
          {!initial && companyOptions && companyOptions.length > 0 && (
            <label>{t('company')}
              {select('company_id', companyOptions, '—')}
            </label>
          )}
          {!initial && (
            <label>{t('order')}
              <input value={form.order_number ?? ''} onChange={e => set('order_number', e.target.value)} />
            </label>
          )}
          <label>{t('supplier')}
            {select('supplier_id', dicts.suppliers, '—')}
          </label>
          <label>{t('forwarder')}
            {select('forwarder_id', dicts.forwarders, '—')}
          </label>
          <label>{t('warehouse')}
            {select('warehouse_id', dicts.warehouses, '—')}
          </label>
          <label>{t('port')}
            {select('port_id', dicts.ports, '—')}
          </label>
          <label>{t('carriers')}
            {select('carrier_id', dicts.carriers, '—')}
          </label>
          <label>{t('vessel')}
            <input value={form.vessel} onChange={e => set('vessel', e.target.value)} />
          </label>
          <label>{t('eta')}
            <input type="date" value={form.eta ?? ''} onChange={e => set('eta', e.target.value)} />
          </label>
          <label title={t('atdHint')}>{t('atd')}
            <input type="date" value={form.atd ?? ''} onChange={e => set('atd', e.target.value)} />
          </label>
          <label>{t('notifyDate')}
            <input type="date" value={form.notify_date ?? ''} onChange={e => set('notify_date', e.target.value)} />
          </label>
          <label>{t('transport')}
            {/* natywny select nie pokaże ikon — podgląd wybranego trybu pigułką obok */}
            <span className="tr-select">
              <select value={form.transport_type ?? ''} onChange={e => set('transport_type', e.target.value)}>
                <option value="">—</option>
                {TRANSPORT_TYPES.map(v => <option key={v} value={v}>{t(`transport_${v}`)}</option>)}
              </select>
              {form.transport_type && <TransportBadge type={form.transport_type as TransportType} />}
            </span>
          </label>
          <label>{t('onCarriage')}
            <span className="tr-select">
              <select value={form.on_carriage ?? ''} onChange={e => set('on_carriage', e.target.value)}>
                <option value="">—</option>
                {ON_CARRIAGE_TYPES.map(v => <option key={v} value={v}>{t(`transport_${v}`)}</option>)}
              </select>
              {form.on_carriage && <TransportBadge type={form.on_carriage as OnCarriage} />}
            </span>
          </label>
          <label>{t('size')}
            <input value={form.container_size} onChange={e => set('container_size', e.target.value)}
                   placeholder="40'HC" />
          </label>
          <label>{t('customs')}
            <select value={form.customs_status}
                    onChange={e => set('customs_status', e.target.value)}>
              {CUSTOMS_STATUSES.map(s => <option key={s} value={s}>{t(`cs_${s}`)}</option>)}
            </select>
          </label>
          <label>{t('documentStatus')}
            <select value={form.document_status}
                    onChange={e => set('document_status', e.target.value)}>
              {DOCUMENT_STATUSES.map(s => <option key={s} value={s}>{t(`ds_${s}`)}</option>)}
            </select>
          </label>
          {/* A25: agencja tylko ze słownika (panel „Odprawa celna (agencja)”); stary tekst
              bez przypisania ze słownika — do odczytu, wartość zostaje w danych */}
          {initial?.customs_agency && !initial.customs_agency_id && (
            <p className="muted" style={{ gridColumn: '1 / -1', margin: 0, fontSize: 13 }}>
              {t('customsAgencyLegacy').replace('{name}', initial.customs_agency)}
            </p>
          )}
          <label>{t('demurrage')}
            <input type="number" min={0} value={form.demurrage_free_days ?? ''}
                   onChange={e => set('demurrage_free_days', e.target.value)} />
          </label>
          <label>{t('incomingDeliveryNo')}
            <input value={form.incoming_delivery_no} onChange={e => set('incoming_delivery_no', e.target.value)} />
          </label>
          <label>{t('rfNumber')}
            <input value={form.rf_number} onChange={e => set('rf_number', e.target.value)} />
          </label>
          {/* C22: oba pola wyboru w jednym wierszu (Tranzyt nie wisi sam), „Dokumenty kompletne” */}
          <div className="form-checks">
            <label className="check-row">
              <input type="checkbox" checked={form.documents_ok}
                     onChange={e => set('documents_ok', e.target.checked)} />
              {t('frmDocsComplete')}
            </label>
            <label className="check-row" title={t('moduleTransitHint')}>
              <input type="checkbox" checked={form.is_transit}
                     onChange={e => set('is_transit', e.target.checked)} />
              {t('moduleTransit')}
            </label>
          </div>
          <label className="wide">{t('notes')}
            <textarea rows={2} value={form.notes} onChange={e => set('notes', e.target.value)} />
          </label>
          <label>{t('whPallets')}
            <input type="number" min={0} value={form.pallet_count}
                   onChange={e => set('pallet_count', e.target.value)} />
          </label>
          <label className="wide">{t('whMaterials')}
            <textarea rows={2} value={form.materials_list}
                      onChange={e => set('materials_list', e.target.value)} />
          </label>
          <label className="wide">{t('whPalletization')}
            <textarea rows={2} value={form.palletization_note}
                      onChange={e => set('palletization_note', e.target.value)} />
          </label>
          {initial && (
            <label className="wide">{t('changeNote')}
              <input value={form.change_note} onChange={e => set('change_note', e.target.value)}
                     placeholder="np. przeniesiony z 16.06" />
            </label>
          )}
        </div>
        {error && <p className="error" data-testid="form-error">{error}</p>}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={close} disabled={busy}>{t('cancel')}</button>
          <button className="btn" disabled={busy} data-testid="container-submit">{t('save')}</button>
        </div>
      </form>
    </Modal>
  )
}

// Ostrzeżenie przy cofaniu statusu w osi czasu (Task 2 UX foundations) — wspólne dla
// statusu kontenera i celnego: pyta o potwierdzenie i pozwala doprecyzować notatkę audytu.
export function BackwardStatusConfirm({ fromLabel, toLabel, note, onNoteChange, onConfirm, onCancel, noteRequired }: {
  fromLabel: string
  toLabel: string
  note: string
  onNoteChange: (note: string) => void
  onConfirm: () => void
  onCancel: () => void
  noteRequired?: boolean  // D2: cofnięcie statusu kontenera wymaga powodu (backend 422)
}) {
  const t = useT()
  return (
    <Modal title={t('backwardStatusTitle')} onClose={onCancel}>
      <div className="form-col" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <p>{t('backwardStatusWarning')} ({fromLabel} → {toLabel})</p>
        <label>{t(noteRequired ? 'backwardStatusNote' : 'statusNote')}
          <input value={note} onChange={e => onNoteChange(e.target.value)} />
        </label>
        <div className="actions">
          <button type="button" className="btn secondary" onClick={onCancel}>{t('cancel')}</button>
          <button type="button" className="btn" onClick={onConfirm}
                  disabled={noteRequired && !note.trim()}>{t('confirm')}</button>
        </div>
      </div>
    </Modal>
  )
}

export function StatusModal({ container, warehouseRole, onSaved, onClose }: {
  container: Container
  warehouseRole: boolean
  onSaved: (c: Container) => void
  onClose: () => void
}) {
  const t = useT()
  const options: ContainerStatus[] = warehouseRole
    ? ['DOSTARCZONY']   // ZREALIZOWANY ustawia logistyka (decyzja 2026-09-28)
    : [...STATUSES]
  // gdy bieżący status nie należy do dozwolonych (np. magazyn), select startuje z 1. opcji —
  // stan musi się z nim zgadzać, inaczej zapis wysyła wartość niewidoczną w liście
  const [status, setStatus] = useState<ContainerStatus>(
    options.includes(container.status) ? container.status : options[0])
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [confirmBackward, setConfirmBackward] = useState(false)
  const { busy, run } = useBusy()   // dwuklik „Zapisz” = jedna zmiana statusu, nie dwie
  const { showToast } = useToast()

  const doSubmit = (finalNote: string) => run(async () => {
    try {
      const saved = await api.post<Container>(`/api/containers/${container.id}/status`,
        { status, note: finalNote })
      if (saved?.docs_warning) showToast(saved.docs_warning, 'error')   // braki dokumentów: nie blokada
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const fromIdx = STATUSES.indexOf(container.status)
    const toIdx = STATUSES.indexOf(status)
    if (toIdx !== -1 && fromIdx !== -1 && toIdx < fromIdx) {
      setConfirmBackward(true)
      return
    }
    doSubmit(note)
  }

  const close = useDiscardGuard(status !== container.status || note !== '', onClose)

  return (
    <Modal title={`${t('changeStatus')}: ${container.container_no}`} onClose={close} busy={confirmBackward}>
      <form onSubmit={submit} className="form-col" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label>{t('status')}
          <select value={status} onChange={e => setStatus(e.target.value as ContainerStatus)}>
            {options.map(s => <option key={s} value={s}>{t(`st_${s}`)}</option>)}
          </select>
        </label>
        <label>{t('statusNote')}
          <input value={note} onChange={e => setNote(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={close}>{t('cancel')}</button>
          <button className="btn" disabled={busy}>{t('save')}</button>
        </div>
      </form>
      {confirmBackward && (
        <BackwardStatusConfirm
          fromLabel={t(`st_${container.status}`)} toLabel={t(`st_${status}`)}
          note={note} onNoteChange={setNote} noteRequired
          onConfirm={() => { setConfirmBackward(false); doSubmit(note) }}
          onCancel={() => setConfirmBackward(false)}
        />
      )}
    </Modal>
  )
}
