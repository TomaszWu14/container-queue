import { useCallback, useEffect, useRef, useState } from 'react'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { px as projLon, py as projLat } from './mapStatic'

// Zoom/pan płaskiej mapy przez viewBox: {x, y, w}; h wynika z proporcji świata.
// Wydzielone z TrackingPage — ten sam stan i te same efekty (RO + natywny wheel).
export function useMapView() {
  const [view, setView] = useState({ x: 0, y: 0, w: WORLD_W })
  const svgRef = useRef<SVGSVGElement | null>(null)
  // element SVG jako stan (callback ref): mapa bywa montowana później niż hook (pusta lista
  // kontenerów → „Pokaż mapę”) — efekty z [] podpinały wtedy wheel/RO do null i kółko nie działało
  const [svgEl, setSvgEl] = useState<SVGSVGElement | null>(null)
  const attachSvg = useCallback((el: SVGSVGElement | null) => { svgRef.current = el; setSvgEl(el) }, [])
  // realna szerokość SVG w px — mapa jest responsywna, więc „16 px ekranu" nie da się
  // przeliczyć na jednostki świata bez pomiaru (WORLD_W to szerokość viewBoxa, nie elementu)
  const [svgW, setSvgW] = useState(0)
  useEffect(() => {
    const svg = svgEl
    if (!svg || typeof ResizeObserver === 'undefined') return   // jsdom nie ma RO → fallback WORLD_W
    const ro = new ResizeObserver(([entry]) => setSvgW(entry.contentRect.width))
    ro.observe(svg)
    return () => ro.disconnect()
  }, [svgEl])
  const viewH = view.w * (WORLD_H / WORLD_W)

  // wheel przez natywny listener {passive:false} — React rejestruje onWheel pasywnie,
  // więc preventDefault w syntetycznym handlerze nie działa i strona przewija się
  // podczas zoomowania mapy
  useEffect(() => {
    const svg = svgEl
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 1.25 : 0.8)
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
    // zoomAt jest stabilne w praktyce (korzysta z setState-updaterów) — jeden listener na element
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svgEl])

  const zoomAt = (clientX: number, clientY: number, factor: number) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    if (!rect.width || !rect.height) return   // zminimalizowane/ukryte okno → NaN w viewBox
    setView(v => {
      const h = v.w * (WORLD_H / WORLD_W)
      // punkt mapy pod kursorem zostaje pod kursorem po zoomie
      const mx = v.x + ((clientX - rect.left) / rect.width) * v.w
      const my = v.y + ((clientY - rect.top) / rect.height) * h
      // do ×64: z bliska mapa wektorowa (vectorMap.ts) jest ostra przy każdym zoomie
      const w = Math.min(WORLD_W, Math.max(WORLD_W / 64, v.w * factor))
      const nh = w * (WORLD_H / WORLD_W)
      return {
        x: Math.min(Math.max(0, mx - ((mx - v.x) / v.w) * w), WORLD_W - w),
        y: Math.min(Math.max(0, my - ((my - v.y) / h) * nh), WORLD_H - nh),
        w,
      }
    })
  }

  // zoom na środek widocznej mapy (przyciski +/− i klik w klaster wielu lokalizacji)
  const zoomCenter = (factor: number) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (r) zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor)
  }

  const zoomToPort = (lat: number, lon: number) => {
    const w = WORLD_W / 6
    const h = w * (WORLD_H / WORLD_W)
    setView({
      x: Math.min(Math.max(0, projLon(lon) - w / 2), WORLD_W - w),
      y: Math.min(Math.max(0, projLat(lat) - h / 2), WORLD_H - h),
      w,
    })
  }

  return { view, setView, viewH, svgRef, attachSvg, svgW, zoomAt, zoomCenter, zoomToPort }
}

export type MapView = ReturnType<typeof useMapView>
