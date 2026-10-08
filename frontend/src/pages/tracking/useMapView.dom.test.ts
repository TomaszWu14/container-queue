// @vitest-environment jsdom
// Strażnik: kółko myszy zoomuje mapę 2D także, gdy SVG montuje się po hooku
// (pusta lista kontenerów → „Pokaż mapę”) — wcześniej listener wisiał na null.
import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { WORLD_W } from '../../worldmap'
import { useMapView } from './useMapView'

it('wheel na SVG podpiętym później niż hook przybliża widok (limit ×64)', () => {
  const { result } = renderHook(() => useMapView())
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500 } as DOMRect)
  act(() => result.current.attachSvg(svg))
  act(() => { svg.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, clientX: 500, clientY: 250, cancelable: true })) })
  expect(result.current.view.w).toBeCloseTo(WORLD_W * 0.8)
  for (let i = 0; i < 40; i++) act(() => { svg.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, clientX: 500, clientY: 250 })) })
  expect(result.current.view.w).toBeCloseTo(WORLD_W / 64)
})
