// Monitor wydajności i pojemności serwera (admin, 2026-09-24) — /api/admin/monitor,
// odświeżany co 15 s. Host = cały serwer (/proc), kontener = limit Dockera aplikacji.
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { formatNum } from '../../dates'
import MonitorMemory, { type MemBreakdown, type Processes } from './MonitorMemory'

type Disk = { label: string; path: string; total_gb: number; used_gb: number; free_gb: number; percent: number | null }
type Sample = { at: string; cpu: number | null; mem: number | null; rss_mb: number | null }
export type Monitor = {
  cpu_percent: number | null; cpu_count: number | null; load_avg: number[] | null
  memory: { total_mb: number; used_mb: number; percent: number | null; breakdown?: MemBreakdown } | null
  container_memory: { used_mb: number; limit_mb: number | null } | null
  process_rss_mb: number | null; threads: number; disks: Disk[]; history: Sample[]
  processes?: Processes
  database: { engine: string; size_mb?: number; connections?: number | null; error?: string
    tables?: { name: string; size_mb: number; rows: number }[] }
}

const REFRESH_MS = 15_000
// progi: zielony < 70%, bursztyn < 90%, czerwony
const tone = (p: number | null | undefined) =>
  p == null ? 'var(--muted)' : p < 70 ? 'var(--good)' : p < 90 ? '#b7791f' : 'var(--danger)'

function Meter({ label, pct, detail }: { label: string; pct: number | null | undefined; detail: string }) {
  return (
    <div className="mon-meter">
      <div className="mon-head"><span>{label}</span><b style={{ color: tone(pct) }}>{pct == null ? '—' : `${pct}%`}</b></div>
      <div className="mon-bar" role="meter" aria-label={label} aria-valuenow={pct ?? undefined}
           aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${Math.min(pct ?? 0, 100)}%`, background: tone(pct) }} />
      </div>
      <small className="muted">{detail}</small>
    </div>
  )
}

// wykres 24 h: CPU i RAM serwera jako dwie linie 0–100%
function History({ samples, label }: { samples: Sample[]; label: string }) {
  const t = useT()
  if (samples.length < 2) return <p className="muted">{t('monNoHistory')}</p>
  const W = 600, H = 80
  const line = (key: 'cpu' | 'mem') => samples.map((s, i) =>
    `${(i / (samples.length - 1)) * W},${H - ((s[key] ?? 0) / 100) * H}`).join(' ')
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={label}
           preserveAspectRatio="none" style={{ background: 'var(--soft)', borderRadius: 4 }}>
        <polyline points={line('mem')} fill="none" stroke="#6b8fd6" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <polyline points={line('cpu')} fill="none" stroke="var(--accent)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption className="muted" style={{ fontSize: 13 }}>
        {label}: <span style={{ color: 'var(--accent)' }}>■</span> CPU · <span style={{ color: '#6b8fd6' }}>■</span> RAM
        · {samples.length} {t('monSamples')}
      </figcaption>
    </figure>
  )
}

export default function MonitorPanel() {
  const t = useT()
  const [m, setM] = useState<Monitor | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    const load = () => api.get<Monitor>('/api/admin/monitor')
      .then(r => { if (alive && Array.isArray(r?.disks)) { setM(r); setError('') } })   // pusta/obca odpowiedź = brak danych, nie crash
      .catch(err => { if (alive) setError(errorMessage(err)) })
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])
  const mb = (v: number) => (v >= 1024 ? `${(v / 1024).toFixed(1)} GB` : `${v} MB`)
  const cm = m?.container_memory
  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <h3>{t('monTitle')} <small className="muted" style={{ fontWeight: 400 }}>· {t('monAuto')}</small></h3>
      {error && <p className="error">{error}</p>}
      {m && (
        <>
          <div className="mon-grid">
            <Meter label={t('monCpu')} pct={m.cpu_percent}
                   detail={`${m.cpu_count ?? '?'} ${t('monCores')}${m.load_avg ? ` · load ${m.load_avg.join(' / ')}` : ''}`} />
            <Meter label={t('monMemHost')} pct={m.memory?.percent}
                   detail={m.memory ? `${mb(m.memory.used_mb)} / ${mb(m.memory.total_mb)}` : '—'} />
            <Meter label={t('monMemContainer')}
                   pct={cm?.limit_mb ? Math.round(1000 * cm.used_mb / cm.limit_mb) / 10 : null}
                   detail={cm ? `${mb(cm.used_mb)}${cm.limit_mb ? ` / ${mb(cm.limit_mb)}` : ` · ${t('monNoLimit')}`}` : '—'} />
            {m.disks.map(d => (
              <Meter key={d.path} label={`${t('monDisk')}: ${d.label}`} pct={d.percent}
                     detail={`${d.used_gb} / ${d.total_gb} GB · ${t('monFree')} ${d.free_gb} GB`} />
            ))}
          </div>
          <p className="muted" style={{ fontSize: 14 }}>
            {t('monProcess')}: {m.process_rss_mb != null ? mb(m.process_rss_mb) : '—'} · {m.threads} {t('monThreads')}
          </p>
          <History samples={m.history} label={t('monHistory')} />
          <MonitorMemory breakdown={m.memory?.breakdown} processes={m.processes} />
          <h4 style={{ margin: '14px 0 6px' }}>
            {t('monDb')} ({m.database.engine}): {m.database.size_mb != null ? mb(m.database.size_mb) : '—'}
            {m.database.connections != null && <> · {m.database.connections} {t('monConnections')}</>}
          </h4>
          {m.database.error && <p className="error">{m.database.error}</p>}
          {!!m.database.tables?.length && (
            <table className="grid" style={{ width: 'auto' }}>
              <thead><tr><th>{t('monTable')}</th><th>MB</th><th>{t('monRows')}</th></tr></thead>
              <tbody>{m.database.tables.map(tb => (
                <tr key={tb.name}><td className="mono">{tb.name}</td><td className="mono">{tb.size_mb}</td>
                  <td className="mono">{formatNum(tb.rows)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
