// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { UserContext } from '../userContext'
import type { Role, User } from '../types'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: apiPost, upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))
vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,QQ==') },
}))

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

const container = {
  id: 5, container_no: 'MSDU0806613', supplier_name: 'ACME', vessel: 'MV DEMO ATLAS',
  eta: '2026-09-10', notify_date: '2026-09-18', warehouse_name: 'DLT',
  pallet_count: 20, notes: '', unload_started_at: null, unload_finished_at: null,
}

function mockApi(c: object) {
  apiGet.mockImplementation((path: string) => {
    if (path === '/api/containers/5') return Promise.resolve(c)
    if (path.endsWith('/palletization')) return Promise.resolve({ configured: false })
    if (path.endsWith('/unload-photos')) return Promise.resolve([])
    return Promise.reject(new Error('x'))
  })
}

async function renderPage(role: Role = 'warehouse') {
  const { default: Page } = await import('./KartaRozladunkuPage')
  render(
    <UserContext.Provider value={{ user: { id: 1, role } as User, reload: () => {} }}>
      <MemoryRouter initialEntries={['/kontenery/5/karta']}>
        <Routes><Route path="/kontenery/:id/karta" element={<Page />} /></Routes>
      </MemoryRouter>
    </UserContext.Provider>,
  )
}

describe('Karta rozładunku — W10', () => {
  it('#61: Start rozładunku strzela do API; po starcie widać Stop', async () => {
    mockApi(container)
    apiPost.mockResolvedValue({})
    await renderPage()
    const start = await screen.findByRole('button', { name: /Start rozładunku/ })
    fireEvent.click(start)
    expect(apiPost).toHaveBeenCalledWith('/api/containers/5/unload/start', {})

    cleanup()
    mockApi({ ...container, unload_started_at: '2026-09-18T06:00:00' })
    await renderPage()
    expect(await screen.findByRole('button', { name: /Stop rozładunku/ })).toBeTruthy()
    expect(screen.getByText('Rozładunek trwa')).toBeTruthy()
  })

  it('#61: czas trwania na karcie po zakończeniu', async () => {
    mockApi({
      ...container,
      unload_started_at: '2026-09-18T06:00:00',
      unload_finished_at: '2026-09-18T07:30:00',
    })
    await renderPage()
    expect(await screen.findByText('90 min')).toBeTruthy()
  })

  it('#62: przycisk Drukuj etykietę QR ustawia klasę print i renderuje etykietę', async () => {
    mockApi(container)
    await renderPage()
    const printSpy = vi.fn()
    window.print = printSpy
    const btn = await screen.findByRole('button', { name: /Drukuj etykietę QR/ })
    let hadClass = false
    printSpy.mockImplementation(() => {
      hadClass = document.body.classList.contains('print-qr-label')
    })
    fireEvent.click(btn)
    expect(printSpy).toHaveBeenCalled()
    expect(hadClass).toBe(true)   // klasa aktywna w trakcie window.print()
    expect(document.body.classList.contains('print-qr-label')).toBe(false)
    // etykieta zawiera numer kontenera (drugi egzemplarz obok nagłówka)
    expect(screen.getAllByText('MSDU0806613').length).toBeGreaterThanOrEqual(2)
  })

  it('#64: zdjęcie ma przycisk Utwórz reklamację', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/containers/5') return Promise.resolve(container)
      if (path.endsWith('/palletization')) return Promise.resolve({ configured: false })
      if (path.endsWith('/unload-photos'))
        return Promise.resolve([{ id: 9, filename: 'f.jpg', caption: '', created_at: '' }])
      return Promise.reject(new Error('x'))
    })
    apiPost.mockResolvedValue({ complaint_id: 3, number: 'REK-X' })
    await renderPage()
    const btn = await screen.findByRole('button', { name: /Utwórz reklamację/ })
    fireEvent.click(btn)
    expect(apiPost).toHaveBeenCalledWith('/api/unload-photos/9/complaint', {})
  })
})

describe('Karta rozładunku — przyciski zgodne z rolą (backend WarehouseOrEditors)', () => {
  it('spedytor: karta tylko do odczytu — bez Start, zdjęć i reklamacji', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/containers/5') return Promise.resolve(container)
      if (path.endsWith('/palletization')) return Promise.resolve({ configured: false })
      if (path.endsWith('/unload-photos'))
        return Promise.resolve([{ id: 9, filename: 'f.jpg', caption: '', created_at: '' }])
      return Promise.reject(new Error('x'))
    })
    await renderPage('forwarder')
    expect(await screen.findByText('f.jpg')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Start rozładunku/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Utwórz reklamację/ })).toBeNull()
    expect(screen.queryByText(/Dodaj zdjęcie/)).toBeNull()
  })
})

describe('durationMinutes', () => {
  it('liczy minuty i odrzuca ujemne', async () => {
    const { durationMinutes } = await import('./KartaRozladunkuPage')
    expect(durationMinutes('2026-09-18T06:00:00', '2026-09-18T06:45:00')).toBe(45)
    expect(durationMinutes('2026-09-18T07:00:00', '2026-09-18T06:00:00')).toBeNull()
    expect(durationMinutes(null, '2026-09-18T06:00:00')).toBeNull()
  })
})
