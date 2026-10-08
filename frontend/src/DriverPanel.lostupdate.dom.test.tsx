// @vitest-environment jsdom
// Dane kierowcy: zapis niesie updated_at z chwili wczytania formularza (backend → 409 przy cudzej
// zmianie w międzyczasie); po udanym zapisie kolejny niesie updated_at z odpowiedzi.
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import type { Container } from './types'

const { apiPatch } = vi.hoisted(() => ({ apiPatch: vi.fn() }))
vi.mock('./api', () => ({
  api: { get: vi.fn(() => Promise.resolve({ configured: false, messages: [] })), patch: apiPatch },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./i18n', async importOriginal => ({
  ...(await importOriginal<typeof import('./i18n')>()), useT: () => (key: string) => key,
}))

import { DriverPanel } from './DriverPanel'

afterEach(() => { cleanup(); apiPatch.mockReset() })

const container = { id: 7, updated_at: '2026-10-05T06:00:00.123456', driver_name: '', driver_id_no: '',
  truck_no: '', trailer_no: '', driver_phone: '' } as unknown as Container

it('PATCH kierowcy zawiera expected_updated_at, a po zapisie bierze nowy z odpowiedzi', async () => {
  apiPatch.mockResolvedValue({ ...container, updated_at: '2026-10-05T07:00:00.000001' })
  const { container: root } = render(<DriverPanel container={container} onSaved={() => {}} />)
  fireEvent.submit(root.querySelector('form')!)
  await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1))
  expect(apiPatch.mock.calls[0][1]).toMatchObject({ expected_updated_at: '2026-10-05T06:00:00.123456' })
  await waitFor(() => expect(root.querySelector('button')!.hasAttribute('disabled')).toBe(false))
  fireEvent.submit(root.querySelector('form')!)
  await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(2))
  expect(apiPatch.mock.calls[1][1]).toMatchObject({ expected_updated_at: '2026-10-05T07:00:00.000001' })
})
