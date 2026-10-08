// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import AuditTab from './AuditTab'

// #49: viewer audytu — lista wpisów + filtry przekazywane do /api/audit.
vi.mock('../../i18n', async (orig) => ({
  ...await orig<typeof import('../../i18n')>(), useT: () => (k: string) => k,
}))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet }, errorMessage: String }))
afterEach(() => { cleanup(); apiGet.mockReset() })

describe('AuditTab', () => {
  it('renderuje wpisy i wysyła filtry', async () => {
    apiGet.mockResolvedValue([{ id: 1, entity_type: 'container', entity_id: 7, field: 'eta',
      old_value: '2026-09-01', new_value: '2026-09-05', note: null, user_login: 'jan',
      created_at: '2026-09-22T10:00:00' }])
    render(<AuditTab />)
    expect(await screen.findByText('container #7')).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('auditEntity'), { target: { value: 'container' } })
    fireEvent.click(screen.getByText('search'))
    expect(apiGet).toHaveBeenLastCalledWith(expect.stringContaining('entity_type=container'))
  })
})
