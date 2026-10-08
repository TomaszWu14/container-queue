// @vitest-environment jsdom
// Odpytywanie tylko w widocznej karcie: tick w ukrytej pomijany, powrót do karty = od razu świeże dane.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { useVisibleInterval } from './useVisibleInterval'

function Poller({ fn }: { fn: () => void }) { useVisibleInterval(fn, 1000); return null }

const setHidden = (hidden: boolean) =>
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })

afterEach(() => { cleanup(); vi.useRealTimers(); setHidden(false) })

describe('useVisibleInterval', () => {
  it('ukryta karta: brak zapytań; powrót: natychmiastowe odświeżenie', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    render(<Poller fn={fn} />)
    vi.advanceTimersByTime(1000)
    expect(fn).toHaveBeenCalledTimes(1)          // widoczna — tick działa

    setHidden(true)
    vi.advanceTimersByTime(5000)
    expect(fn).toHaveBeenCalledTimes(1)          // ukryta — ticki pominięte

    setHidden(false)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(fn).toHaveBeenCalledTimes(2)          // powrót — od razu, bez czekania na tick
  })

  it('odmontowanie zatrzymuje zegar', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    render(<Poller fn={fn} />)
    cleanup()
    vi.advanceTimersByTime(5000)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(fn).not.toHaveBeenCalled()
  })
})
