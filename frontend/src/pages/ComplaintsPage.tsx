import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import type { Complaint, ComplaintStatus } from '../types'
import { COMPLAINT_STATUS_BADGE } from './ComplaintsPanel'
import { CameraIcon, ChartColumnIcon, MessageSquareWarning } from 'lucide-react'
import { EmptyState, LoadError, Skeleton } from '../feedback'
import { PageHeader } from '../PageHeader'

const STATUSES: ComplaintStatus[] = ['SZKIC', 'NOWA', 'ZGLOSZONA', 'WYSLANA', 'ODPOWIEDZ', 'ZAMKNIETA']

// /reklamacje i /reklamacje/archiwum renderują ten sam element — osobny key per widok
// wymusza remount, więc zakładka, lista i loading nie przeciekają między widokami
export default function ComplaintsPage({ archive = false }: { archive?: boolean }) {
  return <ComplaintsList key={archive ? 'archive' : 'active'} archive={archive} />
}

function ComplaintsList({ archive }: { archive: boolean }) {
  const t = useT()
  const navigate = useNavigate()
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [tab, setTab] = useState<'' | ComplaintStatus>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // numer żądania odrzuca spóźnioną odpowiedź (np. powtórny load() z LoadError onRetry)
  const seq = useRef(0)
  const load = useCallback(() => {
    const my = ++seq.current
    setLoading(true)
    setError('')
    api.get<Complaint[]>(`/api/complaints?archived=${archive}`)
      .then(rows => { if (my === seq.current) setComplaints(rows) })
      .catch(err => {   // błąd API nie maskuje się jako pusta lista bez sygnału
        if (my === seq.current) { setComplaints([]); setError(errorMessage(err)) }
      })
      .finally(() => { if (my === seq.current) setLoading(false) })
  }, [archive])
  useEffect(() => load(), [load])

  const counts = useMemo(() => {
    const map: Partial<Record<ComplaintStatus, number>> = {}
    for (const c of complaints) map[c.status] = (map[c.status] ?? 0) + 1
    return map
  }, [complaints])

  const visible = tab ? complaints.filter(c => c.status === tab) : complaints

  return (
    <main className="page">
      <PageHeader title={archive ? t('complaintsArchive') : t('complaints')} actions={!archive && (
        <button className="btn small secondary" onClick={() => navigate('/reklamacje/statystyki')}>
          <ChartColumnIcon size={14} /> {t('complaintStats')}
        </button>
      )} />
      {!archive && (
        <div className="tabs">
          <button className={tab === '' ? 'active' : ''} onClick={() => setTab('')}>
            {t('allOrders')}{error ? '' : ` (${complaints.length})`}
          </button>
          {STATUSES.filter(s => s !== 'ZAMKNIETA').map(s => (
            <button key={s} className={tab === s ? 'active' : ''} onClick={() => setTab(s)}>
              {t(`cst_${s}`)}{error ? '' : ` (${counts[s] ?? 0})`}
            </button>
          ))}
        </div>
      )}
      {loading && complaints.length === 0 && <Skeleton rows={4} />}
      {!loading && error && complaints.length === 0 && <LoadError message={error} onRetry={load} />}
      {!loading && !error && visible.length === 0 && (
        <EmptyState icon={MessageSquareWarning} title={t('complaintsEmptyTitle')} hint={t('complaintsEmptyHint')} />
      )}
      {visible.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('complaintNo')}</th><th>{t('containerNo')}</th>
                <th>{t('status')}</th><th>{t('complaintProblems')}</th>
                <th><CameraIcon size={14} /></th><th>{t('complaintAge')}</th><th>{t('createdBy')}</th><th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map(c => (
                <tr key={c.id} className="clickable" style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/reklamacje/${c.id}`)}>
                  <td className="mono strong">{c.number}</td>
                  <td className="mono">{c.container_no}</td>
                  <td><span className={`badge ${COMPLAINT_STATUS_BADGE[c.status]}`}>
                    {t(`cst_${c.status}`)}</span></td>
                  <td>{c.problems.join(', ') || '—'}</td>
                  <td>{c.photo_count || ''}</td>
                  <td className={c.status === 'WYSLANA' && c.age_days >= 15 ? 'over-limit' : ''}>
                    {c.age_days} {t('complaintDays')}
                  </td>
                  <td className="muted">{c.created_by_login}</td>
                  <td><button className="btn small secondary">{t('details')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
