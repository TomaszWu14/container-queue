// Dziennik zadań tła (admin) — kafelki najnowszego przebiegu + historia z rozwijanym detalem
import { Fragment, useContext, useEffect, useState } from 'react'
import { api, errorMessage } from '../../../api'
import { LangContext, useT } from '../../../i18n'
import { formatDateTime, relTime } from '../../../dates'

interface JobRow { job: string; fn: string; started_at: string; duration_ms: number; ok: boolean; detail: string | null }
type JobsResp = { latest: JobRow[]; history: JobRow[] }

export default function LogsJobs() {
  const t = useT()
  const { lang } = useContext(LangContext)
  const [data, setData] = useState<JobsResp>({ latest: [], history: [] })
  const [error, setError] = useState('')
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let live = true
    api.get<JobsResp>('/api/admin/logs/jobs')
      .then(r => {
        if (!live) return
        setData(Array.isArray(r?.latest) && Array.isArray(r?.history) ? r : { latest: [], history: [] })
        setError('')
      })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [nonce])

  return (
    <div>
      {error && <p className="error">{error}</p>}
      <div className="log-toolbar">
        <button type="button" className="btn small secondary" onClick={() => setNonce(n => n + 1)}>
          {t('logRefresh')}
        </button>
      </div>
      {data.latest.length === 0 ? <p className="muted">{t('logEmpty')}</p> : (
        <div className="log-tile-grid">
          {data.latest.map(j => (
            <div key={`${j.job}/${j.fn}`} className={`log-tile ${j.ok ? 'log-tile-ok' : 'log-tile-err'}`}>
              <span className="mono log-tile-name" title={`${j.job}/${j.fn}`}>{j.job}/{j.fn}</span>
              <div className="log-tile-meta">
                <small className="muted">{relTime(j.started_at, lang)} · {j.duration_ms} ms</small>
                <b>{j.ok ? t('logJobOk') : t('logJobError')}</b>
              </div>
            </div>
          ))}
        </div>
      )}
      {data.history.length > 0 && (
        <table className="grid" style={{ marginTop: 10 }}>
          <thead>
            <tr><th>{t('logColJob')}</th><th>{t('logColStarted')}</th><th>{t('logColStatus')}</th><th>{t('logColDuration')}</th></tr>
          </thead>
          <tbody>
            {data.history.map((j, i) => (
              <Fragment key={i}>
                <tr className={`clickable${j.ok ? '' : ' log-5xx'}`}
                    onClick={() => setOpenIdx(openIdx === i ? null : i)}>
                  <td className="mono">{j.job}/{j.fn}</td>
                  <td className="mono">{formatDateTime(j.started_at)}</td>
                  <td>{j.ok ? t('logJobOk') : t('logJobError')}</td>
                  <td className="mono">{j.duration_ms}</td>
                </tr>
                {openIdx === i && (
                  <tr><td colSpan={4}><pre>{j.detail || t('logNoDetails')}</pre></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
