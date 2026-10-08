// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: „zaznacz wszystko" w kolejce bierze tylko kontenery
// widoczne po filtrach klienta (★ Moje, 🚩 Specjalne), nie całą listę z serwera.
import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('../../api', () => ({ api: { patch: vi.fn() } }))

import { useQueueMove } from './useQueueMove'
import type { Container } from '../../types'

const mk = (id: number) => ({ id, container_no: `C${id}` }) as Container

describe('useQueueMove — zaznacz wszystko', () => {
  it('zaznacza tylko widoczne kontenery, ukryte filtrem klienta zostają poza', () => {
    const containers = [mk(1), mk(2), mk(3)]
    const visible = [containers[0]]  // np. ★ Moje: obserwowany tylko #1
    const { result } = renderHook(() => useQueueMove({
      containers, visible, canMove: true, replaceContainer: () => {}, load: () => {} }))
    act(() => result.current.toggleSelectAll())
    expect([...result.current.selected]).toEqual([1])
    expect(result.current.allSelected).toBe(true)
    // drugi klik odznacza
    act(() => result.current.toggleSelectAll())
    expect(result.current.selected.size).toBe(0)
  })
})
