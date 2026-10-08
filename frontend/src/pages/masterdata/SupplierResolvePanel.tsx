// „Do rozstrzygnięcia" (kartoteka dostawców, spec 2026-09-25 §3): po przejściu na jedną
// globalną kartotekę — grupy tego samego kodu SAP (dawne kopie per spółka) do scalenia jednym
// przyciskiem oraz dostawcy bez kodu SAP do decyzji: scal / nieaktywny / usuń (bez powiązań).
// Sekcja „Kopie bez powiązań" (decyzje usera #2/#7/#8, 2026-09-25): masowe kasowanie kopii
// nadawców spółek-klientów bez żadnych powiązań (profil dokumentów chroni rekord — patrz backend supplier_consolidation).
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Supplier } from '../../types'
import { useConfirm } from '../../ConfirmDialog'

interface Brief { id: number; name: string; sap_code: string; country: string; is_active: boolean; usage: number }
// profile_conflict: ≥2 rekordy z profilem dokumentów — „Scal wszystkie” pomija (decyzja usera #9)
interface Group { sap_code: string; target: Brief; sources: Brief[]; profile_conflict?: boolean }
interface Unresolved extends Brief { suggestion: Brief | null }
interface Proposal { merge_groups: Group[]; unresolved: Unresolved[] }
interface OrphanSample { id: number; name: string; company_code: string }
interface OrphansPreview { count: number; by_company: Record<string, number>; sample: OrphanSample[] }

const SHOWN = 50   // ponytail: pierwsze 50 wierszy + licznik; paginacja, gdyby lista realnie tyle miała

// kształt sprawdzany: ogólne mocki api w testach stron zwracają listę dostawców pod /api/suppliers*
const isProposal = (x: unknown): x is Proposal =>
  typeof x === 'object' && x !== null
  && Array.isArray((x as Proposal).merge_groups) && Array.isArray((x as Proposal).unresolved)

const isOrphansPreview = (x: unknown): x is OrphansPreview =>
  typeof x === 'object' && x !== null && typeof (x as OrphansPreview).count === 'number'
  && Array.isArray((x as OrphansPreview).sample)
  && typeof (x as OrphansPreview).by_company === 'object' && (x as OrphansPreview).by_company !== null

