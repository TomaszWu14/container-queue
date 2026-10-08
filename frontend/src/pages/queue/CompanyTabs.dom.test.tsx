// @vitest-environment jsdom
// Jeden akcent (2026-09-28): aktywna zakładka ma zawsze kolor akcentu, a spółkę rozpoznaje się po
// kropce w jej kolorze (--co-*, w dark jaśniejszy) — dawniej .mod-* przemalowywał cały akcent kolejki.
import { createContext } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
}))

import CompanyTabs from './CompanyTabs'

describe('zakładki spółek — znacznik spółki', () => {
  it('każda spółka ma kropkę w swoim kolorze, Tranzyt bez kropki', () => {
    const { container } = render(<CompanyTabs module="acme" setModule={() => {}}
      counts={{ ACME: 3, DLT: 1, BOREALIS: 0, COBALT: 2, PT: 5 }} transitCount={0} />)
    const pills = [...container.querySelectorAll('.kq-pill')]
    const dots = pills.map(p => (p.querySelector('.kq-pill-dot') as HTMLElement | null)
      ?.style.getPropertyValue('--kq-co') ?? null)
    expect(dots).toEqual(['var(--co-acme)', 'var(--co-dlt)', 'var(--co-borealis)',
      'var(--co-cobalt)', 'var(--co-pt)', null])
    expect(container.querySelector('.kq-pill-dot')?.getAttribute('aria-hidden')).toBe('true')
    expect(pills[0].classList.contains('active')).toBe(true)
  })
})
