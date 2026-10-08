// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { SentLinksPanel } from './ContainerItems'
import type { Container } from '../types'

// S10 (audyt UI): historia linków SENT — magazyn (decyzja: NIE) i agencja nie wołają API.
vi.mock('../i18n', async (orig) => ({
  ...await orig<typeof import('../i18n')>(), useT: () => (k: string) => k,
}))
const { role } = vi.hoisted(() => ({ role: { v: 'logistics' } }))
vi.mock('../App', () => ({ useUser: () => ({ role: role.v }) }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: String }))

const container = { id: 5, order_numbers: '4500000001', order_number: null } as unknown as Container
afterEach(() => { cleanup(); apiGet.mockReset(); role.v = 'logistics' })

it('logistyka widzi linki SENT', async () => {
  apiGet.mockResolvedValue([{ id: 1, sent_number: 'SENT-77', order_number: '4500000001', note: '' }])
  render(<SentLinksPanel container={container} />)
  expect(await screen.findByText('SENT-77')).toBeTruthy()
})

it.each(['warehouse', 'customs'])('%s: brak zapytania i brak panelu', r => {
  role.v = r
  const { container: root } = render(<SentLinksPanel container={container} />)
  expect(apiGet).not.toHaveBeenCalled()
  expect(root.innerHTML).toBe('')
})
