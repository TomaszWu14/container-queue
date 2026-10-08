// @vitest-environment jsdom
// Strażnik UX-041: historia w szufladzie kolejki pokazuje datę dd.mm.rrrr (formatDateTime),
// nie surowy ISO „2026-09-28 10:30" wycięty z created_at.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet, post: vi.fn() }, errorMessage: String }))
vi.mock('../../i18n', async orig => ({ ...(await orig<object>()), useT: () => (key: string) => key }))

import QueueDrawer from './QueueDrawer'
import type { Container } from '../../types'

afterEach(() => { cleanup(); apiGet.mockReset() })

const C = { id: 7, container_no: 'TRHU0003565', status: 'W_DRODZE', updated_at: 'x' } as unknown as Container

describe('szuflada kolejki — historia', () => {
  it('data zmiany w formacie dd.mm.rrrr, bez surowego ISO', async () => {
    apiGet.mockImplementation((url: string) => Promise.resolve(url.endsWith('/history')
      ? [{ id: 1, field: 'status', old_value: 'A', new_value: 'B', user_login: 'jan',
           created_at: '2026-09-28T10:30:00', note: null }]
      : []))
    render(<QueueDrawer c={C} fill={null} onPrev={null} onNext={null} onClose={() => {}}
                        onStatus={null} statusLabel="Status" onAvizo={null} onFull={() => {}} />)
    fireEvent.click(await screen.findByRole('tab', { name: /kqdHistory/ }))
    const meta = await screen.findByText(/28\.09\.2026/)
    expect(meta.textContent).not.toMatch(/2026-09-28|T10:30/)
  })
})
