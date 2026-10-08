// Dziennik żądań (admin) — filtry + wykres ruchu 24h + tabela z rozwijanym wierszem
import { Fragment, useEffect, useState } from 'react'
import { api, errorMessage } from '../../../api'
import { useT } from '../../../i18n'
import { formatDateTime, parseServerTs } from '../../../dates'

interface ReqRow {
  id: number; at: string; method: string; path: string; status: number
  duration_ms: number; user_id: number | null; user_login: string | null
  ip: string; request_id: string; error: string | null
}
type ReqResp = { total: number; items: ReqRow[] }
type TrafficPoint = { at: string; total: number; c4xx: number; c5xx: number; avg_ms: number }

const PER_PAGE = 50
const HOURS = 24

const hm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

// Słupki na prawdziwej osi czasu [teraz-HOURS, teraz] — pozycja x z timestampu kubełka,
// nie z indeksu w tablicy; brakujący kubełek (backend nic nie zwrócił) = brak słupka,
// zamiast rozciągać dane na całą szerokość.
function Traffic({ points, title, now: nowLabel }: { points: TrafficPoint[]; title: string; now: string }) {
  if (points.length === 0) return null
  const W = 600, H = 60
  const end = Date.now()
  const start = end - HOURS * 3600_000
  const slots = (HOURS * 60) / 5   // 288 dla 24h
  const barW = Math.max(W / slots - 1, 1)
  const max = Math.max(1, ...points.map(p => p.total))
  return (
    <figure style={{ margin: '0 0 10px' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={title}
           preserveAspectRatio="none" style={{ background: 'var(--soft)', borderRadius: 4 }}>
        {points.map(p => {
          const t = parseServerTs(p.at).getTime()
          const x = Math.min(1, Math.max(0, (t - start) / (end - start))) * W
          const th = (p.total / max) * H
          const eh = (p.c5xx / max) * H
          return (
            <g key={p.at}>
              <rect x={x} y={H - th} width={barW} height={th} fill="var(--accent)" />
              <rect x={x} y={H - eh} width={barW} height={eh} fill="var(--danger)" />
            </g>
          )
        })}
      </svg>
      <div className="log-traffic-axis muted">
        <span>{hm(new Date(start))}</span>
        <span>{hm(new Date((start + end) / 2))}</span>
        <span>{nowLabel}</span>
      </div>
      <figcaption className="muted" style={{ fontSize: 13 }}>{title}</figcaption>
    </figure>
  )
}

const statusClass = (r: ReqRow) =>
  r.status >= 500 ? 'log-5xx' : r.status >= 400 ? 'log-4xx' : r.duration_ms > 1000 ? 'log-slow' : ''

export default function LogsRequests() {
  const t = useT()
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<ReqResp>({ total: 0, items: [] })
  const [traffic, setTraffic] = useState<TrafficPoint[]>([])
  const [error, setError] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    // reset strony do 1 w tym samym callbacku co debouncedQ — nie osobnym efektem,
    // inaczej zmiana filtra odpalała fetch dwa razy (raz ze starą stroną, raz z 1)
    const id = setTimeout(() => { setDebouncedQ(q); setPage(1) }, 300)
    return () => clearTimeout(id)
  }, [q])

  const onFilter = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1) }
  const onStatus = onFilter(setStatus)
  const onFrom = onFilter(setFrom)
  const onTo = onFilter(setTo)

  useEffect(() => {
    let live = true
    const params = new URLSearchParams({ page: String(page), per_page: String(PER_PAGE) })
    if (status) params.set('status', status)
    if (debouncedQ) params.set('q', debouncedQ)
    if (from) params.set('date_from', from)
    if (to) params.set('date_to', to)
    api.get<ReqResp>(`/api/admin/logs/requests?${params}`)
      .then(r => { if (live) { setData(Array.isArray(r?.items) ? r : { total: 0, items: [] }); setError('') } })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [status, debouncedQ, from, to, page, nonce])

  useEffect(() => {
    let live = true
    api.get<TrafficPoint[]>(`/api/admin/logs/traffic?hours=${HOURS}`)
      .then(r => { if (live) setTraffic(Array.isArray(r) ? r : []) })
      .catch(() => { if (live) setTraffic([]) })
    return () => { live = false }
  }, [nonce])

  return (
    <div>
      {error && <p className="error">{error}</p>}
      <div className="log-filters">
        <label>{t('logFilterStatus')}
          <select value={status} onChange={e => onStatus(e.target.value)}>
            <option value="">{t('logStatusAll')}</option>
            <option value="4xx">{t('logStatus4xx')}</option>
            <option value="5xx">{t('logStatus5xx')}</option>
            <option value="slow">{t('logStatusSlow')}</option>
          </select>
        </label>
        <label>{t('logFilterSearch')}
          <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('logSearchPlaceholder')} />
        </label>
        <label>{t('logFilterFrom')}<input type="date" value={from} onChange={e => onFrom(e.target.value)} /></label>
        <label>{t('logFilterTo')}<input type="date" value={to} onChange={e => onTo(e.target.value)} /></label>
        <button type="button" className="btn small secondary" onClick={() => setNonce(n => n + 1)}>
          {t('logRefresh')}
        </button>
      </div>
      <Traffic points={traffic} title={t('logTrafficTitle')} now={t('logTrafficNow')} />
      {data.items.length === 0 ? <p className="muted">{t('logEmpty')}</p> : (
        <table className="grid">
          <thead>
            <tr>
              <th>{t('logColAt')}</th><th>{t('logColMethod')}</th><th>{t('logColPath')}</th>
              <th>{t('logColStatus')}</th><th>{t('logColDuration')}</th>
              <th>{t('logColUser')}</th><th>{t('logColRequestId')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(r => (
              <Fragment key={r.id}>
                <tr className="clickable" onClick={() => setOpenId(openId === r.id ? null : r.id)}>
                  <td className="mono">{formatDateTime(r.at)}</td>
                  <td className="mono">{r.method}</td>
                  <td className="mono">{r.path}</td>
                  <td className={statusClass(r)}>{statusClass(r) === 'log-slow' && '⏱ '}{r.status}</td>
                  <td className="mono">{r.duration_ms}</td>
                  <td>{r.user_login ?? '—'}</td>
                  <td className="mono">{r.request_id}</td>
                </tr>
                {openId === r.id && (
                  <tr>
                    <td colSpan={7}><pre>{r.error || t('logNoDetails')}</pre></td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
      <div className="log-pager">
        <button type="button" className="btn small secondary" disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}>{t('logPrev')}</button>
        <button type="button" className="btn small secondary" disabled={page * PER_PAGE >= data.total}
                onClick={() => setPage(p => p + 1)}>{t('logNext')}</button>
      </div>
    </div>
  )
}
