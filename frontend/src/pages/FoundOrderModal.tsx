import { useEffect, useRef, useState } from 'react'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { Modal } from '../components'
import { formatNum } from '../dates'
import { useToast } from '../feedback'
import { useT } from '../i18n'
import type {
  ContainerType, FxConvert, MainMode, Port, SeaService, Supplier, SupplierContact,
} from '../types'

// Zakładanie zlecenia (Borealis/Cobalt): jedno zamówienie → N rekordów kontenerów.
// companyId: konkretna spółka (admin) albo null → backend przypisze spółkę użytkownika.
export default function FoundOrderModal({ companyId, companyCode, onDone, onClose }: {
  companyId: number | null
  companyCode: string
  onDone: () => void
  onClose: () => void
}) {
  const t = useT()
  const user = useUser()
  const { showToast } = useToast()

  const [number, setNumber] = useState('')
  const [supplierId, setSupplierId] = useState<number | null>(null)
  const [supplierNew, setSupplierNew] = useState('')
  const [contactId, setContactId] = useState<number | null>(null)
  const [portId, setPortId] = useState<number | null>(null)
  const [typeId, setTypeId] = useState<number | null>(null)
  const [mode, setMode] = useState<MainMode>('SEA')
  const [service, setService] = useState<SeaService>('STANDARD')
  const [count, setCount] = useState('1')
  const [value, setValue] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [goodsType, setGoodsType] = useState('')
  const [isAdr, setIsAdr] = useState(false)
  const [classification, setClassification] = useState('')
  const [readiness, setReadiness] = useState('')
  const [weight, setWeight] = useState('')
  const [notes, setNotes] = useState('')

  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [ports, setPorts] = useState<Port[]>([])
  const [types, setTypes] = useState<ContainerType[]>([])
  const [contacts, setContacts] = useState<SupplierContact[]>([])
  const [fx, setFx] = useState<FxConvert | null>(null)
  const [addingContact, setAddingContact] = useState(false)
  const [cName, setCName] = useState(''); const [cEmail, setCEmail] = useState('')
  const [cPhone, setCPhone] = useState('')

  const [fxPending, setFxPending] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // ładowanie słowników: nie połykaj błędu bez śladu — pusta lista + toast błędu
  // słowniki zależne od spółki: dostawcy zawężeni do zakładki; porty i typy globalne
  useEffect(() => {
    const params = companyCode ? `?company_code=${companyCode}` : ''
    api.get<Supplier[]>(`/api/suppliers${params}`).then(setSuppliers)
      .catch(err => { setSuppliers([]); showToast(errorMessage(err), 'error') })
  }, [companyCode, showToast])
  useEffect(() => {
    api.get<Port[]>('/api/ports').then(setPorts)
      .catch(err => { setPorts([]); showToast(errorMessage(err), 'error') })
    api.get<ContainerType[]>('/api/container-types').then(setTypes)
      .catch(err => { setTypes([]); showToast(errorMessage(err), 'error') })
  }, [showToast])
  // kontakty zależne od wybranego (istniejącego) dostawcy
  useEffect(() => {
    setContactId(null)
    if (supplierId == null) { setContacts([]); return }
    api.get<SupplierContact[]>(`/api/supplier-contacts?supplier_id=${supplierId}`)
      .then(setContacts).catch(err => { setContacts([]); showToast(errorMessage(err), 'error') })
  }, [supplierId, showToast])

  // przewalutowanie NBP — z debounce, best-effort (nie blokuje przy braku dostępu)
  const fxTimer = useRef<number | undefined>(undefined)
  useEffect(() => {
    window.clearTimeout(fxTimer.current)
    const amount = Number(value)
    if (!amount || amount <= 0) { setFx(null); setFxPending(false); return }
    // wyczyść poprzednie przeliczenie (inaczej po zmianie waluty pokazywałoby stare kwoty)
    setFx(null); setFxPending(true)
    fxTimer.current = window.setTimeout(() => {
      api.get<FxConvert>(`/api/fx?amount=${amount}&currency=${currency}`)
        .then(setFx).catch(() => setFx(null))
        .finally(() => setFxPending(false))
    }, 500)
    return () => window.clearTimeout(fxTimer.current)
  }, [value, currency])

  const usingNewSupplier = supplierNew.trim().length > 0
  const port = ports.find(p => p.id === portId)
  const ctype = types.find(t2 => t2.id === typeId)
  // transit time jest sezonowy: bierzemy miesiąc gotowości towaru (a gdy jej nie podano —
  // bieżący), z fallbackiem na wartość domyślną portu, gdy dany miesiąc nie ma danych.
  const transitMonth = readiness ? Number(readiness.slice(5, 7)) : new Date().getMonth() + 1
  const monthlyTransit = port?.monthly_transit?.[String(transitMonth)] ?? null
  const transit = port
    ? (service === 'LONG' ? port.transit_time_long_days
                          : monthlyTransit ?? port.transit_time_days)
    : null

  const addContact = async () => {
    if (supplierId == null || !cName.trim()) return
    try {
      const created = await api.post<SupplierContact>('/api/supplier-contacts', {
        supplier_id: supplierId, full_name: cName.trim(), email: cEmail.trim(), phone: cPhone.trim(),
      })
      setContacts(list => [...list, created])
      setContactId(created.id)
      setAddingContact(false); setCName(''); setCEmail(''); setCPhone('')
    } catch (err) { setError(errorMessage(err)) }
  }

  const submit = async () => {
    setBusy(true); setError('')
    try {
      await api.post('/api/zlecenia', {
        number: number.trim(),
        company_id: companyId,
        company_code: companyCode || null,   // fallback, gdy company_id niedostępne (admin)
        supplier_id: usingNewSupplier ? null : supplierId,
        supplier_name: usingNewSupplier ? supplierNew.trim() : null,
        supplier_contact_id: usingNewSupplier ? null : contactId,
        departure_port_id: portId,
        container_type_id: typeId,
        main_mode: mode,
        sea_service: mode === 'SEA' ? service : null,
        container_count: Math.min(50, Math.max(1, Number(count) || 1)),
        goods_type: goodsType,
        is_adr: isAdr,
        goods_classification: classification,
        goods_value: value.trim() === '' ? null : value,   // '0' to prawidłowa wartość, nie brak
        goods_currency: currency,
        goods_weight: weight,
        readiness_date: readiness || null,
        notes,
      })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally { setBusy(false) }
  }

  const portLabel = (p: Port) =>
    `${p.name} · ${t(`portCat_${p.category}`)}${p.transit_time_days ? ` · ${p.transit_time_days} ${t('zlDays')}` : ''}`

  return (
    <Modal title={`${t('foundOrder')}${companyCode ? ` — ${companyCode}` : ''}`} onClose={onClose} busy={busy} className="found-order">
        <p className="muted" style={{ marginTop: 0, fontSize: 14 }}>{t('foundOrderInfo')}</p>

        <div className="form-grid">
          <label>{t('zlNumber')} *
            <input value={number} onChange={e => setNumber(e.target.value)} placeholder="ZL-2026-001" />
          </label>

          <label>{t('supplier')}
            <select value={String(supplierId ?? '')} disabled={usingNewSupplier}
                    onChange={e => setSupplierId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label>{t('zlSupplierNew')}
            <input value={supplierNew} onChange={e => setSupplierNew(e.target.value)}
                   placeholder="ACME Ltd" />
          </label>

          {supplierId != null && !usingNewSupplier && (
            <label className="wide">{t('zlContact')}
              <div className="row" style={{ gap: 8 }}>
                <select style={{ flex: 1 }} value={String(contactId ?? '')}
                        onChange={e => setContactId(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">{t('zlContactNone')}</option>
                  {contacts.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.full_name}{c.phone ? ` · ${c.phone}` : ''}{c.email ? ` · ${c.email}` : ''}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn small secondary"
                        onClick={() => setAddingContact(v => !v)}>{t('zlContactAdd')}</button>
              </div>
            </label>
          )}
          {addingContact && supplierId != null && (
            <div className="wide contact-add">
              <input aria-label={t('fullName')} placeholder={t('fullName')} value={cName} onChange={e => setCName(e.target.value)} />
              <input aria-label={t('email')} placeholder={t('email')} value={cEmail} onChange={e => setCEmail(e.target.value)} />
              <input aria-label={t('phone')} placeholder={t('phone')} value={cPhone} onChange={e => setCPhone(e.target.value)} />
              <button type="button" className="btn small" disabled={!cName.trim()}
                      onClick={addContact}>{t('save')}</button>
            </div>
          )}

          <label>{t('zlPort')}
            <select value={String(portId ?? '')}
                    onChange={e => setPortId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {ports.map(p => <option key={p.id} value={p.id}>{portLabel(p)}</option>)}
            </select>
          </label>
          <label>{t('zlMode')}
            <select value={mode} onChange={e => setMode(e.target.value as MainMode)}>
              <option value="SEA">{t('mode_SEA')}</option>
              <option value="AIR">{t('mode_AIR')}</option>
              <option value="RAIL">{t('mode_RAIL')}</option>
            </select>
          </label>
          {mode === 'SEA' && (
            <label>{t('zlSeaService')}
              <select value={service} onChange={e => setService(e.target.value as SeaService)}>
                <option value="STANDARD">{t('service_STANDARD')}</option>
                <option value="LONG">{t('service_LONG')}</option>
              </select>
            </label>
          )}
          {mode === 'SEA' && transit != null && (
            <label>{t('zlTransit')}
              <input readOnly value={`${transit} ${t('zlDays')}`} />
            </label>
          )}

          <label>{t('zlContainerType')}
            <select value={String(typeId ?? '')}
                    onChange={e => setTypeId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {types.map(ct => (
                <option key={ct.id} value={ct.id}>
                  {ct.name}{ct.volume_m3 ? ` · ${ct.volume_m3} m³` : ''}
                </option>
              ))}
            </select>
          </label>
          {ctype?.volume_m3 != null && (
            <label>{t('zlVolume')}
              <input readOnly value={`${ctype.volume_m3} m³${ctype.max_payload_kg ? ` · ${ctype.max_payload_kg} kg` : ''}`} />
            </label>
          )}
          <label>{t('zlCount')} *
            <input type="number" min={1} max={50} value={count}
                   onChange={e => setCount(e.target.value)} />
            <span className="muted" style={{ fontSize: 12 }}>
              {Math.max(1, Number(count) || 1)} × {t('zlCountHint')}
            </span>
          </label>

          <label>{t('zlValue')}
            <input type="number" inputMode="decimal" min={0} step="0.01" value={value}
                   onChange={e => setValue(e.target.value)} />
          </label>
          <label>{t('zlCurrency')}
            <select value={currency} onChange={e => setCurrency(e.target.value)}>
              {['USD', 'EUR', 'PLN', 'CNY', 'GBP'].map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          {value && Number(value) > 0 && (
            <div className="wide fx-box">
              {fxPending
                ? <span className="muted">…</span>
                : fx?.available
                ? <>
                    {['PLN', 'EUR', 'USD'].filter(c => c !== currency && fx.converted[c] != null)
                      .map(c => <span key={c} className="fx-chip">
                        {formatNum(fx.converted[c], 2)} {c}</span>)}
                    {fx.as_of && <span className="muted"> · {t('zlNbpAsOf')} {fx.as_of}</span>}
                  </>
                : <span className="muted">{t('zlNbpUnavailable')}</span>}
            </div>
          )}

          <label>{t('zlGoodsType')}
            <input value={goodsType} onChange={e => setGoodsType(e.target.value)} />
          </label>
          <label>{t('zlClassification')}
            <input value={classification} onChange={e => setClassification(e.target.value)} />
          </label>
          <label className="row" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={isAdr} onChange={e => setIsAdr(e.target.checked)} />
            {t('zlAdr')}
          </label>
          <label>{t('zlWeight')}
            <input value={weight} onChange={e => setWeight(e.target.value)} placeholder="12 t" />
          </label>
          <label>{t('zlReadiness')}
            <input type="date" value={readiness} onChange={e => setReadiness(e.target.value)} />
          </label>
          <label>{t('zlOrderedBy')}
            <input readOnly value={user?.full_name || user?.login || ''} />
          </label>
          <label className="wide">{t('notes')}
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
          </label>
        </div>

        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
          <button className="btn" disabled={busy || !number.trim()} onClick={submit}>
            {busy ? t('loading') : t('zlCreate')}
          </button>
        </div>
    </Modal>
  )
}
