// @vitest-environment jsdom
// Kafelki dokumentów dostawy (spec 2026-10-01): nagłówek N/7 · brakuje, klik w kafelek z plikiem → otwarcie.
// Spec 2026-10-06 decyzja 1: kafelki nie wgrywają (jedyne wejście to poczekalnia „Dodaj dokumenty”).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
const get = vi.fn()
const upload = vi.fn()
const downloadFile = vi.fn()
vi.mock('./api', () => ({
  api: { get: (p: string) => get(p), upload: (...a: unknown[]) => upload(...a) },
  downloadFile: (...a: unknown[]) => downloadFile(...a),
  errorMessage: (e: unknown) => String(e),
}))

import DocumentTiles, { DocumentTilesCompact } from './DocumentTiles'
import type { TilesResult } from './DocumentTiles'

const codes = ['PI', 'CI', 'PL', 'BL', 'SAD_DRAFT', 'SAD_PZ', 'SAD_PW'] as const
const RESULT: TilesResult = {
  loaded: 1, total: 7, missing: ['CI', 'BL'],
  tiles: codes.map(code => ({
    code, required: code === 'CI' || code === 'BL',
    state: code === 'PI' ? 'ok' : 'none',
    files: code === 'PI' ? [{ source: 'attachment', id: 9, name: 'pi.pdf', filename: 'pi.pdf',
                              created_at: '2026-10-01', url: '/api/attachments/9/download' }] : [],
  })),
} as TilesResult

afterEach(() => { cleanup(); vi.clearAllMocks() })

const mount = () => {
  get.mockResolvedValue(RESULT)
  downloadFile.mockResolvedValue(undefined)
  return render(<DocumentTiles containerId={7} />)
}
const drop = (el: Element) => fireEvent.drop(el.closest('.dt-tile')!, {
  dataTransfer: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] },
})

describe('DocumentTiles', () => {
  it('nagłówek: załadowane i brakujące wymagane', async () => {
    mount()
    expect((await screen.findByRole('heading')).textContent).toContain('1/7')
    expect(screen.getByRole('heading').textContent).toContain('dtMissing: dtName_CI, dtName_BL')
  })

  it('kafelki nie wgrywają: pusty kafelek wyłączony, upuszczenie pliku nic nie wysyła', async () => {
    const { container } = mount()
    const bl = (await screen.findByText('dtName_BL')).closest('button')!
    expect(bl.disabled).toBe(true)
    drop(bl)
    expect(container.querySelector('input[type="file"]')).toBeNull()
    expect(upload).not.toHaveBeenCalled()
  })

  it('klik w kafelek z plikiem otwiera najnowszy plik', async () => {
    mount()
    fireEvent.click(await screen.findByText('pi.pdf'))
    expect(downloadFile).toHaveBeenCalledWith('/api/attachments/9/download', 'pi.pdf')
  })

  it('kompakt: kwadracik ze skrótem, brak wymagany oznaczony', () => {
    const { container } = render(<DocumentTilesCompact result={RESULT} />)
    expect([...container.querySelectorAll('.dt-sq')].map(e => e.textContent)).toEqual(
      ['PI', 'CI', 'PL', 'BL', 'SD', 'PZ', 'PW'])
    expect(container.querySelector('.dt-sq.dt-CI')?.className).toContain('miss')
    expect(container.querySelector('.dt-sq.dt-PI')?.className).toContain('st-ok')
  })

  it('kompakt w szufladzie: klik przenosi do zakładki Dokumenty', () => {
    const onOpen = vi.fn()
    render(<DocumentTilesCompact result={RESULT} onOpen={onOpen} />)
    const btn = screen.getByRole('button')
    expect(btn.title).toContain('1/7')
    fireEvent.click(btn)
    expect(onOpen).toHaveBeenCalled()
  })
})
