// @vitest-environment jsdom
// Strażnik monitora serwera (2026-09-24): paski zajętości z progami, dyski, baza,
// wykres dopiero od 2 próbek; brak danych poza Linuksem (null) nie wywala panelu.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet }, errorMessage: String }))

import MonitorPanel, { type Monitor } from './MonitorPanel'

afterEach(cleanup)

const BASE: Monitor = {
  cpu_percent: 95, cpu_count: 4, load_avg: [0.5, 0.4, 0.3],
  memory: { total_mb: 8192, used_mb: 4096, percent: 50 }, container_memory: { used_mb: 300, limit_mb: null },
  process_rss_mb: 180, threads: 12, history: [],
  disks: [{ label: 'system', path: '/', total_gb: 100, used_gb: 75, free_gb: 25, percent: 75 }],
  database: { engine: 'postgresql', size_mb: 42, connections: 3, tables: [{ name: 'containers', size_mb: 5, rows: 1200 }] },
}

describe('MonitorPanel', () => {
  it('pokazuje zajętość z kolorem progu, dyski i największe tabele', async () => {
    apiGet.mockResolvedValue(BASE)
    render(<MonitorPanel />)
    const cpu = await screen.findByRole('meter', { name: 'monCpu' })
    expect(cpu.getAttribute('aria-valuenow')).toBe('95')
    expect((cpu.firstChild as HTMLElement).style.background).toBe('var(--danger)')
    expect(screen.getByRole('meter', { name: 'monDisk: system' }).getAttribute('aria-valuenow')).toBe('75')
    expect(screen.getByText('containers')).toBeTruthy()
    expect(screen.getByText('monNoHistory')).toBeTruthy()   // < 2 próbek = bez wykresu
  })

  it('brak pomiarów (Windows/dev) = kreski, bez błędu; wykres od 2 próbek', async () => {
    apiGet.mockResolvedValue({ ...BASE, cpu_percent: null, memory: null, container_memory: null,
      history: [{ at: 'a', cpu: 10, mem: 20, rss_mb: 1 }, { at: 'b', cpu: 30, mem: 40, rss_mb: 1 }] })
    render(<MonitorPanel />)
    expect((await screen.findByRole('meter', { name: 'monCpu' })).getAttribute('aria-valuenow')).toBeNull()
    expect(screen.getByRole('img', { name: 'monHistory' })).toBeTruthy()
  })

  it('rozbicie RAM i największe procesy; podpowiedź montażu, gdy widać tylko kontener', async () => {
    apiGet.mockResolvedValue({ ...BASE,
      memory: { ...BASE.memory!, breakdown: { apps_mb: 1500, shared_mb: 64, cache_mb: 900, kernel_mb: 120,
        swap_used_mb: 0, swap_total_mb: 0 } },
      processes: { scope: 'container', items: [
        { name: 'php-fpm', container: 'abc123def456', count: 9, private_mb: 420, shared_mb: 0 }] } })
    render(<MonitorPanel />)
    expect(await screen.findByText('php-fpm')).toBeTruthy()
    expect(screen.getByText('abc123def456')).toBeTruthy()
    expect(screen.getByText('1.5 GB')).toBeTruthy()
    expect(screen.getByText('monProcScopeHint')).toBeTruthy()
  })
})