export default function SupplierResolvePanel({ suppliers, onChanged }: {
  suppliers: Supplier[]
  onChanged: () => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const [plan, setPlan] = useState<Proposal | null>(null)
  const [orphans, setOrphans] = useState<OrphansPreview | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState<Record<number, string>>({})
  const [confirmN, setConfirmN] = useState('')
  const load = () => {
    api.get<unknown>('/api/suppliers/resolve').then(r => setPlan(isProposal(r) ? r : null)).catch(() => setPlan(null))
    api.get<unknown>('/api/suppliers/resolve/orphans')
      .then(r => setOrphans(isOrphansPreview(r) ? r : null)).catch(() => setOrphans(null))
  }
  useEffect(() => { load() }, [])

  const hasPlan = plan && (plan.merge_groups.length > 0 || plan.unresolved.length > 0)
  const hasOrphans = orphans && orphans.count > 0
  if (!hasPlan && !hasOrphans) return null
  const sapTargets = suppliers.filter(s => s.client_company_id == null && s.sap_code)
  const dupCount = plan ? plan.merge_groups.reduce((n, g) => n + (g.profile_conflict ? 0 : g.sources.length), 0) : 0
  const act = (call: Promise<unknown>, msg: string) => {
    setBusy(true)
    call.then(() => { showToast(msg); load(); onChanged() })
      .catch(err => showToast(errorMessage(err), 'error'))
      .finally(() => setBusy(false))
  }
  const targetOf = (r: Unresolved) => pick[r.id] ?? (r.suggestion ? String(r.suggestion.id) : '')
  // PATCH podmienia wszystkie pola — reszta z wiersza słownika, żeby nie wyczyścić adresu/notatki
  const deactivate = (r: Unresolved) => {
    const s = suppliers.find(x => x.id === r.id)
    act(api.patch(`/api/suppliers/${r.id}`, {
      name: r.name, is_active: false, address: s?.address ?? '', note: s?.note ?? '',
      column_map: s?.column_map ?? '' }), t('supResDone'))
  }
  const remove = async (r: Unresolved) => {
    if (await confirm(`${t('confirmDeleteEntry')} „${r.name}"?`, { danger: true }))
      act(api.del(`/api/suppliers/${r.id}`), t('supResDone'))
  }
  const deleteOrphans = () => {
    if (!orphans || confirmN !== String(orphans.count)) return
    setConfirmN('')
    setBusy(true)
    api.post<{ deleted: number }>('/api/suppliers/resolve/orphans/delete', {})
      .then(r => { showToast(t('supResOrphansDeleted').replace('{n}', String(r.deleted))); load(); onChanged() })
      .catch(err => showToast(errorMessage(err), 'error'))
      .finally(() => setBusy(false))
  }
  return (
    <div className="panel" style={{ margin: '8px 0' }} aria-label={t('supResTitle')}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <b>{t('supResTitle')}</b>
        {plan && <span className="muted">{t('supResSummary')
          .replace('{g}', String(plan.merge_groups.length))
          .replace('{u}', String(plan.unresolved.length))}</span>}
        <button className="btn small secondary" onClick={() => setOpen(o => !o)}>
          {open ? t('supResHide') : t('supResShow')}</button>
      </div>
      {open && plan && plan.merge_groups.length > 0 && (
        <section style={{ marginTop: 8 }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="muted" style={{ flex: '1 1 320px' }}>{t('supResGroupsHint')}</span>
            <button className="btn small" disabled={busy || dupCount === 0}
                    onClick={() => act(api.post('/api/suppliers/resolve/apply', {}),
                                       t('supResMergedAll').replace('{n}', String(dupCount)))}>
              {t('supResMergeAll').replace('{n}', String(dupCount))}</button>
          </div>
          <table className="grid">
            <thead><tr>
              <th>{t('sapCode')}</th><th>{t('supResKeep')}</th><th>{t('supResDuplicates')}</th>
            </tr></thead>
            <tbody>{plan.merge_groups.slice(0, SHOWN).map(g => (
              <tr key={g.sap_code}>
                <td className="mono">{g.sap_code}</td><td>{g.target.name}</td>
                <td>{g.sources.map(s => `${s.name} (${s.usage})`).join(', ')}
                  {g.profile_conflict && <> <span className="badge special">{t('supResProfileConflict')}</span></>}</td>
              </tr>))}</tbody>
          </table>
          {plan.merge_groups.length > SHOWN && <p className="muted">
            {t('supResMore').replace('{n}', String(plan.merge_groups.length - SHOWN))}</p>}
        </section>
      )}
      {open && plan && plan.unresolved.length > 0 && (
        <section style={{ marginTop: 8 }}>
          <p className="muted">{t('supResNoSapHint')}</p>
          <table className="grid">
            <thead><tr>
              <th>{t('name')}</th><th>{t('mdCountry')}</th><th>{t('supResUsage')}</th><th />
            </tr></thead>
            <tbody>{plan.unresolved.slice(0, SHOWN).map(r => (
              <tr key={r.id}>
                <td>{r.name}</td><td>{r.country}</td><td className="mono">{r.usage}</td>
                <td><div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <select aria-label={`${t('mdMergePick')}: ${r.name}`} value={targetOf(r)}
                          onChange={e => setPick(p => ({ ...p, [r.id]: e.target.value }))}>
                    <option value="">— {t('mdMergePick')} —</option>
                    {sapTargets.map(s => (
                      <option key={s.id} value={s.id}>{s.sap_code} · {s.name}</option>))}
                  </select>
                  <button className="btn small" disabled={busy || !targetOf(r)}
                          onClick={() => act(api.post(`/api/suppliers/${r.id}/merge`,
                                                      { target_id: Number(targetOf(r)) }),
                                             t('mdMergeDone'))}>
                    {t('supResMerge')}</button>
                  <button className="btn small secondary" disabled={busy}
                          onClick={() => deactivate(r)}>{t('supResInactive')}</button>
                  <button className="btn small danger" disabled={busy || r.usage > 0}
                          onClick={() => remove(r)}>{t('supResDelete')}</button>
                </div></td>
              </tr>))}</tbody>
          </table>
          {plan.unresolved.length > SHOWN && <p className="muted">
            {t('supResMore').replace('{n}', String(plan.unresolved.length - SHOWN))}</p>}
        </section>
      )}
      {open && orphans && orphans.count > 0 && (
        <section style={{ marginTop: 8 }}>
          <b>{t('supResOrphansTitle').replace('{n}', String(orphans.count))}</b>
          <p className="muted" style={{ margin: '4px 0' }}>{t('supResOrphansHint')}</p>
          <p className="muted">{Object.entries(orphans.by_company)
            .map(([code, n]) => `${code}: ${n}`).join(' · ')}</p>
          {orphans.sample.length > 0 && <p className="muted">{t('supResOrphansSample')
            .replace('{names}', orphans.sample.map(s => s.name).join(', '))}
            {orphans.count > orphans.sample.length
              && ` ${t('supResOrphansMore').replace('{n}', String(orphans.count - orphans.sample.length))}`}</p>}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input type="text" style={{ width: 100 }} value={confirmN}
                   aria-label={t('supResOrphansConfirmLabel').replace('{n}', String(orphans.count))} placeholder={t('supResOrphansConfirmLabel').replace('{n}', String(orphans.count))}
                   onChange={e => setConfirmN(e.target.value)} />
            <button className="btn small danger" disabled={busy || confirmN !== String(orphans.count)}
                    onClick={deleteOrphans}>
              {t('supResOrphansDeleteBtn').replace('{n}', String(orphans.count))}</button>
          </div>
        </section>
      )}
    </div>
  )
}
