// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { handlePreloadError } from './chunkReload'

afterEach(() => sessionStorage.clear())

describe('vite:preloadError — jednorazowe przeładowanie po wdrożeniu', () => {
  it('pierwszy błąd chunku → reload; drugi zaraz po nim → bez pętli', () => {
    const reload = vi.fn()
    const ev1 = new Event('vite:preloadError', { cancelable: true })
    handlePreloadError(ev1, reload)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(ev1.defaultPrevented).toBe(true)
    const ev2 = new Event('vite:preloadError', { cancelable: true })
    handlePreloadError(ev2, reload)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(ev2.defaultPrevented).toBe(false)
  })
})
