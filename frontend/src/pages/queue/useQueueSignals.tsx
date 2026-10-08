import { TriangleAlertIcon } from 'lucide-react'
// Warstwy sygnałów kolejki doczytywane obok listy: bufor ETA magazynu, dzienne limity
// magazynów → „Pilność", kolizje transportowe. Żadna nie może wywalić kolejki.
// Wyniesione z QueuePage.tsx.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { useT } from '../../i18n'
import type { Container, Warehouse } from '../../types'
import type { DayRow } from '../queueRows'


// Pilność rozładunku (makieta hybryda A+E): narastające obłożenie dnia per magazyn
// względem dziennego limitu magazynu — default_daily_limit ze słownika, nadpisany
// wyjątkami per-datę z /api/limits (te same dane, którymi steruje moduł limitów).
export function useUrgency({ rows, warehouses, warehouseKeys }: {
  rows: DayRow[]
  warehouses: Warehouse[]
  warehouseKeys: string[]
}) {
  const whLimits = useMemo(() => Object.fromEntries(
    warehouses.map(w => [w.name, w.default_daily_limit])), [warehouses])
  const [limitOverrides, setLimitOverrides] = useState<Record<string, number>>({})
  // zakres dni z aktualnych wierszy — działa też w trybie „Wszystko" (bez dat w query)
  const daysSpan = useMemo(() => {
    const days = rows.map(r => r.day).filter(Boolean).sort()
    return days.length ? `${days[0]}..${days[days.length - 1]}` : ''
  }, [rows])
  useEffect(() => {
    const [from, to] = daysSpan.split('..')
    const whs = warehouses.filter(w => warehouseKeys.includes(w.name))
    if (!from || whs.length === 0) { setLimitOverrides({}); return }
    let cancelled = false
    Promise.all(whs.map(w =>
      api.get<{ day: string; limit: number }[]>(
        `/api/limits?warehouse_id=${w.id}&date_from=${from}&date_to=${to}`)
        .then(list => (Array.isArray(list) ? list : []).map(l =>
          [`${w.name}|${l.day}`, l.limit] as const)
        )
        // warstwa limitów nie może wywalić kolejki — brak nadpisań = domyślny limit
        .catch(() => [] as (readonly [string, number])[])))
      .then(parts => { if (!cancelled) setLimitOverrides(Object.fromEntries(parts.flat())) })
    return () => { cancelled = true }
  }, [daysSpan, warehouses, warehouseKeys])
  const limitFor = useCallback((wh: string, day: string | null) =>
    (day ? limitOverrides[`${wh}|${day}`] : undefined) ?? whLimits[wh] ?? null,
  [limitOverrides, whLimits])
  return { limitFor }
}

// Kolizje transportowe (paczka TransportJob → różne magazyny tego samego dnia):
// jedno zapytanie na widok, mapa id → nazwy magazynów (ikona ⚠ w wierszu)
export function useTransportConflicts({ enabled, queryFrom, queryTo, module, containers }: {
  enabled: boolean
  queryFrom: string
  queryTo: string
  module: string
  containers: Container[]
}) {
  const t = useT()
  const [tConflicts, setTConflicts] = useState<Map<number, string[]>>(new Map())
  useEffect(() => {
    if (!enabled) return
    const params = new URLSearchParams()
    if (queryFrom) params.set('date_from', queryFrom)
    if (queryTo) params.set('date_to', queryTo)
    api.get<{ conflicts: { container_id: number; warehouses: string[] }[] }>(
      `/api/containers/transport-conflicts?${params}`)
      .then(d => setTConflicts(new Map(d.conflicts.map(x => [x.container_id, x.warehouses]))))
      .catch(() => {})   // warstwa ostrzeżeń nie może wywalić kolejki
    // module w zależnościach: przełączenie zakładki odświeża warstwę (jak przed wydzieleniem)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, module, queryFrom, queryTo, containers])
  return (c: Container) => tConflicts.has(c.id) && (
    <span className="conflict-warn" role="img" aria-label={t('transportConflictWarn')}
          style={{ color: '#c0392b', cursor: 'help' }}
          title={`${t('transportConflictWarn')}: ${tConflicts.get(c.id)!.join(' / ')}`}><TriangleAlertIcon size={14} /></span>
  )
}
