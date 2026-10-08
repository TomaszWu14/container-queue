// @vitest-environment jsdom
// Import SAD (podglądy WinSAD): wyniki per plik (nagłówek, pozycje, uwagi walidacji), błąd pliku
// bez danych, raport Excel wysyłany z tymi samymi plikami.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
const { upload, downloadFile } = vi.hoisted(() => ({ upload: vi.fn(), downloadFile: vi.fn() }))
vi.mock('../api', () => ({
  api: { upload: (p: string, f: File[], field: string) => upload(p, f, field) },
  downloadFile: (p: string, name: string, form: FormData) => downloadFile(p, name, form),
  errorMessage: String,
}))

import SadImportPage, { type SadFileResult } from './SadImportPage'

const fee = (due: string) => ({ podstawa: '1000', stawka: '12', kwota_nalezna: due, metoda: 'R' })
const OK_FILE: SadFileResult = {
  plik: 'SAD7100003.pdf', ok: true, blad: null,
  zgloszenie: {
    numer: '7100003', stan_ais: 'W przygotowaniu', data_zgloszenia: '2026-09-24',
    data_wydruku: '2026-09-23T16:05:00', lrn: '26SEPDEMO3', nadawca: 'DEMO MEDICAL', odbiorca: 'ACME',
    kontenery: ['TSTU3000039'], wartosc_faktur: '20382.9', waluta: 'USD', kurs: '3.7306',
    liczba_pozycji: 2, liczba_opakowan: 10, masa_brutto: '1000', suma_cla: '0', suma_vat: '7211',
    status: 'WARN',
  },
  pozycje: [1, 2].map(nr => ({
    nr, opis: 'RĘKAWICE', cn: nr === 1 ? '40151900' : '63079098', taric: '00',
    wartosc_fakturowa: '10000.5', masa_netto: '500', ilosc_uzup: null, faktury: ['INV1'], proformy: [],
    a00: fee('0'), b00: fee('3871'), kwota_ogolem: '3871' })),
  wyniki: [
    { poziom: 'pozycja', pozycja: 1, regula: 'kod CN: 8 cyfr', oczekiwane: '8 cyfr', odczytane: '40151900', status: 'OK' },
    { poziom: 'zgłoszenie', pozycja: null, regula: 'stan AIS: zgłoszenie przyjęte / zwolnione',
      oczekiwane: 'przyjęte / zwolnione', odczytane: 'W przygotowaniu', status: 'WARN' },
  ],
}
const BAD_FILE: SadFileResult = {
  plik: 'notatka.pdf', ok: false, blad: 'To nie jest plik PDF.', zgloszenie: null, pozycje: [], wyniki: [],
}

const pdf = (name: string) => new File(['%PDF-1.4'], name, { type: 'application/pdf' })
const pick = (...files: File[]) =>
  fireEvent.change(screen.getByLabelText('sadImpFiles'), { target: { files } })

afterEach(() => { cleanup(); upload.mockReset(); downloadFile.mockReset() })

describe('SadImportPage', () => {
  it('Sprawdź: karta SAD z nagłówkiem, pozycjami i uwagami; błędny plik z komunikatem', async () => {
    upload.mockResolvedValue({ files: [OK_FILE, BAD_FILE] })
    render(<SadImportPage />)
    const check = screen.getByRole('button', { name: 'sadImpCheck' }) as HTMLButtonElement
    expect(check.disabled).toBe(true)                       // bez plików
    const files = [pdf('SAD7100003.pdf'), pdf('notatka.pdf')]
    pick(...files)
    fireEvent.click(check)
    await waitFor(() => expect(upload).toHaveBeenCalledWith('/api/sad-import/check', files, 'files'))

    const card = await screen.findByRole('region', { name: 'SAD7100003.pdf' })
    const text = card.textContent!.replace(/\s/g, ' ')              // spacja grupująca = NBSP
    for (const part of ['sadImpLrn26SEPDEMO3', 'sadImpContainersTSTU3000039',
      'sadImpInvoiceValue20 382,90 USD', 'sadImpDuty0 PLN', 'sadImpVat7211 PLN', 'sadImpDate24.09.2026'])
      expect(text).toContain(part)
    expect(within(card).getAllByText('sadImpStatus_WARN').length).toBeGreaterThan(0)
    expect(within(card).getByText('63079098')).toBeTruthy()          // pozycja 2
    expect(within(card).getAllByText('3871')).toHaveLength(2)        // B00 należna obu pozycji
    // domyślnie tylko uwagi; przełącznik pokazuje też reguły OK
    expect(within(card).getByText('stan AIS: zgłoszenie przyjęte / zwolnione')).toBeTruthy()
    expect(within(card).queryByText('kod CN: 8 cyfr')).toBeNull()
    fireEvent.click(within(card).getByRole('button', { name: 'sadImpShowAll' }))
    expect(within(card).getByText('kod CN: 8 cyfr')).toBeTruthy()

    const bad = screen.getByRole('region', { name: 'notatka.pdf' })
    expect(within(bad).getByText('To nie jest plik PDF.')).toBeTruthy()
    expect(within(bad).getByText('sadImpFileError')).toBeTruthy()
    expect(within(bad).queryByRole('table')).toBeNull()
  })

  it('błąd całego żądania pokazuje komunikat', async () => {
    upload.mockRejectedValue('Naraz można sprawdzić najwyżej 20 plików.')
    render(<SadImportPage />)
    pick(pdf('a.pdf'))
    fireEvent.click(screen.getByRole('button', { name: 'sadImpCheck' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Naraz można sprawdzić najwyżej 20 plików.')
  })

  it('ponad 20 plików: przyciski wyłączone i komunikat', () => {
    render(<SadImportPage />)
    pick(...Array.from({ length: 21 }, (_, i) => pdf(`s${i}.pdf`)))
    expect(screen.getByText('sadImpTooMany')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'sadImpExcel' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('Pobierz Excel: POST na /report z tymi samymi plikami', async () => {
    downloadFile.mockResolvedValue(undefined)
    render(<SadImportPage />)
    const files = [pdf('SAD1.pdf'), pdf('SAD2.pdf')]
    pick(...files)
    fireEvent.click(screen.getByRole('button', { name: 'sadImpExcel' }))
    await waitFor(() => expect(downloadFile).toHaveBeenCalledTimes(1))
    const [path, name, form] = downloadFile.mock.calls[0] as [string, string, FormData]
    expect(path).toBe('/api/sad-import/report')
    expect(name).toMatch(/^sad_raport_\d{4}-\d{2}-\d{2}\.xlsx$/)
    expect(form.getAll('files').map(f => (f as File).name)).toEqual(['SAD1.pdf', 'SAD2.pdf'])
  })
})
