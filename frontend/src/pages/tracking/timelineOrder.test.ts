// Strażnik (2026-09-24, test T3): kolejność „Drogi kontenera" wg etapów procesu.
import { describe, expect, it } from 'vitest'
import { orderByStage } from './timelineOrder'
import type { TimelineEntry } from './ContainerTimeline'

const e = (kind: string, code: string, at: string | null): TimelineEntry =>
  ({ kind, code, title: code, location: '', at, estimated: false, source: 'x' })

describe('orderByStage', () => {
  it('statusy w swoim etapie procesu, nie wg chwili kliknięcia; cofnięcia poza drogą', () => {
    // chronologia z backendu jak na TRHU0003565: import, 2 kroki w przód, cofnięcie
    const chrono = [
      e('carrier', 'DEPART', '2026-09-10T08:00:00'),
      e('system', 'STATUS_W_TRANSPORCIE', '2026-09-24T09:21:00'),
      e('system', 'STATUS_ODPRAWA', '2026-09-24T09:46:00'),
      e('system', 'STATUS_AWIZOWANY', '2026-09-24T09:48:00'),
      e('system', 'STATUS_ODPRAWA', '2026-09-24T09:54:00'),
      e('planned', 'ETA', '2026-10-11T00:00:00'),
      e('planned', 'NOTIFY', '2026-10-14T00:00:00'),
      e('planned', 'DEMURRAGE', '2026-10-16T00:00:00'),
    ]
    expect(orderByStage(chrono).map(x => `${x.code}@${x.at?.slice(5, 16)}`)).toEqual([
      'DEPART@09-10T08:00', 'STATUS_W_TRANSPORCIE@09-24T09:21',
      'ETA@10-11T00:00',
      'STATUS_ODPRAWA@09-24T09:54',          // tylko ostatnie ustawienie
      'NOTIFY@10-14T00:00', 'DEMURRAGE@10-16T00:00',   // Awizowany zniknął — status cofnięty
    ])
  })

  it('bez statusów i dat nic nie gubi', () => {
    const list = [e('planned', 'ETA', null), e('order', 'PO_ETD', '2026-09-01T00:00:00')]
    expect(orderByStage(list).map(x => x.code)).toEqual(['PO_ETD', 'ETA'])
  })
})
