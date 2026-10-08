// @vitest-environment jsdom
// Telefon i magazyn (audyt UI A6/C28 — UX-019, UX-037):
// - pulpit na telefonie: KPI w siatce 2 × 3 w wersji kompaktowej, lista działań jako karty
//   (bez przewijania tabeli w bok) — dawniej 6 kafli po ~230 px wypychało listę poza 3 ekrany,
// - kolejka magazynu: kompaktowa tabela (nr, status, data dostawy, magazyn…) z klikalnym wierszem
//   i przyciskiem secondary zamiast wielkich kart z pełnym turkusowym „Pokaż szczegóły”.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readAppCss } from './appCss.testutil'

vi.mock('./api', () => ({
  api: { get: vi.fn((p: string) => Promise.resolve(p === '/api/containers' ? [
    { id: 1, container_no: 'DLT0000001', status: 'AWIZOWANY', notify_date: '2026-10-02', warehouse_name: 'DLT',
      container_size: "40'HC", pallet_count: 20, materials_list: 'Lampy', palletization_note: '' },
    { id: 2, container_no: 'DLT0000002', status: 'W_PORCIE', notify_date: '2026-10-01', warehouse_name: 'DLT',
      container_size: null, pallet_count: null, materials_list: '', palletization_note: '' },
  ] : [])), post: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ id: 1, role: 'warehouse' }) }))
vi.mock('./pages/ComplaintsPanel', () => ({ ComplaintsPanel: () => <div>REKLAMACJE</div> }))

import WarehouseQueuePage from './pages/WarehouseQueuePage'

afterEach(cleanup)

describe('telefon i magazyn', () => {
  it('pulpit ≤ 640 px: KPI 2 kolumny kompaktowo, lista działań jako karty', () => {
    const css = readAppCss()
    const mobile = [...css.matchAll(/@media \(max-width: 640px\) \{([\s\S]*?)\n\}/g)].map(m => m[1]).join('\n')
    expect(mobile).toMatch(/\.ctl-kpis \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
    expect(mobile).toMatch(/\.ctl-kpi-sub \{ display: none; \}/)
    expect(mobile).toMatch(/\.ctl-actions table\.grid thead \{ display: none; \}/)
    expect(mobile).toMatch(/\.ctl-actions table\.grid tr \{ display: grid;/)
  })

  it('kolejka magazynu: tabela, wiersze wg daty dostawy, bez pełnych przycisków, szczegóły po kliknięciu', async () => {
    render(<WarehouseQueuePage />)
    await screen.findByText('DLT0000001')
    const rows = [...document.querySelectorAll('table.grid tbody tr.clickable')]
    expect(rows.map(r => r.querySelector('.mono')?.textContent)).toEqual(['DLT0000002', 'DLT0000001'])
    expect(document.querySelectorAll('button.btn:not(.secondary)')).toHaveLength(0)
    expect(screen.queryByText('REKLAMACJE')).toBeNull()
    fireEvent.click(rows[1])
    expect(screen.getByText('REKLAMACJE')).toBeTruthy()
    expect(screen.getByText('Lampy')).toBeTruthy()
  })
})
