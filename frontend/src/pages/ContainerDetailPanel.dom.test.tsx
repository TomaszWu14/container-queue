// @vitest-environment jsdom
// Strażnik T3 (2026-09-24): po zmianie statusu rozwinięty panel pobiera historię
// i oś czasu od nowa — wcześniej trzymał stan z chwili rozwinięcia.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn(() => Promise.resolve([])) }))
vi.mock('../api', () => ({ api: { get: apiGet } }))
vi.mock('../App', () => ({ useUser: () => ({ id: 1, role: 'admin' }) }))
vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../collaboration', () => ({ MessagesPanel: () => null, AttachmentsPanel: () => null }))
vi.mock('./ContainerItems', () => ({ ItemsPanel: () => null }))

import ContainerDetailPanel from './ContainerDetailPanel'
import type { Container } from '../types'

afterEach(cleanup)

const calls = (suffix: string) => apiGet.mock.calls.filter(c => String((c as unknown[])[0]).endsWith(suffix)).length

describe('ContainerDetailPanel', () => {
  it('nowe updated_at kontenera = ponowne pobranie historii i osi czasu', async () => {
    const c = { id: 7, container_no: 'TRHU0003565', status: 'AWIZOWANY', updated_at: '2026-09-24T09:48:00' } as Container
    const view = (x: Container) => <MemoryRouter><ContainerDetailPanel container={x} /></MemoryRouter>
    const { rerender } = render(view(c))
    await waitFor(() => expect(calls('/history')).toBe(1))
    expect(calls('/timeline')).toBe(1)
    rerender(view({ ...c, status: 'ODPRAWA', updated_at: '2026-09-24T09:54:00' }))
    await waitFor(() => expect(calls('/history')).toBe(2))
    expect(calls('/timeline')).toBe(2)
  })
  it('„Zwiń” i Esc zwijają panel; Esc w polu tekstowym nie zwija', () => {
    const c = { id: 8, container_no: 'FFAU6240568', status: 'AWIZOWANY', updated_at: '2026-09-25T10:00:00' } as Container
    const onClose = vi.fn()
    render(<MemoryRouter><ContainerDetailPanel container={c} onClose={onClose} /><input aria-label="pole" /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'cdCollapse' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(screen.getByLabelText('pole'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('bez onClose nie ma przycisku „Zwiń” (karta kontenera)', () => {
    const c = { id: 9, container_no: 'X', status: 'AWIZOWANY' } as Container
    render(<MemoryRouter><ContainerDetailPanel container={c} /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: 'cdCollapse' })).toBeNull()
  })
})
