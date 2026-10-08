import { useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import { SapSource } from '../../SapSource'
import { TemplateButtons } from '../../importTemplate'
import type { Company } from '../../types'
import Lfa1Preview, { isLfa1Result, type Lfa1Result } from './Lfa1Preview'
import { FilePicker } from '../../FilePicker'

// Zakładka „Jakość danych" (#16/#17/#18): raport walidatora + świeżość importów
// + wspólny dropzone „Wgraj plik master data" (typ rozpoznaje backend po nagłówkach).

export interface QualityIssue {
  key: string
  tab: string
  count: number
  items: { id: number; label: string }[]
}

export interface ImportFreshness {
  type: string
  last_at: string | null
  age_days: number | null
  stale: boolean
}

interface QualityPayload {
  issues: QualityIssue[]
  imports: ImportFreshness[]
  stale_import_days: number
}

const IMPORT_LABELS: Record<string, string> = {
  marm: 'MARM (jednostki materiałów)',
  ekko: 'EKKO (zamówienia SAP)',
  lfa1: 'LFA1 (dostawcy)',
  cports: 'Porty kontenerowe',
}

// klucz reguły backendu → klucz i18n etykiety
const ISSUE_KEYS: Record<string, string> = {
  suppliers_no_sap: 'qSuppliersNoSap',
  suppliers_no_country: 'qSuppliersNoCountry',
  suppliers_dup_names: 'qSuppliersDup',
  cports_no_coords: 'qCportsNoCoords',
  materials_no_pal: 'qMaterialsNoPal',
  units_no_dims: 'qUnitsNoDims',
  containers_no_warehouse: 'qContainersNoWh',
  containers_no_po: 'qContainersNoPo',
  containers_no_eta: 'qContainersNoEta',
}

function Dropzone({ companies, onDone }: { companies: Company[]; onDone: () => void }) {
  const t = useT()
  const { showToast } = useToast()
  const [companyCode, setCompanyCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<{ file: File; detected: string;
    summary: string; lfa1: Lfa1Result | null; disappeared: number } | null>(null)
  const [fullExport, setFullExport] = useState(false)
  const [report, setReport] = useState<{ id: number; errors: number } | null>(null)

  const url = (dry: boolean) =>
    `/api/import/master-data?dry_run=${dry}${companyCode ? `&company_code=${companyCode}` : ''}`
    + (fullExport ? '&full_export=true' : '')

  const analyze = (file: File) => {
    setBusy(true)
    api.upload<Record<string, unknown>>(url(true), file)
      .then(r => {
        const lfa1 = isLfa1Result(r) ? r : null
        setFullExport(false)
        setReport(null)
        const counts = r.counts as { disappeared?: number } | undefined
        setPreview({ file, detected: String(r.detected), lfa1, disappeared: counts?.disappeared ?? 0,
                     summary: lfa1 ? '' : JSON.stringify(r.counts ?? r.companies ?? {}, null, 0) })
      })
      .catch(err => { setPreview(null); showToast(errorMessage(err), 'error') })
      .finally(() => setBusy(false))
  }

  const commit = () => {
    if (!preview) return
    setBusy(true)
    api.upload<{ import_id?: number; counts?: { errors?: number } }>(url(false), preview.file)
      .then(r => {
        showToast(t('qImportDone'))
        if (r.import_id && r.counts?.errors) setReport({ id: r.import_id, errors: r.counts.errors })
        setPreview(null)
        onDone()
      })
      .catch(err => showToast(errorMessage(err), 'error'))
      .finally(() => setBusy(false))
  }

  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <h3 style={{ marginTop: 0 }}>{t('qUpload')}{' '}
        {(['MARM', 'EKKO', 'LFA1'] as const).map(tb => <SapSource key={tb} table={tb} />)}</h3>
      <div
        data-testid="md-dropzone"
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) analyze(f) }}
        style={{ border: '2px dashed var(--line)', borderRadius: 8, padding: 16,
                 display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm,.tsv,.csv,.txt" disabled={busy}
                    onChange={f => { if (f) analyze(f) }} />
        <TemplateButtons kinds={['marm', 'ekko', 'lfa1', 'ports']} />
        <select value={companyCode} onChange={e => setCompanyCode(e.target.value)}
                title={t('qCompanyHint')}>
          <option value="">— {t('company')} (EKKO) —</option>
          {companies.map(c => <option key={c.id} value={c.code}>{c.name}</option>)}
        </select>
        <span className="muted">{t('qUploadHint')}</span>
      </div>
      {preview && (
        <p style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span>{t('qDetected')}: <b>{IMPORT_LABELS[preview.detected] ?? preview.detected}</b>
            {' '}<span className="muted">{preview.summary}</span></span>
          <button className="btn small" disabled={busy} onClick={commit}>
            {t('qConfirmImport')}</button>
          <button className="btn small secondary" onClick={() => setPreview(null)}>
            {t('cancel')}</button>
        </p>
      )}
      {preview && !preview.lfa1 && preview.disappeared > 0 && ['ekko', 'marm'].includes(preview.detected) && (
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={fullExport} onChange={e => setFullExport(e.target.checked)} />
          {t('sapFullExport').replace('{n}', String(preview.disappeared))}
        </label>)}
      {preview?.lfa1 && <Lfa1Preview data={preview.lfa1} fullExport={fullExport} onFullExport={setFullExport} />}
      {report && (
        <p className="muted">{t('lfa1ReportDone').replace('{n}', String(report.errors))}{' '}
          <button className="btn small secondary"
                  onClick={() => downloadFile(`/api/import/sap-imports/${report.id}/errors.xlsx`,
                                              `import-lfa1-${report.id}-bledy.xlsx`)}>
            {t('lfa1ReportBtn')}</button></p>
      )}
    </div>
  )
}

