import { useEffect, useState } from 'react'
import { api } from '../../api'

/** Czy JA obserwuję kontener i z jakim powodem — jak gwiazdka w kolejce (GET /watch + /watch/reasons).
    undefined = nie obserwuję (albo odpowiedź innego kształtu); '' = gwiazdka bez powodu. */
export function useWatchReason(containerId: number): string | undefined {
  const [reason, setReason] = useState<string | undefined>(undefined)
  useEffect(() => {
    let cancelled = false
    setReason(undefined)
    Promise.all([api.get<unknown>('/api/watch'), api.get<unknown>('/api/watch/reasons').catch(() => [])])
      .then(([ids, rows]) => {
        if (cancelled || !Array.isArray(ids) || !ids.includes(containerId)) return
        const row = Array.isArray(rows)
          ? (rows as { container_id?: unknown; reason?: unknown }[]).find(r => r?.container_id === containerId)
          : undefined
        setReason(typeof row?.reason === 'string' ? row.reason : '')
      }).catch(() => {})
    return () => { cancelled = true }
  }, [containerId])
  return reason
}
