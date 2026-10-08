// @vitest-environment jsdom
// Audyt DB-005: zapis formularza kontenera niesie updated_at z chwili otwarcia (backend → 409 przy
// cudzej zmianie w międzyczasie), a komunikat 409 zostaje w formularzu zamiast go zamykać.
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ContainerFormModal } from './components'
import type { Container } from './types'

const { apiPatch } = vi.hoisted(() => ({ apiPatch: vi.fn() }))
vi.mock('./api', () => ({ api: { get: vi.fn(() => Promise.resolve([])), patch: apiPatch },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)) }))
afterEach(() => { cleanup(); apiPatch.mockReset() })

const dicts = { suppliers: [], forwarders: [], warehouses: [], ports: [], carriers: [] }
const initial = { id: 1, container_no: 'MSDU0806613', company_id: 1,
  updated_at: '2026-09-28T06:00:00.123456' } as unknown as Container

it('PATCH zawiera expected_updated_at, 409 pokazuje komunikat i nie zamyka formularza', async () => {
  apiPatch.mockRejectedValue(new Error('Ktoś zmienił ten kontener w międzyczasie — odśwież'))
  const onClose = vi.fn()
  const { container } = render(<ContainerFormModal dicts={dicts} onSaved={vi.fn()} onClose={onClose} initial={initial} />)
  fireEvent.submit(container.querySelector('form')!)
  await waitFor(() => expect(apiPatch).toHaveBeenCalled())
  expect(apiPatch.mock.calls[0][1]).toMatchObject({ expected_updated_at: '2026-09-28T06:00:00.123456' })
  expect(await screen.findByText(/Ktoś zmienił ten kontener/)).toBeTruthy()
  expect(onClose).not.toHaveBeenCalled()
})
