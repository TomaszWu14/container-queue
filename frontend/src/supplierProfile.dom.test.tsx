// @vitest-environment jsdom
// Karta dostawcy → kreator profilu dokumentów: 4 kroki, upload próbki, auto-propozycja ról,
// test na próbkach, zapis szkicu i aktywacja; logistyka tylko czyta.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

let USER: { role: string } = { role: 'admin' }
let PROFILE: Record<string, unknown>
let TEST_OK = true
const SAMPLE = { id: 7, filename: 'ci-1.pdf', created_at: null, last_test: {}, last_test_at: null }
const PREVIEW = {
  found: true, page: 1, headers: ['Pos', 'Art. Code', 'Goods', 'Pieces', 'Line total'],
  rows: [['1', 'GLV-1', 'Gloves', '1,000', '250.00']],
  detected: { no: 0, ref: 1, desc: 2, qty: 3, net: 4 }, pages: { ci: [1], pl: [2] },
}
const putMock = vi.fn((_p: string, body: Record<string, unknown>) => {
  PROFILE = { ...PROFILE, ...body, id: 1 }
  return Promise.resolve(PROFILE)
})
const uploadMock = vi.fn((_p: string, _f: File) => {
  PROFILE = { ...PROFILE, samples: [SAMPLE] }
  return Promise.resolve(SAMPLE)
})
const postMock = vi.fn((_p: string, _b: unknown) => Promise.resolve({
  ok: TEST_OK,
  results: [{ sample_id: 7, filename: 'ci-1.pdf', ok: TEST_OK, errors: TEST_OK ? [] : ['sum_mismatch'],
    pages: { ci: [1], pl: [2] }, ci_items: 2, pl_items: 1, matched: 1, sum_items: 450, total: 450,
    sum_ok: TEST_OK, items: [] }],
}))

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(path.includes('/preview') ? PREVIEW : PROFILE),
    put: (p: string, b: Record<string, unknown>) => putMock(p, b),
    post: (p: string, b: unknown) => postMock(p, b),
    upload: (p: string, f: File) => uploadMock(p, f),
    del: () => Promise.resolve(undefined),
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

import DocProfileCard from './pages/supplierProfile/DocProfileCard'
import { ToastProvider } from './feedback'

const EMPTY = {
  id: null, supplier_id: 3, status: 'draft', currency: '', doc_language: '', keywords: [],
  ci_map: {}, pl_map: {}, ref_kind: 'ours', split_marker: '', tol_amount_pct: 0.5, tol_qty_pct: 0,
  samples: [],
}

const lastPut = () => putMock.mock.calls[putMock.mock.calls.length - 1]?.[1]

function renderCard() {
  render(<ToastProvider><DocProfileCard supplierId={3} supplierName="Glove Co" /></ToastProvider>)
}

async function walkToTest() {
  renderCard()
  fireEvent.click(await screen.findByRole('button', { name: 'Skonfiguruj' }))
  // krok 1: dane
  fireEvent.change(screen.getByPlaceholderText('USD'), { target: { value: 'usd' } })
  const kw = screen.getByLabelText('Słowa kluczowe', { selector: 'input' })
  fireEvent.change(kw, { target: { value: 'GLOVE CO' } })
  fireEvent.keyDown(kw, { key: 'Enter' })
  fireEvent.click(screen.getByRole('button', { name: 'Dalej' }))
  await waitFor(() => expect(putMock).toHaveBeenCalledTimes(1))
  expect(putMock.mock.calls[0][1]).toMatchObject({ currency: 'USD', keywords: ['GLOVE CO'], status: 'draft' })
  // krok 2: upload próbki → podgląd tabeli
  const file = new File(['%PDF'], 'ci-1.pdf', { type: 'application/pdf' })
  fireEvent.change(await screen.findByTestId('sdp-upload'), { target: { files: [file] } })
  await waitFor(() => expect(uploadMock).toHaveBeenCalledWith('/api/suppliers/3/doc-profile/samples', file))
  expect(await screen.findByText('GLV-1')).toBeTruthy()
  expect(screen.getByText('CI str. 1 · PL str. 2')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Dalej' }))
  // krok 3: mapowanie — auto-propozycja ról z nagłówków, ręczna zmiana roli
  const refSelect = await screen.findByLabelText('Art. Code') as HTMLSelectElement
  await waitFor(() => expect(refSelect.value).toBe('ref'))
  expect((screen.getByLabelText('Pieces') as HTMLSelectElement).value).toBe('qty')
  fireEvent.change(screen.getByLabelText('Goods'), { target: { value: '' } })   // pomiń opis
  fireEvent.click(screen.getByRole('button', { name: 'Dalej' }))
  await waitFor(() => expect(putMock).toHaveBeenCalledTimes(3))
  const saved = putMock.mock.calls[2][1] as { ci_map: Record<string, string[]> }
  expect(saved.ci_map).toMatchObject({ ref: ['Art. Code'], qty: ['Pieces'], net: ['Line total'] })
  expect(saved.ci_map.desc).toBeUndefined()
  // krok 4: test
  fireEvent.click(await screen.findByRole('button', { name: 'Testuj na wszystkich próbkach' }))
  await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/suppliers/3/doc-profile/test',
    expect.objectContaining({ ci_map: saved.ci_map })))
}

afterEach(cleanup)
beforeEach(() => {
  USER = { role: 'admin' }
  PROFILE = { ...EMPTY }
  TEST_OK = true
  putMock.mockClear(); uploadMock.mockClear(); postMock.mockClear()
})

// długi przepływ 4 kroków — pod obciążeniem pełnego zestawu 5 s domyślnego limitu nie starcza
describe('profil dokumentów dostawcy — kreator', { timeout: 30000 }, () => {
  it('4 kroki → test OK → aktywacja', async () => {
    await walkToTest()
    expect(await screen.findByText('Wszystkie próbki przechodzą — profil gotowy do aktywacji.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Aktywuj profil' }))
    await waitFor(() => expect(lastPut()).toMatchObject({ status: 'active' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('aktywny')).toBeTruthy()
  })

  it('zapis jako szkic', async () => {
    await walkToTest()
    fireEvent.click(await screen.findByRole('button', { name: 'Zapisz jako szkic' }))
    await waitFor(() => expect(lastPut()).toMatchObject({ status: 'draft' }))
  })

  it('aktywacja z niezdanym testem wymaga potwierdzenia', async () => {
    TEST_OK = false
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await walkToTest()
    expect(await screen.findByText(/suma pozycji ≠ suma faktury/)).toBeTruthy()
    const calls = putMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: 'Aktywuj profil' }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(putMock.mock.calls.length).toBe(calls)
    confirmSpy.mockRestore()
  })

  it('logistyka widzi profil bez przycisku edycji', async () => {
    USER = { role: 'logistics' }
    PROFILE = { ...EMPTY, id: 1, status: 'active', currency: 'USD', keywords: ['GLOVE CO'],
      ci_map: { ref: ['Art. Code'], qty: ['Pieces'] } }
    renderCard()
    expect(await screen.findByText('CI: 2 pól')).toBeTruthy()
    expect(screen.getByText('GLOVE CO')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Edytuj' })).toBeNull()
  })
})
