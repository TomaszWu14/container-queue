import { CircleCheckIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Material, MaterialOverride, MlStats } from '../../types'
import { TemplateButtons } from '../../importTemplate'
import { DictTable, dash, useCompanies } from './shared'
import { formatDateTime } from '../../dates'
import { FilePicker } from '../../FilePicker'

interface ImportResult { dry_run: boolean; counts: { total: number; new: number; updated: number; conversions: number } }

const emptyOverride = (companyId: number): MaterialOverride =>
  ({ company_id: companyId, name_pl: '', tariff_cn: '', customs_code: '', base_uom: '', sent: null })

/** Master data materiałów: import xlsx (podgląd → zapis), wyszukiwarka i nadpisania per spółka. */
export default function MaterialsTab() {
  const t = useT()
  const { showToast } = useToast()
  const companies = useCompanies()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [count, setCount] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [items, setItems] = useState<Material[]>([])
  const [overrideFor, setOverrideFor] = useState<number | null>(null)
  const [override, setOverride] = useState<MaterialOverride | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ml, setMl] = useState<MlStats | null>(null)

  const loadCount = () => api.get<{ count: number }>('/api/materials/count')
    .then(r => setCount(r.count)).catch(() => {})
  const loadMl = () => api.get<MlStats>('/api/materials/ml/stats').then(setMl).catch(() => {})
  const train = async () => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setMl(await api.post<MlStats>('/api/materials/ml/train', {}))
      showToast(t('mlTrained'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  // numer żądania: wynik starszego (wolniejszego) wyszukiwania nie nadpisze nowszego
  const searchSeq = useRef(0)
  const search = (query = q) => {
    const my = ++searchSeq.current
    return api.get<Material[]>(
      `/api/materials?q=${encodeURIComponent(query)}&limit=100&include_inactive=true`)
      .then(r => { if (my === searchSeq.current) setItems(r) })
      .catch(err => { if (my === searchSeq.current) setError(errorMessage(err)) })
  }
  const toggleActive = async (m: Material) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.patch<Material>(`/api/materials/${m.id}`, { is_active: !m.is_active })
      setItems(list => list.map(x => (x.id === m.id ? updated : x)))
      loadCount()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { loadCount(); loadMl(); search('') }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const runImport = async (dryRun: boolean) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const body = await api.upload<ImportResult>(`/api/materials/import?dry_run=${dryRun}`, file)
      if (dryRun) setPreview(body)
      else {
        setResult(body)
        setPreview(null)
        showToast(t('importDone'))
        loadCount()
        loadMl()
        search()
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const openOverride = (m: Material, companyId: number) => {
    const existing = m.overrides.find(o => o.company_id === companyId)
    setOverrideFor(m.id)
    setOverride(existing ? { ...existing } : emptyOverride(companyId))
  }

  const saveOverride = async () => {
    if (!override || overrideFor === null || busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.put<Material>(`/api/materials/${overrideFor}/override`, override)
      setItems(list => list.map(m => (m.id === updated.id ? updated : m)))
      setOverrideFor(null)
      showToast(t('matOverrideSaved'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const Summary = ({ r }: { r: ImportResult }) => (
    <span className="import-counts">
      <span className="badge st-DOSTARCZONY">{r.counts.new} {t('importNew')}</span>
      <span className="badge st-W_TRANSPORCIE">{r.counts.updated} {t('importUpdated')}</span>
      <span className="badge st-ZREALIZOWANY">{r.counts.conversions} {t('importConversions')}</span>
    </span>
  )

  const companyName = (id: number) => companies.find(c => c.id === id)?.name ?? `#${id}`

  return (
    <div className="panel">
      <h3>{t('materials')}{count !== null && <span className="muted"> · {count} {t('materialsCount')}</span>}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>{t('materialsHint')}</p>
      <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <FilePicker label={t('materialsImport')} caption={t('materialsImport')} accept=".xlsx,.xlsm"
                    disabled={busy} file={file} onChange={f => { setFile(f); setPreview(null); setResult(null) }} />
        <TemplateButtons kinds={['materials']} />
        {!preview && (
          <button className="btn" disabled={!file || busy} onClick={() => runImport(true)}>
            {busy ? t('loading') : t('importPreviewBtn')}
          </button>
        )}
        {preview && (
          <>
            <Summary r={preview} />
            <button className="btn" disabled={busy || preview.counts.total === 0} onClick={() => runImport(false)}>
              {busy ? t('loading') : `${t('importCommitBtn')} (${preview.counts.total})`}
            </button>
          </>
        )}
        {result && <p className="import-done" style={{ margin: 0 }}><CircleCheckIcon size={14} /> {t('importDone')} — <Summary r={result} /></p>}
      </div>
      {error && <p className="error">{error}</p>}

      <div className="panel" style={{ margin: '14px 0 0', padding: 10 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <b>{t('mlTitle')}</b>
          <button className="btn small secondary" disabled={busy} onClick={train}>{t('mlTrain')}</button>
        </div>
        <p className="muted" style={{ fontSize: 13, margin: '6px 0' }}>{t('mlHint')}</p>
        {ml && (
          <div className="import-counts" style={{ fontSize: 13 }}>
            <span className="badge st-ZREALIZOWANY">{ml.ref_materials} {t('mlRefMaterials')}</span>
            <span className="badge st-DOSTARCZONY">{ml.ref_examples} {t('mlRefExamples')}</span>
            <span className={`badge ${ml.dockind_trained ? 'st-DOSTARCZONY' : 'st-ZREALIZOWANY'}`}>
              {t('mlDockind')}: {ml.dockind_trained ? t('mlDockindOn') : t('mlDockindOff')}
              {' '}({ml.dockind_examples}/{ml.min_examples})
            </span>
            <span className="muted">{t('mlAutoApply')}: {Math.round(ml.auto_apply_threshold * 100)}%</span>
            {ml.ref_trained_at && <span className="muted">{t('mlTrainedAt')}: {formatDateTime(ml.ref_trained_at)}</span>}
          </div>
        )}
      </div>

      <form className="row" style={{ margin: '14px 0 8px' }} onSubmit={e => { e.preventDefault(); search() }}>
        <input aria-label={t('materialsSearch')} placeholder={t('materialsSearch')} value={q} onChange={e => setQ(e.target.value)}
               style={{ minWidth: 260 }} />
        <button className="btn secondary" type="submit" disabled={busy}>{t('matSearchBtn')}</button>
      </form>
      {items.length === 0 && <p className="muted">{t('materialsNoResults')}</p>}
      {items.length > 0 && (
        <DictTable cols={[t('matRef'), t('matNamePl'), t('matCn'), t('matUom'),
                          { label: t('matSent'), width: '70px' }, t('matEan'), t('matOverrides'),
                          { width: '220px' }]}>
          {items.map(m => (
            <tr key={m.id} className={m.is_active ? '' : 'muted'}>
              <td className="mono">{m.ref_code}{!m.is_active && <span className="badge st-OPOZNIONY" style={{ marginLeft: 6 }}>{t('matInactive')}</span>}</td>
              <td>{dash(m.name_pl)}</td>
              <td>{dash(m.tariff_cn || m.customs_code)}</td>
              <td>{dash(m.base_uom)}</td>
              <td>{m.sent ? 'TAK' : 'NIE'}</td>
              <td className="mono">{dash(m.ean)}</td>
              <td style={{ fontSize: 13 }}>
                {m.overrides.length === 0 ? dash('') : m.overrides.map(o => (
                  <div key={o.company_id}>
                    <b>{companyName(o.company_id)}</b>: {[o.name_pl, o.tariff_cn || o.customs_code, o.base_uom,
                      o.sent === null ? '' : (o.sent ? 'SENT' : 'bez SENT')].filter(Boolean).join(' · ')}
                  </div>
                ))}
              </td>
              <td>
                {overrideFor === m.id && override ? (
                  <div style={{ display: 'grid', gap: 4 }}>
                    <select aria-label={t('company')} value={override.company_id}
                            onChange={e => openOverride(m, Number(e.target.value))}>
                      {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                    <input aria-label={t('matNamePl')} placeholder={t('matNamePl')} value={override.name_pl}
                           onChange={e => setOverride({ ...override, name_pl: e.target.value })} />
                    <input aria-label={t('matCn')} placeholder={t('matCn')} value={override.tariff_cn}
                           onChange={e => setOverride({ ...override, tariff_cn: e.target.value })} />
                    <input aria-label={t('matUom')} placeholder={t('matUom')} value={override.base_uom}
                           onChange={e => setOverride({ ...override, base_uom: e.target.value })} />
                    <select value={override.sent === null ? '' : String(override.sent)}
                            aria-label={t('matSent')}
                            onChange={e => setOverride({ ...override,
                              sent: e.target.value === '' ? null : e.target.value === 'true' })}>
                      <option value="">{t('matSent')}: {t('matSentInherit')}</option>
                      <option value="true">{t('matSent')}: TAK</option>
                      <option value="false">{t('matSent')}: NIE</option>
                    </select>
                    <span className="muted" style={{ fontSize: 12 }}>{t('matOverrideHint')}</span>
                    <span className="row">
                      <button className="btn small" disabled={busy} onClick={saveOverride}>{t('save')}</button>
                      <button className="btn small secondary" onClick={() => setOverrideFor(null)}>{t('cancel')}</button>
                    </span>
                  </div>
                ) : (
                  <span className="row">
                    <button className="btn small secondary" disabled={companies.length === 0}
                            onClick={() => openOverride(m, companies[0].id)}>
                      {t('matOverride')}
                    </button>
                    <button className="btn small secondary" disabled={busy} onClick={() => toggleActive(m)}>
                      {t(m.is_active ? 'matDeactivate' : 'matActivate')}
                    </button>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </DictTable>
      )}
    </div>
  )
}
