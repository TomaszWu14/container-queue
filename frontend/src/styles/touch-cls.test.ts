// Strażnik celów dotykowych i przesunięć układu (audyt UI S9/S11 — UX-011, UX-007):
// - na ekranach dotykowych (pointer: coarse) każdy przycisk, link-akcja i pole ma ≥ 44 px (--tap);
//   mały „?” pomocy dostaje niewidoczne pole trafienia, pola wyboru są większe — gęstość na
//   desktopie (mysz) bez zmian, bo reguły siedzą tylko w @media (pointer: coarse),
// - /analityka rezerwuje miejsce na KPI w trakcie ładowania (panel niżej nie skacze — CLS 0,19).
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { readAppCss } from '../appCss.testutil'

const coarse = () => [...readAppCss().matchAll(/@media \(pointer: coarse\) \{([\s\S]*?)\n\}/g)].map(m => m[1]).join('\n')

describe('cele dotykowe (pointer: coarse)', () => {
  it('przyciski, role=button, link-akcje i pola bez type mają min. --tap', () => {
    const css = coarse()
    expect(css).toMatch(/button, \[role="button"\], summary \{ min-height: var\(--tap\); \}/)
    expect(css).toMatch(/a\.link-like \{[^}]*min-height: var\(--tap\)/)
    expect(css).toMatch(/input:not\(\[type\]\)/)
  })

  it('„?” pomocy: pole trafienia 44 px bez zmiany układu; większe pola wyboru', () => {
    const css = coarse()
    expect(css).toMatch(/\.help-tip-btn::after \{ content: ''; position: absolute; inset: -14px; \}/)
    expect(css).toMatch(/input\[type="checkbox"\], input\[type="radio"\] \{ width: 22px; height: 22px; \}/)
  })

  it('reguły dotykowe nie wyciekają poza @media (pointer: coarse)', () => {
    const css = readAppCss().replace(/@media \(pointer: coarse\) \{[\s\S]*?\n\}/g, '')
    expect(css).not.toMatch(/^button, \[role="button"\], summary \{ min-height/m)
  })
})

describe('CLS /analityka', () => {
  it('panel KPI w trakcie ładowania ma zarezerwowaną wysokość', () => {
    const src = readFileSync(new URL('../pages/AnalitykaPage.tsx', import.meta.url), 'utf-8')
    expect(src).toMatch(/className=\{`panel an-kpi\$\{kpi \? '' : ' loading'\}`\}/)
    expect(readAppCss()).toMatch(/\.an-kpi\.loading \{ min-height: \d{3}px; \}/)
  })
})
