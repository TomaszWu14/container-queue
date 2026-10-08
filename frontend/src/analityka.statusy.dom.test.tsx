// @vitest-environment jsdom
import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import AnalitykaPage from './pages/AnalitykaPage'

// B23 (audyt UI): rozkład statusów z etykietami jak w kolejce, bez surowych kodów enum
vi.mock('./api', () => ({
  api: { get: vi.fn(() => Promise.resolve({ total: 3, by_status: { W_PRODUKCJI: 2, W_PORCIE: 1 },
    throughput: [], avg_lead_time_days: null, avg_unload_minutes: null,
    top_suppliers: [], top_warehouses: [] })) },
  errorMessage: String,
}))

it('pokazuje polskie etykiety statusów zamiast kodów', async () => {
  render(<AnalitykaPage />)
  expect(await screen.findByText('2 · Produkcja / gotowość')).toBeTruthy()
  expect(screen.queryByText(/W_PRODUKCJI/)).toBeNull()
})