export default function QualityTab({ companies, onGoTab }: {
  companies: Company[]
  onGoTab: (tab: string) => void
}) {
  const t = useT()
  const [data, setData] = useState<QualityPayload | null>(null)
  const [ver, setVer] = useState(0)
  useEffect(() => {
    api.get<QualityPayload>('/api/master-data/quality').then(setData).catch(() => {})
  }, [ver])

  if (!data) return <p className="muted">{t('loading')}</p>
  const problems = data.issues.filter(i => i.count > 0)
  return (
    <div>
      <Dropzone companies={companies} onDone={() => setVer(v => v + 1)} />

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>{t('qImports')}
          {' '}<span className="muted">({t('qStaleThreshold')}: {data.stale_import_days} d)</span></h3>
        <table className="grid"><tbody>
          {data.imports.map(f => (
            <tr key={f.type}>
              <td>{IMPORT_LABELS[f.type] ?? f.type}</td>
              <td>{f.age_days == null ? t('qNever') : `${f.age_days} ${t('qDaysAgo')}`}</td>
              <td>{f.stale && <span className="badge danger">{t('qStale')}</span>}</td>
            </tr>
          ))}
        </tbody></table>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t('qIssues')}</h3>
        {!problems.length && <p className="muted">{t('qNoIssues')}</p>}
        {problems.map(issue => (
          <details key={issue.key} style={{ marginBottom: 8 }}>
            <summary style={{ cursor: 'pointer' }}>
              <b>{t(ISSUE_KEYS[issue.key] as never) || issue.key}</b>: {issue.count}
              {issue.tab && (
                <button className="btn small secondary" style={{ marginLeft: 8 }}
                        onClick={e => { e.preventDefault(); onGoTab(issue.tab) }}>
                  {t('qGoTab')}</button>
              )}
            </summary>
            <ul>
              {issue.items.map(item => <li key={item.id}>{item.label}</li>)}
              {issue.count > issue.items.length && (
                <li className="muted">…+{issue.count - issue.items.length}</li>
              )}
            </ul>
          </details>
        ))}
      </div>
    </div>
  )
}
