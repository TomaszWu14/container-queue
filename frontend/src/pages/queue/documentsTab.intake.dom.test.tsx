// @vitest-environment jsdom
// Spec 2026-10-06 decyzja 1: w szufladzie kolejki nowe pliki wchodzą tylko przez poczekalnię
// („Dodaj dokumenty”) — bez osobnego pola wgrywania z typem dokumentu.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (k: string) => k, useLocale: () => 'pl-PL' }))
vi.mock('../../App', () => ({ useUser: () => ({ role: 'logistics' }) }))
const upload = vi.fn()
vi.mock('../../api', () => ({
  api: { get: () => Promise.resolve([]), upload: (...a: unknown[]) => upload(...a) },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => (e as Error).message,
}))

import { DocumentsTab } from './DrawerTabs'

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('DocumentsTab — jedno wejście', () => {
  it('jest „Dodaj dokumenty”, nie ma bezpośredniego wgrywania z typem', async () => {
    const d = { files: [], messages: [], costs: [], loadFiles: vi.fn(), loadMessages: vi.fn() }
    render(<DocumentsTab containerId={9} d={d as never} />)
    expect(await screen.findByRole('region', { name: 'inqAdd' })).toBeTruthy()
    expect(screen.queryByLabelText('docType')).toBeNull()
    expect(screen.queryByLabelText('upload')).toBeNull()
  })
})
