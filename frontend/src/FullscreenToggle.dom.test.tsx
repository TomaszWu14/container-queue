// @vitest-environment jsdom
// Pełny ekran: przycisk włącza/wyłącza przez Fullscreen API, ikona i podpis idą za stanem przeglądarki.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
import FullscreenToggle from './FullscreenToggle'

const setFs = (el: Element | null) => Object.defineProperty(document, 'fullscreenElement', { value: el, configurable: true })

afterEach(() => { cleanup(); setFs(null) })

describe('FullscreenToggle', () => {
  it('włącza i wyłącza pełny ekran, reaguje na fullscreenchange (np. Esc)', async () => {
    Object.defineProperty(document, 'fullscreenEnabled', { value: true, configurable: true })
    const request = vi.fn(() => Promise.resolve())
    const exit = vi.fn(() => Promise.resolve())
    document.documentElement.requestFullscreen = request
    document.exitFullscreen = exit
    render(<FullscreenToggle />)
    fireEvent.click(screen.getByRole('button', { name: 'fsEnter' }))
    expect(request).toHaveBeenCalled()
    act(() => { setFs(document.documentElement); document.dispatchEvent(new Event('fullscreenchange')) })
    fireEvent.click(screen.getByRole('button', { name: 'fsExit' }))
    expect(exit).toHaveBeenCalled()
    act(() => { setFs(null); document.dispatchEvent(new Event('fullscreenchange')) })
    expect(screen.getByRole('button', { name: 'fsEnter' })).toBeTruthy()
  })

  it('bez Fullscreen API — brak przycisku', () => {
    Object.defineProperty(document, 'fullscreenEnabled', { value: false, configurable: true })
    const { container } = render(<FullscreenToggle />)
    expect(container.innerHTML).toBe('')
  })
})
