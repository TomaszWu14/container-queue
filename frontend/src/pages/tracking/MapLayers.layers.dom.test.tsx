// @vitest-environment jsdom
// Panel WIDOK/WARSTWY na mapie (audyt UI B9 — UX-033): zwijany jak legenda. Na wąskim ekranie
// (< 768 px) domyślnie zwinięty do nagłówka „Warstwy” — wcześniej zajmował ~2/3 globusa.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { MapLayersPanel, useMapLayers } from './MapLayers'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function mount(wide: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('min-width') ? wide : !wide,
    media: q, addEventListener: () => {}, removeEventListener: () => {} }))
  const { result } = renderHook(() => useMapLayers())
  render(<MapLayersPanel layers={result.current} mapMode="3d" setViewPreset={() => {}} />)
  return document.querySelector('details.map-layers') as HTMLDetailsElement
}

describe('panel warstw mapy', () => {
  it('telefon (< 768 px): zwinięty, nagłówek „Warstwy” w summary', () => {
    const panel = mount(false)
    expect(panel).not.toBeNull()
    expect(panel.open).toBe(false)
    expect(panel.querySelector('summary')?.textContent).toBe('Warstwy')
  })

  it('szeroki ekran: rozwinięty, widoki i warstwy dostępne', () => {
    const panel = mount(true)
    expect(panel.open).toBe(true)
    expect(screen.getByRole('button', { name: 'Europa' })).toBeTruthy()
  })
})
