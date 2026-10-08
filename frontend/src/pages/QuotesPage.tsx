import { InboxIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useUser } from '../App'
import { api, downloadFile, errorMessage } from '../api'
import { useT } from '../i18n'
import type { TransportJob } from '../types'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { PageHeader } from '../PageHeader'
import { JOB_CLASS, type CostRow, type PerfRow } from './quotes/shared'
import JobDetail from './quotes/JobDetail'
import { CostReport, PerfReport } from './quotes/Reports'

// Cienki kontener: lista zleceń wyceny + przełącznik widoków (szczegóły / raporty).
// Logika paneli mieszka w pages/quotes/*.
export default function QuotesPage() {
  const t = useT()
  const { showToast } = useToast()
  const user = useUser()
  const isForwarder = user?.role === 'forwarder'
  const canManage = user?.role === 'admin' || user?.role === 'logistics'
  const [jobs, setJobs] = useState<TransportJob[]>([])
  const [sel, setSel] = useState<TransportJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cost, setCost] = useState<CostRow[] | null>(null)
  const [perf, setPerf] = useState<PerfRow[] | null>(null)
  const [busy, setBusy] = useState(false)

  const exportCsv = async () => {
    try {
      await downloadFile('/api/stats/transport-jobs.csv', 'zlecenia-wyceny.csv')
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const toggleCost = () => cost
    ? setCost(null)
    : (setPerf(null), api.get<CostRow[]>('/api/stats/cost-report').then(setCost).catch(() => setCost([])))
  const togglePerf = () => perf
    ? setPerf(null)
    : (setCost(null), api.get<PerfRow[]>('/api/stats/forwarders').then(setPerf).catch(() => setPerf([])))

  const load = useCallback((keepId?: number) => {
    setLoading(true)
    setError('')
    api.get<TransportJob[]>('/api/transport-jobs')
      .then(data => {
        setJobs(data)
        setSel(prev => {
          const id = keepId ?? prev?.id
          return data.find(j => j.id === id) ?? data[0] ?? null
        })
      })
      .catch(err => { setJobs([]); setError(errorMessage(err)) })
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const act = async (fn: () => Promise<TransportJob>) => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      const updated = await fn()
      setJobs(list => list.map(j => (j.id === updated.id ? updated : j)))
      setSel(updated)
      showToast(t('toastSaved'))
    } catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }

  // B15/C12: tytuł strony z akcjami eksportu po prawej (wcześniej upchnięte w wąskim panelu listy)
  const header = <PageHeader title={t('navQuotes')} actions={canManage ? <>
    <button className="btn small secondary" onClick={exportCsv}>{t('quoteExport')}</button>
    <button className={`btn small${cost ? '' : ' secondary'}`} onClick={toggleCost}>{t('quoteCostReport')}</button>
    <button className={`btn small${perf ? '' : ' secondary'}`} onClick={togglePerf}>{t('perfReport')}</button>
  </> : undefined} />
  if (loading && jobs.length === 0) return <main className="page">{header}<Skeleton rows={4} /></main>
  if (!loading && error && jobs.length === 0) {
    return <main className="page">{header}<LoadError message={error} onRetry={() => load()} /></main>
  }
  const report = cost ? <CostReport rows={cost} onClose={() => setCost(null)} />
    : perf ? <PerfReport rows={perf} onClose={() => setPerf(null)} /> : null

  // pusta lista: bez panelu szczegółów („Wybierz zlecenie z listy.” przy pustej liście mylił);
  // spedytor dostaje tekst dla siebie — instrukcja „utwórz zlecenie” jest dla logistyki
  if (jobs.length === 0) {
    return (
      <main className="page">
        {header}
        {report ?? <EmptyState icon={InboxIcon}
          title={t(isForwarder ? 'quoteNoneForwarder' : 'quoteNone')}
          hint={t(isForwarder ? 'quoteNoneForwarderHint' : 'quoteNoneHint')} />}
      </main>
    )
  }

  return (
    <main className="page">
      {header}
      <div className="quotes-page">
        <div className="quotes-list panel p0">
          <div className="quotes-list-head">{t('navQuotes')} ({jobs.length})</div>
          {jobs.map(j => (
            <button key={j.id} className={`quote-item${sel?.id === j.id ? ' active' : ''}`}
                    onClick={() => { setSel(j); setCost(null); setPerf(null) }}>
              <div className="row row-between">
                <b className="mono">{j.number}</b>
                <span className={`badge ${JOB_CLASS[j.status]}`}>{t(`job_${j.status}`)}</span>
              </div>
              <div className="muted txt-sm">
                {j.container_count} {t('contAbbrev')}
                {j.pickup_location && ` · ${j.pickup_location} → ${j.delivery_location || '—'}`}
              </div>
            </button>
          ))}
        </div>

        <div className="quotes-detail">
          {report ?? (!sel ? <p className="muted">{t('quotePickJob')}</p> : (
            <JobDetail key={sel.id} job={sel} isForwarder={isForwarder} canManage={canManage}
                       onAction={act} error={error} busy={busy} />
          ))}
        </div>
      </div>
    </main>
  )
}
