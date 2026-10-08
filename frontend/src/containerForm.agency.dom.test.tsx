// @vitest-environment jsdom
// A25 (audyt UI): formularz kontenera bez wolnego tekstu agencji celnej; stary wpis do odczytu
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ContainerFormModal } from './components'
import type { Container } from './types'

vi.mock('./api', () => ({ api: { get: vi.fn(() => Promise.resolve([])) }, errorMessage: String }))
afterEach(cleanup)

const dicts = { suppliers: [], forwarders: [], warehouses: [], ports: [], carriers: [] }
const mount = (extra: object) => render(<ContainerFormModal dicts={dicts} onSaved={vi.fn()} onClose={vi.fn()}
  initial={{ id: 1, container_no: 'MSDU0806613', company_id: 1, ...extra } as unknown as Container} />)

it('brak pola tekstowego; stary wpis bez słownika widoczny do odczytu', () => {
  mount({ customs_agency: 'Stara Agencja', customs_agency_id: null })
  expect(screen.queryByRole('textbox', { name: /Agencja celna/i })).toBeNull()
  expect(screen.getByText(/Stary wpis agencji \(tekst\): Stara Agencja/)).toBeTruthy()
})

it('agencja przypisana ze słownika — bez notki o starym wpisie', () => {
  mount({ customs_agency: 'Stara Agencja', customs_agency_id: 3 })
  expect(screen.queryByText(/Stary wpis agencji/)).toBeNull()
})
