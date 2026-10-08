// @vitest-environment jsdom
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useT } from './i18n'

describe('useT', () => {
  it('zwraca tÄ™ samÄ… funkcjÄ™ miÄ™dzy renderami (brak pÄ™tli w useEffect z [t])', () => {
    const { result, rerender } = renderHook(() => useT())
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })
})
