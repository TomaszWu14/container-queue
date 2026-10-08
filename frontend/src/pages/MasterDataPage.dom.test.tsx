// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mdAt } from './mdRoute.testutil'
import MasterDataPage from './MasterDataPage'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../App', () => ({ useUser: () => ({ role: 'admin' }) }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet } }))

const companies = [{ id: 1, name: 'Acme', code: 'ACME', is_active: true }]
const suppliers = [
  { id: 10, name: 'Beta Tools', client_company_id: null, sap_code: '0000200', country: 'CN', address: '' },
  { id: 11, name: 'Alfa Ltd', client_company_id: null, sap_code: '0000100', country: 'DE', address: '' },
]

function mockApi(map: Record<string, unknown>) {
  apiGet.mockImplementation((url: string) => {
    // panel „Do zmapowania" w zakładce dostawców — pusty, żeby nie dublował nazw
    if (url.startsWith('/api/suppliers/unmapped')) return Promise.resolve([])
    const key = Object.keys(map).find(k => url.startsWith(k))
    return key ? Promise.resolve(map[key]) : Promise.reject(new Error('unmocked ' + url))
  })
}

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('MasterDataPage', () => {
  it('dostawcy: renderuje wiersze, filtruje po kodzie SAP, sortuje po kliku nagłówka', async () => {
    mockApi({ '/api/companies': companies, '/api/suppliers': suppliers })
    render(mdAt('dostawcy', <MasterDataPage />))

    await screen.findByText('Beta Tools')
    expect(screen.getByText('Alfa Ltd')).toBeTruthy()
    // link do istniejącej strony dostawcy
    expect(screen.getByText('Alfa Ltd').closest('a')!.getAttribute('href'))
      .toBe('/dostawcy/11')

    // sort po nazwie (klik nagłówka "name")
    fireEvent.click(screen.getByText('name'))
    const rows = document.querySelectorAll('tbody tr')
    expect(rows[0].textContent).toContain('Alfa Ltd')

    // wyszukiwarka łapie kod SAP
    fireEvent.change(screen.getByPlaceholderText('mdSearch'), { target: { value: '0000200' } })
    await waitFor(() => expect(screen.queryByText('Alfa Ltd')).toBeNull())
    expect(screen.getByText('Beta Tools')).toBeTruthy()
    expect(screen.getByText(/1 mdRows/)).toBeTruthy()
  })

  it('zamówienia SAP: pobiera z unlinked=false i przekazuje filtry do API', async () => {
    mockApi({
      '/api/companies': companies,
      '/api/suppliers': suppliers,
      '/api/purchase-orders': [{
        id: 5, order_no: 'PO-77', supplier: 'Alfa Ltd', etd: null, ready_date: '',
        transport_mode: 'SEA', purchase_decision: 'OK', port_of_departure: '',
        amount: 1000, container_id: null, company_id: 1, created_at: '2026-09-01T00:00:00',
      }],
    })
    render(mdAt('zamowienia-sap', <MasterDataPage />))

    await screen.findByText('PO-77')
    const urls = apiGet.mock.calls.map(c => String(c[0]))
    expect(urls.some(u => u.startsWith('/api/purchase-orders?') && u.includes('unlinked=false')))
      .toBe(true)

    fireEvent.change(screen.getByPlaceholderText('mdSearch'), { target: { value: 'alfa' } })
    await waitFor(() => {
      const last = apiGet.mock.calls.map(c => String(c[0]))
        .filter(u => u.startsWith('/api/purchase-orders')).pop()!
      expect(last).toContain('q=alfa')
    })
  })

  it('jednostki MARM: pobiera listę i przekazuje q do API', async () => {
    mockApi({
      '/api/companies': companies,
      '/api/suppliers': suppliers,
      '/api/material-units': [{
        id: 1, material_no: '100200', unit: 'KAR', numerator: 10, denominator: 1,
        volume: 120, volume_unit: 'CDM', gross_weight: 5, weight_unit: 'KG',
      }],
    })
    render(mdAt('jednostki-materialow', <MasterDataPage />))

    await screen.findByText('100200')
    expect(screen.getByText('KAR')).toBeTruthy()
    expect(screen.getByText('120 CDM')).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText('mdMaterialSearch'),
                     { target: { value: '555' } })
    await waitFor(() => {
      const last = apiGet.mock.calls.map(c => String(c[0]))
        .filter(u => u.startsWith('/api/material-units')).pop()!
      expect(last).toContain('q=555')
    })
  })

  it('jednostki MARM: „brak w SAP” widoczny przy materiale (przelicznik nadal liczony)', async () => {
    mockApi({
      '/api/companies': companies,
      '/api/suppliers': suppliers,
      '/api/material-units': [
        { id: 1, material_no: '100200', unit: 'PAL', numerator: 40, denominator: 1, sap_status: 'brak_w_sap' },
        { id: 2, material_no: '100300', unit: 'PAL', numerator: 50, denominator: 1, sap_status: 'aktywny' },
      ],
    })
    render(mdAt('jednostki-materialow', <MasterDataPage />))

    await screen.findByText('100300')
    expect(screen.getAllByText('sapMissingBadge')).toHaveLength(1)
    expect(screen.getByText('sapMissingBadge').closest('tr')!.textContent).toContain('100200')
  })

  it('słownik magazynów: własna sekcja z wyszukiwarką', async () => {
    mockApi({
      '/api/companies': companies,
      '/api/suppliers': suppliers,
      '/api/warehouses': [{ id: 3, name: 'Magazyn DLT', company_id: 1, country: 'LT', email: '' }],
    })
    render(mdAt('magazyny', <MasterDataPage />))
    await screen.findByText('Magazyn DLT')
    fireEvent.change(screen.getByPlaceholderText('mdSearch'), { target: { value: 'xxx' } })
    await waitFor(() => expect(screen.queryByText('Magazyn DLT')).toBeNull())
  })
})
