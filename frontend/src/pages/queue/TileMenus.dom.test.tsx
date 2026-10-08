// @vitest-environment jsdom
// Strażnik poprawek menu „⋯" (2026-09-24): bez daty/magazynu (edycja na rekordzie),
// kolejność Śledź teraz → Obserwowane; obserwowanie idzie przez ten sam stan co gwiazdka.
// Ręcznej „Specjalnej troski" już nie ma — flaga „pod klienta" liczy się sama z modułu.
import { useEffect } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }))
vi.mock('../../api', () => ({ api: { post: apiPost }, errorMessage: String }))
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

import TileMenus, { useTileMenus } from './TileMenus'
import type { Container } from '../../types'

afterEach(() => { cleanup(); apiPost.mockReset() })

const C = { id: 3, container_no: 'TRHU0003565', is_special: false } as Container

function Harness({ watched, toggleWatch, replace, watchPrompt = null, confirmWatch = () => {}, cancelWatch = () => {} }: {
  watched: Set<number>; toggleWatch: (id: number) => void; replace: (c: Container) => void
  watchPrompt?: number | null; confirmWatch?: (reason: string) => void; cancelWatch?: () => void
}) {
  const m = useTileMenus(replace)
  useEffect(() => { m.setTileMenu({ c: C, x: 10, y: 10 }) }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return <TileMenus m={m} warehouseOptions={['DLT']} canEdit setPendingMove={() => {}}
                    watched={watched} toggleWatch={toggleWatch}
                    watchPrompt={watchPrompt} confirmWatch={confirmWatch} cancelWatch={cancelWatch}
                    onDetails={() => {}} onStatus={null} statusLabel="Status" />
}

describe('menu ⋯ kafelka', () => {
  it('kolejność pozycji: szczegóły, data, magazyn, śledzenie, obserwuj', () => {
    render(<Harness watched={new Set()} toggleWatch={() => {}} replace={() => {}} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.map(b => b.textContent?.trim())).toEqual(['cdExpand', 'changeNotifyDate', 'changeWarehouse', 'watchAdd'])
    // ikony menu = SVG (lucide), nie emoji
    expect(buttons.every(b => b.querySelector('svg.lucide'))).toBe(true)
  })

  it('obserwowany kontener pokazuje „usuń" i przełącza przez wspólny toggleWatch', () => {
    const toggleWatch = vi.fn()
    render(<Harness watched={new Set([3])} toggleWatch={toggleWatch} replace={() => {}} />)
    fireEvent.click(screen.getByText('watchRemove'))
    expect(toggleWatch).toHaveBeenCalledWith(3)
  })

  it('okienko powodu gdy watchPrompt ustawiony — Obserwuj przekazuje powód', () => {
    const confirmWatch = vi.fn()
    render(<Harness watched={new Set()} toggleWatch={() => {}} replace={() => {}}
                    watchPrompt={3} confirmWatch={confirmWatch} cancelWatch={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'watchReasonComplaint' }))
    fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
    expect(confirmWatch).toHaveBeenCalledWith('watchReasonComplaint')
  })
})
