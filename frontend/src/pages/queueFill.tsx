// Kolumna „Wypełnienie" kolejki: batchowe pobieranie % z /api/containers/fill-summary
// (jedno żądanie na paczkę widocznych kontenerów zamiast N × /packing) + pasek %.
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useT } from '../i18n'

const CHUNK = 40   // limit paczki po stronie API

/** Mapa id → % wypełnienia (null = brak danych MARM/typu). Pyta TYLKO o id, których
    jeszcze nie zna (widoczne kontenery), porcjami po 40, sekwencyjnie. */
export function useFillSummary(ids: number[], enabled: boolean): Record<number, number | null> {
  const [map, setMap] = useState<Record<number, number | null>>({})
  const known = useRef<Set<number>>(new Set())
  const key = ids.join(',')
  useEffect(() => {
    if (!enabled) return
    const missing = ids.filter(id => !known.current.has(id))
    if (missing.length === 0) return
    // ponytail: null z budżetu czasu backendu zostaje null do przeładowania strony —
    // retry per id dopiero, gdyby braki realnie przeszkadzały
    // oznaczamy od razu (w locie = nie dubluj żądań), a przy anulowaniu zwalniamy
    // wszystko, czego wynik nie trafił do mapy — inaczej te id nie byłyby już nigdy pobrane
    missing.forEach(id => known.current.add(id))
    let cancelled = false
    let done = 0   // ile id z `missing` ma już zapisany wynik
    ;(async () => {
      for (let i = 0; i < missing.length; i += CHUNK) {
        const chunk = missing.slice(i, i + CHUNK)
        try {
          const part = await api.get<Record<string, number | null>>(
            `/api/containers/fill-summary?ids=${chunk.join(',')}`)
          if (cancelled) return
          setMap(prev => ({
            ...prev,
            ...Object.fromEntries(chunk.map(id => [id, part[String(id)] ?? null])),
          }))
        } catch {
          // kolumna % nie może wywalić kolejki — brak danych = kreska
          if (cancelled) return
        }
        done = i + chunk.length
      }
    })()
    return () => {
      cancelled = true
      missing.slice(done).forEach(id => known.current.delete(id))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])
  return map
}

/** Pasek % wypełnienia kontenera; null/undefined → kreska. >100% = przepełnienie. */
export function FillBar({ pct }: { pct: number | null | undefined }) {
  const t = useT()
  if (pct == null) return <span className="muted">—</span>
  const color = pct > 100 ? '#c0392b' : pct >= 85 ? '#2f7d54' : '#0b5fff'
  return (
    <span className="fill-bar" title={`${t('fillCol')}: ${pct}%`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span aria-hidden="true" style={{
        width: 46, height: 7, borderRadius: 4, background: 'var(--line, #d7dfeb)',
        overflow: 'hidden', display: 'inline-block' }}>
        <i style={{ display: 'block', height: '100%', width: `${Math.min(pct, 100)}%`,
                    background: color }} />
      </span>
      <small className="mono">{Math.round(pct)}%</small>
    </span>
  )
}
