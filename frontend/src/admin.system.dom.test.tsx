// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const system = {
  version: '1.2.3', built_at: '2026-09-18T10:00:00Z', uptime_s: 90061,
  database: 'postgresql', run_background_jobs: true,
  last_tracking_sync: '2026-09-18T09:00:00Z', last_ais_seen: null,
  last_po_import: null, last_container_created: null,
  client_errors_24h: 7, uploads_size_mb: 123,
  backup_verify: null,
}

const post = vi.fn(async (path: string, _body?: unknown) => {
  if (path.includes('verify-backup'))
    return { status: 'ok', detail: 'dump czytelny', started_at: '2026-09-18T11:00:00Z', tables: 42 }
  return {}
})

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(path.includes('/admin/system') ? system : []),
    post: (path: string, body: unknown) => post(path, body),
  },
  errorMessage: (e: unknown) => String(e),
}))

afterEach(cleanup)

import SystemTab from './pages/admin/SystemTab'

describe('Zakładka System', () => {
  it('renderuje metryki i przycisk weryfikacji backupu woła endpoint', async () => {
    render(<SystemTab />)
    // metryki z mocka
    await screen.findByText(/1\.2\.3/)
    expect(screen.getByText('postgresql')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
    expect(screen.getByText('123 MB')).toBeTruthy()
    expect(screen.getByText('1d 1h 1m')).toBeTruthy()
    expect(screen.getByText('włączone')).toBeTruthy()
    // brak wyniku weryfikacji na start
    expect(screen.getByText('Brak wyników weryfikacji.')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Uruchom weryfikację backupu' }))
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/admin/system/verify-backup', {}))
    await screen.findByText(/dump czytelny/)
  })
})
