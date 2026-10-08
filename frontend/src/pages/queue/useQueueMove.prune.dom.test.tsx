// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: zaznaczenie w kolejce nie przeżywa zmiany filtrów
// serwerowych — po nowym load() zostają tylko id obecne na liście, więc akcje
// zbiorcze (usuń, zmień status, awizacja) nie trafiają w niewidoczne kontenery.
import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('../../api', () => ({ api: { patch: vi.fn() } }))

import { useQueueMove } from './useQueueMove'
import type { Container } from '../../types'

const mk = (id: number) => ({ id, container_no: `C${id}` }) as Container
const noop = () => {}

describe('useQueueMove — przycinanie zaznaczenia do listy', () => {
  it('po zmianie listy (nowy filtr/wyszukiwanie) zostają tylko obecne id', () => {
    const { result, rerender } = renderHook(
      ({ containers }: { containers: Container[] }) => useQueueMove({
        containers, visible: containers, canMove: true, replaceContainer: noop, load: noop }),
      { initialProps: { containers: [mk(1), mk(2), mk(3), mk(4), mk(5)] } })
    act(() => result.current.setSelected(new Set([1, 2, 3, 4, 5])))
    rerender({ containers: [mk(2)] })
    expect([...result.current.selected]).toEqual([2])
  })

  it('bez zmian w liście zaznaczenie zostaje tym samym obiektem', () => {
    const containers = [mk(1), mk(2)]
    const { result, rerender } = renderHook(
      ({ list }: { list: Container[] }) => useQueueMove({
        containers: list, visible: list, canMove: true, replaceContainer: noop, load: noop }),
      { initialProps: { list: containers } })
    act(() => result.current.setSelected(new Set([1])))
    const before = result.current.selected
    rerender({ list: [...containers] })
    expect(result.current.selected).toBe(before)
  })
})
