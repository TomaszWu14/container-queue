// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ContainerPackingPanel from './ContainerPacking'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: (e: Error) => e.message }))

afterEach(() => { cleanup(); apiGet.mockReset() })

const okData = {
  status: 'ok',
  boxes: [
    { x: 0, y: 0, z: 0, w: 60, h: 30, d: 40, sku: '100200', color: '#aa4455', approximated: false },
    { x: 60, y: 0, z: 0, w: 50, h: 50, d: 50, sku: '100300', color: '#44aa55', approximated: true },
  ],
  fill_pct: 104.2,
  volume_used_m3: 34.5,
  volume_total_m3: 33.1,
  container_dims: { l: 589, w: 235, h: 239 },
  excluded: [{ order_no: '4500011111', material: '999999', reason: 'nie zmieściło się' }],
}

describe('ContainerPackingPanel', () => {
  it('renderuje HUD (%, m³, czerwony >100%) i listę nieuwzględnionych z mock JSON', async () => {
    apiGet.mockResolvedValue(okData)
    render(<MemoryRouter><ContainerPackingPanel containerId={7} /></MemoryRouter>)

    const hud = await screen.findByTestId('packing-hud')
    expect(hud.textContent).toContain('104,2')          // formatNum pl-PL
    expect(hud.textContent).toContain('34,5')
    expect(hud.textContent).toContain('33,1')
    // przepełnienie >100% -> czerwony
    expect(hud.innerHTML).toContain('rgb(248, 113, 113)')

    // jsdom bez WebGL -> feature-detect pokazuje komunikat zamiast sceny
    expect(screen.getByText('packNoWebgl')).toBeTruthy()
    // legenda bloków szacowanych (approximated w danych)
    expect(screen.getByText('packApproxLegend')).toBeTruthy()

    // lista excluded + link do Master data -> MARM
    expect(screen.getByText('999999')).toBeTruthy()
    expect(screen.getByText('nie zmieściło się')).toBeTruthy()
    expect(screen.getByText('packGoMarm').closest('a')!.getAttribute('href'))
      .toBe('/master-data/jednostki-materialow')
  })

  it('status no_type -> komunikat zamiast sceny', async () => {
    apiGet.mockResolvedValue({ status: 'no_type' })
    render(<MemoryRouter><ContainerPackingPanel containerId={7} /></MemoryRouter>)
    expect(await screen.findByText('packNoType')).toBeTruthy()
    expect(screen.queryByTestId('packing-hud')).toBeNull()
  })

  it('status no_data (wszystko excluded) -> informacja + lista braków', async () => {
    apiGet.mockResolvedValue({
      status: 'no_data', boxes: [], fill_pct: 0, excluded: [
        { order_no: '450002', material: '111111', reason: 'brak danych MARM (wymiarów i objętości)' },
      ],
    })
    render(<MemoryRouter><ContainerPackingPanel containerId={7} /></MemoryRouter>)
    expect(await screen.findByText('packNoData')).toBeTruthy()
    expect(screen.getByText('111111')).toBeTruthy()
  })

  it('status no_items -> panel się nie renderuje', async () => {
    apiGet.mockResolvedValue({ status: 'no_items' })
    const { container } = render(
      <MemoryRouter><ContainerPackingPanel containerId={7} /></MemoryRouter>)
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(container.querySelector('.panel')).toBeNull()
  })
})
