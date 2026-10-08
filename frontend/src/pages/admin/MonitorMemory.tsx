// Szczegóły RAM monitora serwera: na co idzie pamięć hosta + procesy, które zjadają najwięcej.
// Lista całego serwera wymaga montażu /proc:/host/proc:ro (docker-compose.coolify.yml);
// bez niego backend zwraca scope='container' i pokazujemy podpowiedź.
import { useT } from '../../i18n'

export type MemBreakdown = {
  apps_mb: number; shared_mb: number; cache_mb: number; kernel_mb: number
  swap_used_mb: number; swap_total_mb: number
}
export type ProcGroup = { name: string; container: string; count: number; private_mb: number; shared_mb: number }
export type Processes = { scope: 'host' | 'container' | null; items: ProcGroup[] }

const mb = (v: number) => (v >= 1024 ? `${(v / 1024).toFixed(1)} GB` : `${v} MB`)

export default function MonitorMemory({ breakdown, processes }: {
  breakdown?: MemBreakdown; processes?: Processes
}) {
  const t = useT()
  if (!breakdown && !processes?.items.length) return null
  return (
    <>
      <h4 style={{ margin: '14px 0 6px' }}>{t('monMemDetails')}</h4>
      {breakdown && (
        <p className="muted" style={{ fontSize: 14, margin: '0 0 6px' }}>
          {t('monMemApps')}: <b>{mb(breakdown.apps_mb)}</b> · {t('monMemShared')}: {mb(breakdown.shared_mb)}
          {' · '}{t('monMemKernel')}: {mb(breakdown.kernel_mb)}
          {' · '}{t('monMemCache')}: {mb(breakdown.cache_mb)}
          {' · '}swap: {breakdown.swap_total_mb ? `${mb(breakdown.swap_used_mb)} / ${mb(breakdown.swap_total_mb)}` : t('monSwapNone')}
        </p>
      )}
      {processes?.scope === 'container' && <p className="muted" style={{ fontSize: 14 }}>{t('monProcScopeHint')}</p>}
      {!!processes?.items.length && (
        <table className="grid" style={{ width: 'auto' }}>
          <thead><tr>
            <th>{t('monProcName')}</th><th>{t('monProcContainer')}</th><th>{t('monProcCount')}</th>
            <th>{t('monProcPrivate')}</th><th>{t('monProcShared')}</th>
          </tr></thead>
          <tbody>{processes.items.map(p => (
            <tr key={`${p.name}|${p.container}`}>
              <td className="mono">{p.name}</td><td className="mono">{p.container || '—'}</td>
              <td className="mono">{p.count}</td><td className="mono">{mb(p.private_mb)}</td>
              <td className="mono">{p.shared_mb ? mb(p.shared_mb) : '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </>
  )
}
