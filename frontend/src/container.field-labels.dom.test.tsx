// @vitest-environment jsdom
// Etykiety pól na karcie kontenera (audyt UI A29/C33 — UX-001, UX-006): dane kierowcy, odprawa celna
// i portal klienta mają widoczną etykietę NAD polem (Field), a nie sam placeholder, który znika po
// wpisaniu i ucinał „Imię i nazwisko kierowcy”. Dwa pola „Uwagi” odprawy są rozróżnione i niezależne.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Container } from './types'

const { role } = vi.hoisted(() => ({ role: { current: 'admin' } }))
vi.mock('./api', () => ({
  api: {
    get: vi.fn((url: string) => Promise.resolve(url.endsWith('/driver-sms')
      ? { configured: false, messages: [] } : [])),
    post: vi.fn(), patch: vi.fn(), put: vi.fn(),
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ id: 1, role: role.current }) }))

import { CustomsAgencyPanel, DriverPanel } from './collaboration'
import { CustomerPortalPanel } from './pages/ContainerSidePanels'

const container = {
  id: 7, container_no: 'MSKU1234565', status: 'W_PORCIE', customs_status: 'ZLECONA', company_id: 1,
  customs_agency_id: 3, customs_agency_name: 'Agencja', customs_agent_name: '', customs_agent_phone: '',
  customs_agent_email: '', driver_name: '', driver_id_no: '', truck_no: '', trailer_no: '', driver_phone: '',
  customer_id: null,
} as unknown as Container

afterEach(() => { cleanup(); role.current = 'admin' })

// pole ma widoczny podpis w <label class="field"> i nie używa placeholdera jako etykiety
function labelled(root: HTMLElement) {
  return [...root.querySelectorAll('input:not([type=checkbox]):not([type=file]), select')].map(el => {
    const field = el.closest('label.field')
    return {
      label: field?.querySelector('.field-label')?.textContent ?? null,
      placeholderAsLabel: !!el.getAttribute('placeholder')
        && el.getAttribute('placeholder') === field?.querySelector('.field-label')?.textContent,
    }
  })
}

describe('karta kontenera — etykiety pól', () => {
  it('dane kierowcy: każde pole z widoczną etykietą (bez placeholdera-etykiety)', () => {
    const { container: root } = render(<DriverPanel container={container} onSaved={() => {}} />)
    const fields = labelled(root)
    expect(fields.map(f => f.label)).toEqual(
      ['Imię i nazwisko kierowcy', 'Nr dowodu osobistego', 'Nr ciągnika', 'Nr naczepy', 'Nr telefonu'])
    expect(fields.some(f => f.placeholderAsLabel)).toBe(false)
  })

  it('odprawa (logistyka): etykiety pól, dwa rozróżnione i niezależne pola uwag', async () => {
    const { container: root } = render(<CustomsAgencyPanel container={container} onSaved={() => {}} />)
    await waitFor(() => expect(root.querySelectorAll('select').length).toBe(2))
    expect(labelled(root).map(f => f.label)).toEqual(
      ['Agencja celna', 'Uwaga do zlecenia agencji', 'Status odprawy', 'Komentarz do zmiany statusu'])
    const assignNote = screen.getByLabelText('Uwaga do zlecenia agencji') as HTMLInputElement
    const statusNote = screen.getByLabelText('Komentarz do zmiany statusu') as HTMLInputElement
    fireEvent.change(assignNote, { target: { value: 'pilne' } })
    expect(statusNote.value).toBe('')
    // A27: przycisk statusu odprawy nazwany inaczej niż „Zmień status” kontenera w nagłówku karty
    expect(screen.getByRole('button', { name: 'Zmień status odprawy' })).toBeTruthy()
  })

  it('odprawa (agencja): agent, telefon i e-mail z etykietami', () => {
    role.current = 'customs'
    const { container: root } = render(<CustomsAgencyPanel container={container} onSaved={() => {}} />)
    expect(labelled(root).map(f => f.label).slice(0, 3)).toEqual(['Agent celny', 'Telefon agenta', 'E-mail agenta'])
  })

  it('portal klienta: wybór i nowy klient z etykietami', () => {
    const { container: root } = render(<CustomerPortalPanel container={container} onSaved={() => {}} />)
    expect(labelled(root).map(f => f.label)).toEqual(['Klient', 'Nowy klient (nazwa)'])
  })
})
