import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { TemplateButtons } from '../importTemplate'
import { useToast } from '../feedback'
import { StatusBadge } from '../components'
import type { ContainerStatus } from '../types'
import { FilePicker } from '../FilePicker'

interface UploadReport {
  rows_count: number
  errors: string[]
  duplicates: number
  unknown_products: string[]
  saved: boolean
}

interface NamedCount { name: string; count: number }
interface OperationalKpi {
  total: number
  by_status: Record<string, number>
  throughput: { month: string; count: number }[]
  avg_lead_time_days: number | null
  avg_unload_minutes: number | null
  top_suppliers: NamedCount[]
  top_warehouses: NamedCount[]
}

export default function AnalitykaPage() {
  const t = useT()
  const { showToast } = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<UploadReport | null>(null)
  const [uploadError, setUploadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [kpi, setKpi] = useState<OperationalKpi | null>(null)
  const [kpiError, setKpiError] = useState('')

  useEffect(() => {
    api.get<OperationalKpi>('/api/analytics/operational')
      .then(setKpi).catch(err => setKpiError(errorMessage(err)))
  }, [])

  const maxThroughput = kpi ? Math.max(1, ...kpi.throughput.map(m => m.count)) : 1

  const doUpload = async (commit: boolean) => {
    if (!file) return
    setUploadError('')
    setBusy(true)
    try {
      const r = await api.upload<UploadReport>(`/api/analytics/upload?commit=${commit}`, file)
      setReport(r)
      if (r.saved) showToast(t('toastSaved'))
    } catch (err) {
      setUploadError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <h1>{t('anTitle')}</h1>

      {/* S11: w trakcie ładowania panel trzyma przybliżoną wysokość — dane historyczne niżej nie skaczą */}
      <div className={`panel an-kpi${kpi ? '' : ' loading'}`}>
        <h2>{t('anKpiTitle')}</h2>
        {kpiError && <p className="error">{kpiError}</p>}
        {!kpi && !kpiError && <p>{t('loading')}</p>}
        {kpi && (
          <>
            <div className="kpi-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
              <div className="kpi-tile"><b style={{ fontSize: 26 }}>{kpi.total}</b><div>{t('anKpiTotal')}</div></div>
              <div className="kpi-tile"><b style={{ fontSize: 26 }}>{kpi.avg_lead_time_days ?? '—'}</b><div>{t('anKpiLeadTime')}</div></div>
              <div className="kpi-tile"><b style={{ fontSize: 26 }}>{kpi.avg_unload_minutes ?? '—'}</b><div>{t('anKpiUnload')}</div></div>
            </div>
            <h3>{t('anKpiThroughput')}</h3>
            {/* B22: same etykiety osi bez słupków wyglądały jak błąd — przy zerach komunikat */}
            {!kpi.throughput.some(m => m.count > 0) ? <p className="muted">{t('anThroughputEmpty')}</p> : (
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120, marginBottom: 16 }}>
              {kpi.throughput.map(m => (
                <div key={m.month} style={{ textAlign: 'center', flex: 1 }} title={`${m.month}: ${m.count}`}>
                  <div style={{ background: 'var(--accent, #8a5c00)',
                                height: `${Math.round((m.count / maxThroughput) * 90)}px`,
                                minHeight: m.count ? 2 : 0, borderRadius: 3 }} />
                  <small style={{ fontSize: 10, color: 'var(--muted)' }}>{m.month.slice(5)}</small>
                </div>
              ))}
            </div>)}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24 }}>
              <div>
                <h3>{t('anKpiByStatus')}</h3>
                {/* B23: etykiety statusów jak w kolejce (StatusBadge), nie surowe kody enum */}
                <table className="grid"><tbody>{Object.entries(kpi.by_status).sort((a, b) => b[1] - a[1])
                  .map(([s, c]) => (
                    <tr key={s}><td><StatusBadge status={s as ContainerStatus} /></td>
                      <td className="num"><b>{c}</b></td></tr>
                  ))}</tbody></table>
              </div>
              <div>
                <h3>{t('anKpiTopSuppliers')}</h3>
                {kpi.top_suppliers.length === 0 ? <p className="muted">{t('anSuppliersEmpty')}</p>
                  : <ul>{kpi.top_suppliers.map((s, i) => <li key={i}>{s.name}: <b>{s.count}</b></li>)}</ul>}
              </div>
              <div>
                <h3>{t('anKpiTopWarehouses')}</h3>
                {kpi.top_warehouses.length === 0 ? <p className="muted">{t('anWarehousesEmpty')}</p>
                  : <ul>{kpi.top_warehouses.map((w, i) => <li key={i}>{w.name}: <b>{w.count}</b></li>)}</ul>}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="panel">
        <h2>{t('anHistorical')}</h2>
        {/* B24: wybór pliku po polsku; plik, wzór i akcje w jednym rzędzie */}
        <div className="file-pick-bar">
          <FilePicker label={t('anFile')} caption={t('anFile')} accept=".csv,.xlsx" file={file}
                      onChange={f => { setFile(f); setReport(null) }} />
          <TemplateButtons kinds={['issues']} />
          <button className="btn small" disabled={!file || busy} onClick={() => doUpload(false)}>
            {busy ? t('sending') : t('anUploadPreview')}
          </button>
          <button className="btn small" disabled={!report || report.errors.length > 0 || busy}
                  onClick={() => doUpload(true)}>
            {t('save')}
          </button>
        </div>
        {uploadError && <p className="error">{uploadError}</p>}
        {report && (
          <div style={{ marginTop: 10 }}>
            <p>{t('anRows')}: {report.rows_count} · {t('anDuplicates')}: {report.duplicates}
              {report.saved && ` · ${t('anSaved')}`}</p>
            {report.errors.length > 0 && (
              <div>
                <b>{t('anErrors')}:</b>
                <ul>{report.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            )}
            {report.unknown_products.length > 0 && (
              <div>
                <b>{t('anUnknownProducts')}:</b>
                <ul>{report.unknown_products.map((p, i) => <li key={i}>{p}</li>)}</ul>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
