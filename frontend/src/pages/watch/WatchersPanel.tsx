import { StarIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import { formatDateTime } from '../../dates'
import { useT } from '../../i18n'
import UserAvatar from './UserAvatar'
import WatchReasonDialog from './WatchReasonDialog'

export interface WatchersResponse {
  watching: boolean
  watchers: { user_id: number; name: string; reason: string; created_at: string | null; has_avatar: boolean }[]
}

/** „Śledzone przez…" + gwiazdka dla kontenera/statku. baseUrl: /api/containers/5 | /api/tracking/vessels/3 */
export default function WatchersPanel({ baseUrl, framed = true }: { baseUrl: string; framed?: boolean }) {
  const t = useT()
  const [data, setData] = useState<WatchersResponse | null>(null)
  const [asking, setAsking] = useState(false)
  const load = useCallback(() => {
    let cancelled = false
    setData(null)
    api.get<WatchersResponse>(`${baseUrl}/watchers`)
      // odpowiedź innego kształtu (np. ogólny mock api w testach stron) = brak panelu, nie wyjątek
      .then(res => { if (!cancelled) setData(Array.isArray(res?.watchers) ? res : null) })
      .catch(() => { if (!cancelled) setData(null) })
    return () => { cancelled = true }
  }, [baseUrl])
  useEffect(load, [load])

  const toggle = (body: { reason?: string }) =>
    api.post<{ watching: boolean }>(`${baseUrl}/watch`, body).then(load).catch(() => {})

  if (!data) return null
  return (
    <div className={framed ? 'panel watchers-panel' : 'watchers-panel'}>
      <div className="watchers-head">
        <h3>{t('watchedBy')}</h3>
        <button type="button" className={`btn small${data.watching ? '' : ' secondary'}`}
                onClick={() => data.watching ? toggle({}) : setAsking(true)}>
          <StarIcon size={14} fill={data.watching ? 'currentColor' : 'none'} /> {data.watching ? t('watchRemove') : t('watchAdd')}
        </button>
      </div>
      {data.watchers.length === 0
        ? <p className="muted">{t('watchedByNobody')}</p>
        : (
          <ul className="watchers-list">
            {data.watchers.map(w => (
              <li key={w.user_id}>
                <UserAvatar userId={w.user_id} name={w.name} hasAvatar={w.has_avatar} />
                <span className="watcher-name">{w.name}</span>
                <span className="muted">{w.created_at ? formatDateTime(w.created_at) : '—'}</span>
                {w.reason && <span className="watcher-reason">{w.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      {asking && (
        <WatchReasonDialog onClose={() => setAsking(false)}
                           onConfirm={reason => { setAsking(false); toggle({ reason }) }} />
      )}
    </div>
  )
}
