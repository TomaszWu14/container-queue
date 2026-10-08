// @vitest-environment jsdom
// W11: strona statystyk szkód (rejestr) + checklista kontroli przyjęcia.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ComplaintStatsPage from './ComplaintStatsPage'
import { ChecklistPanel } from './ChecklistPanel'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, put: apiPut },
  errorMessage: (e: unknown) => String(e),
}))

afterEach(() => { cleanup(); apiGet.mockReset(); apiPut.mockReset() })

describe('ComplaintStatsPage — rejestr szkód', () => {
  const stats = {
    months: 12,
    suppliers: [
      { name: 'Dostawca A', containers: 4, with_complaint: 2, pct: 50 },
      { name: 'Dostawca B', containers: 10, with_complaint: 1, pct: 10 },
    ],
    carriers: [{ name: 'Maersk', containers: 14, with_complaint: 3, pct: 21.4 }],
    costs: [{ currency: 'USD', claim: 1000, recovered: 250, recovery_pct: 25 }],
  }

  it('renderuje tabele dostawców/armatorów i koszty ze skutecznością odzysku', async () => {
    apiGet.mockResolvedValue(stats)
    render(<MemoryRouter><ComplaintStatsPage /></MemoryRouter>)
    await screen.findByText('Dostawca A')
    expect(screen.getByText('Maersk')).toBeTruthy()
    expect(screen.getByText('50%')).toBeTruthy()
    expect(screen.getByText('USD')).toBeTruthy()
    expect(screen.getByText('25%')).toBeTruthy()   // skuteczność odzysku
  })

  it('sortuje po kliknięciu nagłówka (odwrócenie kierunku)', async () => {
    apiGet.mockResolvedValue(stats)
    render(<MemoryRouter><ComplaintStatsPage /></MemoryRouter>)
    await screen.findByText('Dostawca A')
    // domyślnie sort po pct desc: A (50) przed B (10)
    let rows = [...document.querySelectorAll('tbody tr')].map(r => r.textContent)
    expect(rows.findIndex(r => r?.includes('Dostawca A')))
      .toBeLessThan(rows.findIndex(r => r?.includes('Dostawca B')))
    // klik w "Kontenery" → desc po liczbie kontenerów: B (10) przed A (4)
    fireEvent.click(screen.getAllByText(/complaintStatsContainers/)[0])
    rows = [...document.querySelectorAll('tbody tr')].map(r => r.textContent)
    expect(rows.findIndex(r => r?.includes('Dostawca B')))
      .toBeLessThan(rows.findIndex(r => r?.includes('Dostawca A')))
  })
})

describe('ChecklistPanel — kontrola przyjęcia', () => {
  const rows = [
    { point_id: 1, name: 'Plomba', result: null, note: '', checked_by_login: null, checked_at: null },
    { point_id: 2, name: 'Towar bez uszkodzeń', result: 'NOK', note: 'wgniecenia',
      checked_by_login: 'magazyn', checked_at: '2026-09-18T10:00:00' },
  ]

  it('editable: zapisuje wyniki i pokazuje hint przy NOK', async () => {
    apiGet.mockResolvedValue(rows)
    apiPut.mockResolvedValue(rows)
    render(<ChecklistPanel containerId={7} editable />)
    await screen.findByText('Plomba')
    expect(screen.getByText(/checklistNokHint/)).toBeTruthy()   // NOK z API
    // zaznacz OK dla plomby i zapisz
    fireEvent.click(screen.getAllByText('OK')[0])
    fireEvent.click(screen.getByText('checklistSave'))
    await waitFor(() => expect(apiPut).toHaveBeenCalled())
    const [url, body] = apiPut.mock.calls[0]
    expect(url).toBe('/api/containers/7/checklist')
    expect(body.items).toContainEqual({ point_id: 1, result: 'OK', note: '' })
  })

  it('read-only: pokazuje badge wyniku bez przycisków', async () => {
    apiGet.mockResolvedValue(rows)
    render(<ChecklistPanel containerId={7} editable={false} />)
    await screen.findByText('Towar bez uszkodzeń')
    expect(screen.getByText('NOK')).toBeTruthy()
    expect(screen.queryByText('checklistSave')).toBeNull()
  })

  it('read-only bez żadnych wyników: nie renderuje sekcji', async () => {
    apiGet.mockResolvedValue([{ point_id: 1, name: 'Plomba', result: null, note: '',
      checked_by_login: null, checked_at: null }])
    const { container } = render(<ChecklistPanel containerId={7} editable={false} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    await waitFor(() => expect(container.innerHTML).toBe(''))
  })
})
