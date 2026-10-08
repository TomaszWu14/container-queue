// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Container } from './types'

const { apiPost, apiPatch, apiGet } = vi.hoisted(() => ({
  apiPost: vi.fn(() => Promise.resolve({ id: 1 })),
  apiPatch: vi.fn(() => Promise.resolve({ id: 1 })),
  apiGet: vi.fn((path: string) => {
    if (path.startsWith('/api/customs/board')) {
      return Promise.resolve([
        { id: 1, container_no: 'CONT1', customs_status: 'ODPRAWIONY', missing_documents: [] },
      ])
    }
    return Promise.resolve([])
  }),
}))

vi.mock('./api', () => ({
  api: { get: apiGet, post: apiPost, put: vi.fn(), patch: apiPatch },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./i18n', async () => ({
  LangContext: (await import('react')).createContext({ lang: 'pl', setLang: () => {} }),
  useT: () => (key: string) => ({
    changeStatus: 'Zmień status', statusNote: 'Komentarz', status: 'Status',
    cancel: 'Anuluj', save: 'Zapisz', confirm: 'Potwierdź',
    backwardStatusTitle: 'Cofasz status', backwardStatusWarning: 'To nietypowe. Kontynuować?',
    st_ZAPOWIEDZIANY: 'Zapowiedziany', st_W_TRANSPORCIE: 'W transporcie', st_W_PORCIE: 'W porcie',
    st_ODPRAWA: 'Odprawa', st_AWIZOWANY: 'Awizowany', st_W_DOSTAWIE: 'W dostawie',
    st_DOSTARCZONY: 'Dostarczony', st_ZREALIZOWANY: 'Zrealizowany',
    customsPanel: 'Odprawa celna', customsAgency: 'Agencja celna', notes: 'Notatki',
    updateCustoms: 'Aktualizuj', customsModule: 'Moduł celny', customsAssign: 'Przypisz',
    customsIntroAgency: '', customsIntroLogistics: '', allOrders: 'Wszystkie', onlyIncomplete: 'Braki',
    customsEmpty: 'Brak danych', containerNo: 'Kontener', company: 'Firma', eta: 'ETA',
    customsAgent: 'Agent', customs: 'Celna', caseStatus: 'Status sprawy', customsManage: 'Zarządzaj',
    toastStatusChanged: 'Status zmieniony',
    cs_BRAK: 'Brak', cs_DOKUMENTY_KOMPLETNE: 'Dokumenty kompletne', cs_ZLECONA: 'Zlecona',
    cs_DRAFT_WYSLANY: 'Draft wysłany', cs_DRAFT_POTWIERDZONY: 'Draft potwierdzony',
    cs_ODPRAWIONY: 'Odprawiony', cs_REWIZJA: 'Rewizja',
  } as Record<string, string>)[key] ?? key,
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'logistics' }) }))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import { StatusModal } from './components'
import CustomsPage from './pages/CustomsPage'

const baseContainer = { id: 1, container_no: 'CONT1', status: 'W_PORCIE' } as unknown as Container

afterEach(() => { cleanup(); apiPost.mockClear(); apiPatch.mockClear(); apiGet.mockClear() })

describe('StatusModal — guardrail cofania statusu', () => {
  it('ruch w przód: brak modala ostrzeżenia, request idzie od razu', async () => {
    const onSaved = vi.fn()
    render(<StatusModal container={baseContainer} warehouseRole={false} onSaved={onSaved} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ODPRAWA' } })
    fireEvent.click(screen.getByText('Zapisz'))
    expect(screen.queryByText('Cofasz status')).toBeNull()
    expect(apiPost).toHaveBeenCalledWith('/api/containers/1/status', { status: 'ODPRAWA', note: '' })
  })

  it('ruch wstecz: pokazuje modal ostrzeżenia, anuluj = brak requestu', async () => {
    render(<StatusModal container={baseContainer} warehouseRole={false} onSaved={vi.fn()} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ZAPOWIEDZIANY' } })
    fireEvent.click(screen.getByText('Zapisz'))
    expect(await screen.findByText('Cofasz status')).toBeTruthy()
    expect(apiPost).not.toHaveBeenCalled()
    const cancelButtons = screen.getAllByText('Anuluj')
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('ruch wstecz: potwierdź wysyła request z notatką', async () => {
    const onSaved = vi.fn()
    render(<StatusModal container={baseContainer} warehouseRole={false} onSaved={onSaved} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ZAPOWIEDZIANY' } })
    fireEvent.click(screen.getByText('Zapisz'))
    await screen.findByText('Cofasz status')
    // D2: bez powodu cofnięcia nie da się potwierdzić
    expect((screen.getByText('Potwierdź') as HTMLButtonElement).disabled).toBe(true)
    const noteInputs = screen.getAllByLabelText('backwardStatusNote')
    fireEvent.change(noteInputs[noteInputs.length - 1], { target: { value: 'pomyłka' } })
    fireEvent.click(screen.getByText('Potwierdź'))
    expect(apiPost).toHaveBeenCalledWith('/api/containers/1/status', { status: 'ZAPOWIEDZIANY', note: 'pomyłka' })
  })
})

describe('CustomsPage (tabela modułu celnego) — guardrail cofania odprawy', () => {
  it('cofnięcie z ODPRAWIONY w tabeli: pokazuje modal, anuluj = brak requestu, select wraca do poprzedniej wartości', async () => {
    render(<CustomsPage />)
    const select = await screen.findByDisplayValue('Odprawiony') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'REWIZJA' } })
    expect(await screen.findByText('Cofasz status')).toBeTruthy()
    expect(apiPost).not.toHaveBeenCalled()
    const cancelButtons = screen.getAllByText('Anuluj')
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
    expect(apiPost).not.toHaveBeenCalled()
    expect(select.value).toBe('ODPRAWIONY')
  })
})
