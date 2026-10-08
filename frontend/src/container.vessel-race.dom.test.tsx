// @vitest-environment jsdom
// Ostrzeżenie „statek przy porcie” nie może zależeć od kolejności odpowiedzi API:
// /tracking/vessels potrafi wrócić przed /containers/:id.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Container } from './types'

let resolveContainer: (c: Container) => void = () => {}
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve([])), put: vi.fn(), patch: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
})
vi.mock('./dates', () => ({ formatDate: (s: string) => s, formatDateTime: (s: string) => s,
                            relTime: () => 'nigdy', parseServerTs: (s: string) => new Date(s),
                            formatNum: (n: number) => String(n) }))
vi.mock('./components', () => ({
  ContainerFormModal: () => null, CustomsBadge: () => null, DocumentBadge: () => null,
  PurchasingBadge: () => null, StatusBadge: () => null, StatusModal: () => null,
  useDicts: () => ({}),
}))
vi.mock('./collaboration', () => ({
  AttachmentsPanel: () => null, CustomsAgencyPanel: () => null,
  DriverPanel: () => null, MessagesPanel: () => null, TransportOrdersPanel: () => null,
}))
vi.mock('./pages/ContainerItems', () => ({ ItemsPanel: () => null, SentLinksPanel: () => null }))
vi.mock('./pages/ComplaintsPanel', () => ({ ComplaintsPanel: () => null }))

import ContainerPage from './pages/ContainerPage'

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('ContainerPage — statek przy porcie', () => {
  it('vessels wraca przed kontenerem → ostrzeżenie i tak liczone dla statku kontenera', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/api/tracking/vessels')
        return Promise.resolve([{ name: 'MV DEMO BOREAS', near_port: 'GDANSK' }])
      if (url === '/api/containers/1')
        return new Promise<Container>(r => { resolveContainer = r })
      return Promise.resolve([])
    })
    render(
      <MemoryRouter initialEntries={['/kontenery/1']}>
        <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
      </MemoryRouter>,
    )
    // vessels już rozstrzygnięte, kontener przychodzi dopiero teraz
    await new Promise(r => setTimeout(r, 0))
    resolveContainer({ id: 1, container_no: 'CONT1', status: 'W_TRANSPORCIE',
      vessel: 'mv-demo-boreas', is_delayed: false } as unknown as Container)
    expect(await screen.findByText('GDANSK')).toBeTruthy()
  })
})
