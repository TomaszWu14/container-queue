import { Fragment, FormEvent, useContext, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { LangContext, localeFor, useT } from '../../i18n'
import type { Named, Supplier } from '../../types'
import { AddCancel, EditActions, DictCol, DictTable, dash, dupKey, useCompanies } from './shared'
import { LoadError, Skeleton, useToast } from '../../feedback'
import { useConfirm } from '../../ConfirmDialog'

// manageable: słowniki, które backend pozwala czyścić po imporcie z Excela
// (edycja nazwy, dezaktywacja, usuwanie, scalanie duplikatów) — porty, dostawcy, armatorzy.
// Spedytorzy tego nie mają: nie są zaśmieceni, a merge dotykałby wycen i zleceń.
// extraFields: dodatkowe pola tekstowe słownika (np. telefon/adres spedytora) —
// renderowane w formularzu dodawania, kolumnach i edycji inline. Domyślnie brak.
// options: pole wyboru zamiast tekstu (np. język awizacji spedytora pl/en); pierwsza = domyślna
export interface ExtraField { key: string; label: string; textarea?: boolean; hint?: string; options?: string[] }

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

// monthlyTransit: słownik portów trzyma transit time per miesiąc (profil sezonowy).
// Edycja w rozwijanym wierszu, bo 12 pól nie zmieści się w kolumnie.
export default function NamedTab({ endpoint, withCompany = false, withEmail = false,
                                   manageable = false, extraFields = [],
                                   monthlyTransit = false }:
                  { endpoint: string; withCompany?: boolean; withEmail?: boolean
                    manageable?: boolean; extraFields?: ExtraField[]
                    monthlyTransit?: boolean }) {
  const t = useT()
  const { confirm } = useConfirm()
  const { lang } = useContext(LangContext)
  // nazwy miesięcy z Intl — 36 kluczy w słowniku nic by nie dodało
  const monthLabel = (m: number) => new Intl.DateTimeFormat(localeFor(lang), { month: 'short' })
    .format(new Date(2026, m - 1, 1))
  const { showToast } = useToast()
  const companies = useCompanies()
  const [items, setItems] = useState<(Named & { company_id?: number })[]>([])
  const [name, setName] = useState('')
  const [companyId, setCompanyId] = useState('')
  const [email, setEmail] = useState('')
  const [extra, setExtra] = useState<Record<string, string>>({})
  const [editId, setEditId] = useState<number | null>(null)
  const [editEmail, setEditEmail] = useState('')
  const [editName, setEditName] = useState('')
  const [editExtra, setEditExtra] = useState<Record<string, string>>({})
  const [onlyDups, setOnlyDups] = useState(false)
  const [ttId, setTtId] = useState<number | null>(null)
  const [ttValues, setTtValues] = useState<Record<string, string>>({})
  const [mergeId, setMergeId] = useState<number | null>(null)
  const [mergeTarget, setMergeTarget] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)

  // include_inactive: bez tego dezaktywowany wpis zniknąłby też adminowi i nie dałoby się
  // go już przywrócić. Listy wyboru w reszcie panelu nadal dostają tylko aktywne.
  // numer żądania: po zmianie zakładki wolna odpowiedź starego endpointu jest ignorowana
  const seq = useRef(0)
  const load = () => {
    const my = ++seq.current
    setLoading(true)
    setLoadError('')
    api.get<Supplier[]>(manageable ? `${endpoint}?include_inactive=true` : endpoint)
      .then(r => { if (my === seq.current) setItems(r) })
      .catch(err => { if (my === seq.current) setLoadError(errorMessage(err)) })
      .finally(() => { if (my === seq.current) setLoading(false) })
  }
  useEffect(() => { load() }, [endpoint, manageable]) // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await fn()
      setEditId(null)
      setMergeId(null)
      setTtId(null)
      showToast(t('toastSaved'))
      load()
    } catch (err) {
      setError(errorMessage(err))   // np. 409 „w użyciu (12) — scal albo dezaktywuj”
    } finally {
      setBusy(false)
    }
  }

  // Raport duplikatów = zaznaczenie ich w tej samej tabeli, obok gotowego „Scal”.
  // Osobny ekran nic by nie dodał: scalanie i tak robi się w wierszu.
  const dupIds = (() => {
    const byKey = new Map<string, number[]>()
    for (const item of items) {
      const k = dupKey(item.name, withCompany ? item.company_id : undefined)
      byKey.set(k, [...(byKey.get(k) ?? []), item.id])
    }
    return new Set([...byKey.values()].filter(ids => ids.length > 1).flat())
  })()

  // scalać można tylko w obrębie spółki — backend to wymusza (409), UI nie powinno kusić
  const mergeCandidates = (item: Named & { company_id?: number }) =>
    items.filter(other => other.id !== item.id
                 && (!withCompany || other.company_id === item.company_id))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const body: Record<string, unknown> = { name, ...extra }
      if (withCompany && companyId) body.company_id = Number(companyId)
      if (withEmail) body.email = email
      await api.post(endpoint, body)
      setName('')
      setEmail('')
      setExtra({})
      showToast(t('toastSaved'))
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const companyName = (id?: number) => companies.find(c => c.id === id)?.name ?? ''

  const hasActions = withEmail || manageable || extraFields.length > 0 || monthlyTransit

  const openTransit = (item: Named & { company_id?: number }) => {
    const current = (item as unknown as { monthly_transit?: Record<string, number> })
      .monthly_transit ?? {}
    setTtId(item.id)
    setTtValues(Object.fromEntries(MONTHS.map(m => [String(m), String(current[m] ?? '')])))
  }

  // puste pole = brak danych dla tego miesiąca (zadziała fallback), nie zero
  const saveTransit = (item: Named) => act(() => api.patch(`${endpoint}/${item.id}`, {
    ...item,
    monthly_transit: Object.fromEntries(Object.entries(ttValues)
      .filter(([, v]) => v.trim() !== '').map(([m, v]) => [m, Number(v)])),
  }))
  const cols: DictCol[] = [
    t('name'),
    ...(withCompany ? [t('company')] : []),
    ...(withEmail ? [t('email')] : []),
    ...extraFields.map(f => f.label),
    ...(manageable ? [{ label: t('active'), width: '90px' }] : []),
    // kolumna akcji: przy manageable mieści edycję, scalanie i usuwanie (+ select scalania)
    ...(hasActions ? [{ width: manageable ? '300px' : '110px' }] : []),
  ]

  return (
    <div className="panel">
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={name} required onChange={e => setName(e.target.value)} />
        {withCompany && (
          <select aria-label={t('company')} value={companyId} onChange={e => setCompanyId(e.target.value)}>
            <option value="">— {t('company')} —</option>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
        {withEmail && (
          <input type="email" aria-label={t('email')} placeholder={t('email')} value={email}
                 onChange={e => setEmail(e.target.value)} />
        )}
        {extraFields.map(f => f.options ? (
          <select key={f.key} title={f.label} aria-label={f.label} value={extra[f.key] ?? f.options[0]}
                  onChange={e => setExtra(x => ({ ...x, [f.key]: e.target.value }))}>
            {f.options.map(o => <option key={o} value={o}>{o.toUpperCase()}</option>)}
          </select>
        ) : (
          <input key={f.key} placeholder={f.label} title={f.hint} value={extra[f.key] ?? ''}
                 onChange={e => setExtra(x => ({ ...x, [f.key]: e.target.value }))} />
        ))}
        <AddCancel dirty={!!(name || companyId || email || Object.values(extra).some(Boolean))}
                   onReset={() => { setName(''); setCompanyId(''); setEmail(''); setExtra({}) }} />
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {manageable && (
        <p className="muted" style={{ marginTop: 0 }}>
          {t('mergeHint')}
          {dupIds.size > 0 && (
            <>
              {' '}
              <button type="button" className="btn small secondary"
                      aria-pressed={onlyDups} onClick={() => setOnlyDups(v => !v)}>
                {onlyDups ? t('dupAll') : `${t('dupOnly')} (${dupIds.size})`}
              </button>
            </>
          )}
        </p>
      )}
      {loading && items.length === 0 && <Skeleton rows={4} />}
      {!loading && loadError && items.length === 0 && <LoadError message={loadError} onRetry={load} />}
      <DictTable cols={cols}>
        {items.filter(item => !onlyDups || dupIds.has(item.id)).map(item => (
          <Fragment key={item.id}>
          <tr className={manageable && item.is_active === false ? 'muted' : ''}>
            <td>
              {manageable && editId === item.id ? (
                <input aria-label={t('name')} value={editName} autoFocus onChange={e => setEditName(e.target.value)} />
              ) : (
                <>
                  {item.name}
                  {manageable && dupIds.has(item.id) &&
                    <span className="dup-mark" title={t('dupHint')}> {t('dupMark')}</span>}
                  {manageable && item.is_active === false &&
                    <span className="muted"> · {t('inactiveMark')}</span>}
                </>
              )}
            </td>
            {withCompany && <td>{companyName(item.company_id)}</td>}
            {withEmail && (
              <td>
                {editId === item.id ? (
                  <input aria-label={t('email')} type="email" value={editEmail} autoFocus
                         onChange={e => setEditEmail(e.target.value)} />
                ) : dash(item.email)}
              </td>
            )}
            {extraFields.map(f => (
              <td key={f.key}>
                {editId === item.id ? (f.options ? (
                  <select value={editExtra[f.key] || f.options[0]} aria-label={f.label}
                          onChange={e => setEditExtra(x => ({ ...x, [f.key]: e.target.value }))}>
                    {f.options.map(o => <option key={o} value={o}>{o.toUpperCase()}</option>)}
                  </select>
                ) : (
                  <input value={editExtra[f.key] ?? ''} title={f.hint} placeholder={f.hint}
                         onChange={e => setEditExtra(x => ({ ...x, [f.key]: e.target.value }))} />
                )) : dash((item as unknown as Record<string, unknown>)[f.key])}
              </td>
            ))}
            {manageable && (
              <td>
                <input type="checkbox" checked={item.is_active !== false}
                       aria-label={t('active')}
                       onChange={e => act(() => api.patch(`${endpoint}/${item.id}`,
                         { ...item, is_active: e.target.checked }))} />
              </td>
            )}
            {hasActions && (
              <td>
                {mergeId === item.id ? (
                  // scalanie: wskaż rekord docelowy — powiązania item przejdą na niego
                  <span className="row">
                    <select aria-label={t('mergeInto')} value={mergeTarget} autoFocus
                            onChange={e => setMergeTarget(e.target.value)}>
                      <option value="">— {t('mergeInto')} —</option>
                      {mergeCandidates(item).map(other => (
                        <option key={other.id} value={other.id}>{other.name}</option>
                      ))}
                    </select>
                    <button className="btn small" disabled={!mergeTarget || busy}
                            onClick={async () => (await confirm(t('confirmMerge'), { danger: true }))
                              && act(() => api.post(`${endpoint}/${item.id}/merge`,
                                { target_id: Number(mergeTarget) }))}>
                      {t('merge')}
                    </button>
                    <button className="btn small secondary"
                            onClick={() => { setMergeId(null); setMergeTarget('') }}>
                      {t('mergeCancel')}
                    </button>
                  </span>
                ) : editId === item.id ? (
                  <EditActions busy={busy} onCancel={() => setEditId(null)}
                               dirty={editName !== item.name || editEmail !== (item.email ?? '') || extraFields.some(f =>
                                 (editExtra[f.key] ?? '') !== String((item as unknown as Record<string, unknown>)[f.key] ?? ''))}
                               onSave={() => act(() => api.patch(
                                 `${endpoint}/${item.id}`,
                                 { ...item, name: manageable ? editName : item.name,
                                   email: editEmail, ...editExtra }))} />
                ) : (
                  <span className="row">
                    <button className="btn small secondary" onClick={() => {
                      setEditId(item.id)
                      setEditName(item.name)
                      setEditEmail(item.email ?? '')
                      setEditExtra(Object.fromEntries(extraFields.map(f =>
                        [f.key, String((item as unknown as Record<string, unknown>)[f.key] ?? '')])))
                    }}>{t('edit')}</button>
                    {monthlyTransit && (
                      <button className="btn small secondary" onClick={() => openTransit(item)}>
                        {t('transitMonthly')}
                      </button>
                    )}
                    {manageable && (
                      <>
                        <button className="btn small secondary"
                                onClick={() => { setMergeId(item.id); setMergeTarget('') }}>
                          {t('merge')}
                        </button>
                        {/* usuwanie tylko dla nieużywanych — backend odbija 409 z liczbą
                            powiązań, komunikat trafia do setError i podpowiada scalanie */}
                        <button className="btn small danger"
                                onClick={async () => (await confirm(`${t('confirmDeleteEntry')} „${item.name}"?`, { danger: true }))
                                  && act(() => api.del(`${endpoint}/${item.id}`))}>
                          {t('del')}
                        </button>
                      </>
                    )}
                  </span>
                )}
              </td>
            )}
          </tr>
          {monthlyTransit && ttId === item.id && (
            <tr>
              <td colSpan={cols.length}>
                <div className="panel" style={{ padding: 8 }}>
                  <p className="muted" style={{ marginTop: 0 }}>{t('transitMonthlyHint')}</p>
                  <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
                    {MONTHS.map(m => (
                      <label key={m} style={{ display: 'grid', fontSize: 13 }}>
                        {monthLabel(m)}
                        <input type="number" min={0} max={200} style={{ width: 70 }}
                               value={ttValues[String(m)] ?? ''}
                               onChange={e => setTtValues(v =>
                                 ({ ...v, [String(m)]: e.target.value }))} />
                      </label>
                    ))}
                  </div>
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="btn small" disabled={busy}
                            onClick={() => saveTransit(item)}>{t('save')}</button>
                    <button className="btn small secondary"
                            onClick={() => setTtId(null)}>{t('mergeCancel')}</button>
                  </div>
                </div>
              </td>
            </tr>
          )}
          </Fragment>
        ))}
      </DictTable>
    </div>
  )
}
