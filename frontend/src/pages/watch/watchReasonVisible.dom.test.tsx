// @vitest-environment jsdom
// Strażnik (2026-09-30): powód obserwacji był zapisywany, ale nigdzie niewidoczny.
// Kolejka: etykieta przy numerze (+ title), szuflada: ★ + powód, mapa: ★ nad statkiem + lista w podpowiedzi.
import { createContext } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, renderHook, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api', () => ({ api: { get: vi.fn(() => Promise.resolve([])), post: vi.fn() }, errorMessage: String }))
vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
vi.mock('../ContainerDetailPanel', () => ({ default: () => null }))

import EnterpriseTable from '../queue/EnterpriseTable'
import type { TableCtx } from '../queue/EnterpriseTable'
import QueueDrawer from '../queue/QueueDrawer'
import FlatMap from '../tracking/FlatMap'
import { useMapLayers } from '../tracking/MapLayers'
import { useMapView } from '../tracking/useMapView'
import type { Vessel } from '../tracking/types'
import type { Container } from '../../types'

afterEach(cleanup)

const row = (id: number) => ({
  id, container_no: `MSCU000000${id}`, status: 'W_PORCIE', warehouse_name: 'DLT',
  supplier_name: 'X', vessel: 'MV DEMO ATLAS', customs_status: 'BRAK',
}) as unknown as Container

const ctx = (watched: number[], reasons: [number, string][]) => ({
  groups: [{ key: 'X', items: [row(1), row(2), row(3)] }], groupBy: 'warehouse', collapsed: new Set(),
  collapsedPlanning: [], selectable: false, compact: false, showCompany: false, dense: true,
  columns: new Set(['no', 'vessel']), sortBy: [], fillMap: {}, openCells: new Set(),
  conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
  watched: new Set(watched), watchReasons: new Map(reasons),
  sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
  warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
}) as unknown as TableCtx

describe('kolejka — powód przy gwiazdce', () => {
  it('obserwowany z powodem: etykieta z pełnym tekstem w title; bez powodu i nieobserwowany: brak', () => {
    const { container } = render(<MemoryRouter>
      <EnterpriseTable x={ctx([1, 2], [[1, 'Pilne dla klienta'], [3, 'stary powód']])} /></MemoryRouter>)
    const tags = container.querySelectorAll('td.kq-c-no .watch-reason-tag')
    expect(tags).toHaveLength(1)
    expect(tags[0].closest('tr')!.getAttribute('data-cid')).toBe('1')
    expect(tags[0].getAttribute('title')).toBe('watchReasonLabel: Pilne dla klienta')
    // czytnik ekranu słyszy etykietę pola, nie sam goły tekst
    expect(tags[0].textContent).toBe('watchReasonLabel: Pilne dla klienta')
  })

  it('podpowiedź pełnej gwiazdki = powód (nie „Obserwuj / przestań”); pusta gwiazdka — akcja', () => {
    const { container } = render(<MemoryRouter>
      <EnterpriseTable x={ctx([1, 2], [[1, 'TEST FV']])} /></MemoryRouter>)
    const star = (id: number) => container.querySelector(`tr[data-cid="${id}"] .kq-flag-btn`)!
    expect(star(1).getAttribute('title')).toBe('TEST FV')
    expect(star(1).getAttribute('aria-label')).toBe('watchToggle — TEST FV')     // akcja dalej słyszalna
    expect(star(2).getAttribute('title')).toBe('watchingNoReason')
    expect(star(3).getAttribute('title')).toBe('watchToggle')
  })
})

describe('szuflada — powód obserwacji w nagłówku', () => {
  const C = { id: 7, container_no: 'TRHU0003565', status: 'W_PORCIE', updated_at: 'x' } as unknown as Container
  const mount = (watchReason?: string) => render(
    <QueueDrawer c={C} fill={null} onPrev={null} onNext={null} onClose={() => {}} onStatus={null}
                 statusLabel="Status" onAvizo={null} onFull={() => {}} watchReason={watchReason} />)

  it('★ + powód', () => {
    const { container } = mount('Reklamacja')
    expect(container.querySelector('.kq-dr-row .watch-mark')).toBeTruthy()
    expect(screen.getByTitle('watchReasonLabel: Reklamacja')).toBeTruthy()
  })
  it('★ bez powodu = sama gwiazdka; nieobserwowany = nic', () => {
    const { container, unmount } = mount('')
    expect(screen.getByRole('img', { name: 'watchingNoReason' })).toBeTruthy()
    expect(container.querySelector('.watch-reason-tag')).toBeNull()
    unmount()
    expect(mount().container.querySelector('.watch-mark')).toBeNull()
  })
})

describe('mapa — gwiazdka nad statkiem', () => {
  const vessel = (id: number, watched: Vessel['watched']): Vessel => ({
    id, name: `V${id}`, mmsi: null, imo: null, lat: 10, lon: 20, sog: null, cog: 0, destination: '',
    ais_eta: null, last_seen: null, trail: [], companies: [], containers: 1, delayed: 0,
    drift_days: null, eta_alert: false, hours_to_dest: null, near_port: '', predicted_late: false,
    length_m: null, beam_m: null, has_photo: false, watched,
  })
  it('★ tylko przy statku z moim obserwowanym kontenerem; lista z powodami w podpowiedzi', () => {
    const mv = renderHook(() => useMapView()).result.current
    const layers = renderHook(() => useMapLayers()).result.current
    const { container } = render(<FlatMap mv={mv} layers={layers} grouped={new Map()} weather={{}}
      vessels={[vessel(1, [{ id: 5, container_no: 'TGBU6784203', reason: 'Pilne' },
                           { id: 6, container_no: 'MSDU0806613', reason: '' }]), vessel(2, [])]}
      active={null} setActive={() => {}} pinned={false} setPinned={() => {}}
      activeVessel={null} setActiveVessel={() => {}} replayOpen={false} replayIndex={0}
      portCounts={new Map()} containerPorts={[]} factories={[]} onFactoryClick={() => {}} />)
    const markers = container.querySelectorAll('.vessel-marker')
    expect(markers[0].querySelector('.vessel-watch-star')).toBeTruthy()
    expect(markers[1].querySelector('.vessel-watch-star')).toBeNull()
    const title = markers[0].querySelector(':scope > title')!.textContent
    expect(title).toContain('\n• TGBU6784203 — Pilne')
    expect(title).toContain('\n• MSDU0806613')
  })
})
