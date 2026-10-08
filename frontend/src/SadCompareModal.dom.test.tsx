// @vitest-environment jsdom
// Strażnik (2026-09-30, spec agencja-draft-sad PR 2): okno porównania draftu SAD z fakturami.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import type { SadComparison, SadDraft } from './types'

const post = vi.fn()
vi.mock('./api', () => ({ api: { post: (p: string, b: unknown) => post(p, b) }, errorMessage: String }))
vi.mock('./i18n', async orig => ({ ...(await orig<typeof import('./i18n')>()), useT: () => (k: string) => k }))

import { SadCompareModal } from './SadCompareModal'

const f = (ours: string | null, sad: string | null, ok: boolean | null, diff_pct: number | null = null) =>
  ({ ours, sad, ok, diff_pct })
const RESULT: SadComparison = {
  draft_id: 5, version: 2, pages: 2, at: '2026-09-30T10:00:00', error: null,
  no_cn: ['C3'], unread: [{ item: 1, field: 'net_mass' }],
  tolerances: { amount_pct: 0.5, qty_pct: 0, mass_abs_kg: 1 },
  summary: { groups: 3, ok: 1, diff: 2, manual: 0, all_ok: false },
  header: [
    { field: 'invoices', ours: 'T-1, T-3', sad: null, ok: false, diff_pct: null, detail: 'T-3' },
    { field: 'total', ours: '1205.5', sad: '1205.5', ok: true, diff_pct: 0, detail: '' }],
  groups: [
    { cn: '90183900', status: 'diff', refs: ['NL753'], sad_items: [1], suppl_unit: '',
      value: f('900', '950', false, 5.56), net_mass: f('12.5', '12.5', true, 0), suppl_qty: null },
    { cn: '84713000', status: 'missing_in_sad', refs: ['Z9'], sad_items: [], suppl_unit: '',
      value: f('10', null, null), net_mass: f('1', null, null), suppl_qty: null }],
}
const draft = { id: 5, version: 2 } as SadDraft

afterEach(() => { cleanup(); post.mockReset() })

describe('SadCompareModal', () => {
  it('porównuje wersję: grupy CN, nagłówek, strony PDF obok', async () => {
    post.mockResolvedValue(RESULT)
    const onCompared = vi.fn()
    render(<SadCompareModal batchId={7} draft={draft} onClose={() => {}} onCompared={onCompared} />)
    expect(await screen.findByText('90183900')).toBeTruthy()
    expect(post).toHaveBeenCalledWith('/api/invoice-batches/7/sad-drafts/5/compare', {})
    expect(screen.getByText('sadStatus_diff')).toBeTruthy()
    expect(screen.getByText('sadStatus_missing_in_sad')).toBeTruthy()
    expect(screen.getAllByRole('img', { name: /sadPage/ })).toHaveLength(2)
    expect(screen.getByRole('img', { name: 'sadVerdictBad' })).toBeTruthy()
    expect(onCompared).toHaveBeenCalled()
  })

  it('PDF bez tekstu: komunikat zamiast zgadywania', async () => {
    post.mockResolvedValue({ ...RESULT, error: 'no_text', groups: [] })
    render(<SadCompareModal batchId={7} draft={draft} onClose={() => {}} />)
    expect(await screen.findByText('sadErr_no_text')).toBeTruthy()
  })
})
