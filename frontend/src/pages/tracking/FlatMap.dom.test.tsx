// @vitest-environment jsdom
// Strażnik (2026-09-24): płaska mapa ma tło ze zdjęcia satelitarnego (to samo co globus),
// a przy błędzie wczytania wraca do wektorowego lądu z kreską wybrzeża. Od 2026-10-01 zdjęcie to
// opcjonalna warstwa — domyślnie mapa terenu (wektor + cieniowana rzeźba).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, renderHook } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))

import FlatMap from './FlatMap'
import { useMapLayers } from './MapLayers'
import { useMapView } from './useMapView'
import { EARTH_PHOTO_URL } from './earthPhoto'

afterEach(cleanup)

function mount(satellite = true) {
  const mv = renderHook(() => useMapView()).result.current
  const layers = { ...renderHook(() => useMapLayers()).result.current, showSatellite: satellite }
  return render(<FlatMap mv={mv} layers={layers} grouped={new Map()} vessels={[]} weather={{}}
    active={null} setActive={() => {}} pinned={false} setPinned={() => {}}
    activeVessel={null} setActiveVessel={() => {}} replayOpen={false} replayIndex={0}
    portCounts={new Map()} containerPorts={[]} factories={[]} onFactoryClick={() => {}} />)
}

describe('FlatMap — tło', () => {
  it('domyślnie mapa terenu: rzeźba w trybie hard-light, bez zdjęcia NASA', () => {
    const { container } = mount(false)
    const hrefs = [...container.querySelectorAll('image')].map(i => i.getAttribute('href'))
    expect(hrefs).not.toContain(EARTH_PHOTO_URL)
    expect(hrefs.some(h => h?.endsWith('globe/relief/relief-4k.webp'))).toBe(true)
    expect(container.querySelector('svg.world-map.is-vector')).toBeTruthy()
  })

  it('zdjęcie satelitarne na całym świecie 1000x500, bez wektorowej kreski wybrzeża', () => {
    const { container } = mount()
    const img = container.querySelector('image')!
    expect(img.getAttribute('href')).toBe(EARTH_PHOTO_URL)
    expect([img.getAttribute('width'), img.getAttribute('height')]).toEqual(['1000', '500'])
    expect(container.querySelector('path[stroke="rgba(226, 240, 255, 0.55)"]')).toBeNull()
  })

  it('błąd wczytania zdjęcia → fallback wektorowy z wybrzeżem', () => {
    const { container } = mount()
    fireEvent.error(container.querySelector('image')!)
    expect(container.querySelector('image')).toBeNull()
    expect(container.querySelector('path[stroke="rgba(226, 240, 255, 0.55)"]')).toBeTruthy()
  })
})
