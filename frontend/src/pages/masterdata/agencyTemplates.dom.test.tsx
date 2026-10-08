// @vitest-environment jsdom
// Wzory plików dla agencji: układ kolumn widoczny (litera kolumny Excela, źródło, wymagana,
// przykład), wymagana bez źródła podświetlona, edycja → PUT z nową kolejnością.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (k: string) => k }))
const get = vi.fn()
const put = vi.fn()
vi.mock('../../api', () => ({
  api: { get: (p: string) => get(p), put: (p: string, b: unknown) => put(p, b), upload: vi.fn() },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e),
}))

import AgencyTemplatesTab, { colLetter } from './AgencyTemplatesTab'

const col = (name: string, source = 'empty', over = {}) =>
  ({ name, source, value: '', required: false, note: '', example: '', ...over })
const payload = {
  sources: { ref: 'REF materiału', empty: 'Puste', const: 'Stała wartość' },
  templates: [{ key: 'winsad_symbole', name: 'Symbole WinSAD', description: 'opis', sheet: 'Arkusz1',
                has_sample: false,
                columns: [col('Symbol', 'ref', { required: true, example: '145851' }),
                          col('KodKrajuPoch', 'empty', { required: true }), col('Militarny', 'const', { value: 'N' })] }],
}

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('AgencyTemplatesTab', () => {
  it('litery kolumn jak w Excelu', () => {
    expect([colLetter(0), colLetter(25), colLetter(26), colLetter(43)]).toEqual(['A', 'Z', 'AA', 'AR'])
  })

  it('pokazuje układ i edytuje: zmiana kolejności + zapis', async () => {
    get.mockResolvedValue(payload)
    put.mockImplementation((_p: string, b: { columns: unknown[] }) =>
      Promise.resolve({ ...payload.templates[0], columns: b.columns }))
    render(<AgencyTemplatesTab />)
    const name = await screen.findByLabelText('atplName A') as HTMLInputElement
    expect(name.value).toBe('Symbol')
    expect(screen.getByText('145851')).toBeTruthy()
    // wymagana bez źródła danych — wiersz oznaczony do uzupełnienia
    expect((screen.getByLabelText('atplName B') as HTMLElement).closest('tr')!.className).toContain('atpl-gap')
    expect((screen.getByLabelText('atplValue C') as HTMLInputElement).value).toBe('N')

    fireEvent.click(screen.getAllByLabelText('atplDown')[0])
    fireEvent.click(screen.getByText('save'))
    await waitFor(() => expect(put).toHaveBeenCalled())
    const [path, body] = put.mock.calls[0]
    expect(path).toBe('/api/agency-templates/winsad_symbole')
    expect(body.columns.map((c: { name: string }) => c.name)).toEqual(['KodKrajuPoch', 'Symbol', 'Militarny'])
    expect(await screen.findByText('atplSaved')).toBeTruthy()
  })
})
