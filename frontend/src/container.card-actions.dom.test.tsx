// @vitest-environment jsdom
// Jeden akcent (pomiar 60-30-10, 2026-09-28): na karcie kontenera wypełniony przycisk ma tylko
// główna akcja strony („Edytuj”). Stale widoczne formularze sekcji (zlecenia, odprawa, kierowca)
// mają przyciski obrysowane (.btn.secondary) — wcześniej 5 wypełnionych naraz.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import type { Container } from './types'

const { role } = vi.hoisted(() => ({ role: { current: 'admin' } }))
vi.mock('./api', () => ({
  api: {
    get: vi.fn((url: string) => Promise.resolve(url.endsWith('/driver-sms')
      ? { configured: false, messages: [] } : [])),
    post: vi.fn(), patch: vi.fn(),
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ id: 1, role: role.current }) }))
vi.mock('./i18n', async importOriginal => ({
  ...(await importOriginal<typeof import('./i18n')>()), useT: () => (key: string) => key,
}))

import { CustomsAgencyPanel, DriverPanel, TransportOrdersPanel } from './collaboration'

const container = {
  id: 7, container_no: 'MSKU1234565', status: 'W_PORCIE', customs_status: 'ZLECONA',
  customs_agency_id: 3, customs_agency_name: 'Agencja', customs_agent_name: '', customs_agent_phone: '',
  customs_agent_email: '', driver_name: '', driver_id_no: '', truck_no: '', trailer_no: '', driver_phone: '',
} as unknown as Container

const filled = (root: HTMLElement) =>
  [...root.querySelectorAll('button.btn:not(.secondary)')].map(b => b.textContent)

afterEach(() => cleanup())

describe('karta kontenera — przyciski sekcji obrysowane', () => {
  it.each(['admin', 'customs', 'forwarder'])('rola %s: brak wypełnionych przycisków w spoczynku', async r => {
    role.current = r
    const { container: root } = render(<>
      <TransportOrdersPanel container={container} />
      <CustomsAgencyPanel container={container} onSaved={() => {}} />
      <DriverPanel container={container} onSaved={() => {}} />
    </>)
    await waitFor(() => expect(root.querySelectorAll('button.btn').length).toBeGreaterThan(0))
    expect(filled(root)).toEqual([])
  })
})
