// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import {
  MemoryRouter, Route, Routes, useLocation, useNavigate, useNavigationType,
} from 'react-router-dom'

import { useQueryParam, validDateRange } from './urlState'

afterEach(cleanup)

let renders = 0

function Probe() {
  renders++
  const [f, setF] = useQueryParam('f')
  const navType = useNavigationType()
  const navigate = useNavigate()
  const loc = useLocation()
  return (
    <div>
      <span data-testid="val">{f || '(empty)'}</span>
      <span data-testid="search">{loc.search || '(none)'}</span>
      <span data-testid="nav">{navType}</span>
      <button onClick={() => setF('x')}>set</button>
      <button onClick={() => setF('x')}>setSame</button>
      <button onClick={() => setF('')}>clear</button>
      <button onClick={() => navigate('/other')}>go</button>
    </div>
  )
}

function mount(initial = '/start') {
  renders = 0
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes><Route path="*" element={<Probe />} /></Routes>
    </MemoryRouter>,
  )
}

describe('useQueryParam — round-trip i czyste parametry', () => {
  it('brak parametru → wartość domyślna (pusta)', () => {
    mount('/start')
    expect(screen.getByTestId('val').textContent).toBe('(empty)')
    expect(screen.getByTestId('search').textContent).toBe('(none)')
  })

  it('zapis → odczyt (round-trip) i parametr w URL', () => {
    mount('/start')
    fireEvent.click(screen.getByText('set'))
    expect(screen.getByTestId('val').textContent).toBe('x')
    expect(screen.getByTestId('search').textContent).toBe('?f=x')
  })

  it('wartość pusta usuwa parametr z URL (tylko odchylenia)', () => {
    mount('/start?f=x')
    expect(screen.getByTestId('val').textContent).toBe('x')
    fireEvent.click(screen.getByText('clear'))
    expect(screen.getByTestId('search').textContent).toBe('(none)')
  })

  it('ustawienie tej samej wartości nie powoduje pętli aktualizacji', () => {
    mount('/start')
    fireEvent.click(screen.getByText('set'))
    fireEvent.click(screen.getByText('setSame'))
    fireEvent.click(screen.getByText('setSame'))
    expect(screen.getByTestId('val').textContent).toBe('x')
    expect(renders).toBeLessThan(20)  // brak runaway re-renderów
  })
})

describe('historia: zmiana filtra = replace, zmiana widoku = push', () => {
  it('zmiana filtra używa replaceState (nie zaśmieca historii)', () => {
    mount('/start')
    fireEvent.click(screen.getByText('set'))
    expect(screen.getByTestId('nav').textContent).toBe('REPLACE')
  })

  it('nawigacja do innego widoku używa pushState', () => {
    mount('/start')
    fireEvent.click(screen.getByText('go'))
    expect(screen.getByTestId('nav').textContent).toBe('PUSH')
  })
})

describe('validDateRange — puste i uszkodzone parametry', () => {
  it('poprawny zakres przechodzi', () => {
    expect(validDateRange('2026-07-01', '2026-07-31')).toEqual(['2026-07-01', '2026-07-31'])
  })
  it('uszkodzona data → domyślna (pusta), bez wyjątku', () => {
    expect(validDateRange('2026-13-99', '2026-07-31')).toEqual(['', '2026-07-31'])
    expect(validDateRange('nie-data', null)).toEqual(['', ''])
  })
  it('odwrócony zakres (od > do) → domyślny', () => {
    expect(validDateRange('2026-08-01', '2026-07-01')).toEqual(['', ''])
  })
  it('pojedyncza data zostaje', () => {
    expect(validDateRange('2026-07-10', '')).toEqual(['2026-07-10', ''])
  })
})
