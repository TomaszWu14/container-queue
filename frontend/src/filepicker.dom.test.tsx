// @vitest-environment jsdom
// Wybór pliku po polsku (audyt UI B24 — UX-028): natywna kontrolka „Choose File / No file chosen” mówiła
// językiem przeglądarki. Każdy <input type="file"> jest ukryty i otwierany przyciskiem aplikacji
// (FilePicker: „Wybierz plik” + nazwa wybranego pliku albo „Nie wybrano pliku”).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { parseAst } from 'rolldown/parseAst'
import { FilePicker } from './FilePicker'

const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

type Node = { type?: string; start: number; [k: string]: unknown }
type Attr = { type: string; name: { name: string }; value: { start: number; end: number } | null }

// widoczny natywny input pliku = bez atrybutu hidden i bez display: 'none'
function visibleFileInputs(path: string, src: string): string[] {
  const found: string[] = []
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { node.forEach(visit); return }
    const n = node as Node
    if (n.type === 'JSXOpeningElement' && (n.name as { name?: string }).name === 'input') {
      const attrs: Record<string, string> = {}
      for (const a of n.attributes as Attr[]) {
        if (a.type === 'JSXAttribute') attrs[a.name.name] = a.value ? src.slice(a.value.start, a.value.end) : 'true'
      }
      const file = /['"]file['"]/.test(attrs.type ?? '')
      const hidden = attrs.hidden || /display:\s*'none'/.test(attrs.style ?? '')
      if (file && !hidden) found.push(`${path}:${src.slice(0, n.start).split('\n').length}`)
    }
    for (const v of Object.values(n)) if (v && typeof v === 'object') visit(v)
  }
  visit(parseAst(src, { lang: 'tsx' }))
  return found
}

afterEach(cleanup)

describe('wybór pliku (B24)', () => {
  it('żaden <input type="file"> nie jest widoczną natywną kontrolką', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50)
    expect(Object.entries(sources).flatMap(([p, s]) => visibleFileInputs(p, s))).toEqual([])
  })

  it('FilePicker: przycisk po polsku, nazwa pliku, ukryty input z nazwą dla czytnika', () => {
    const onChange = vi.fn()
    const { rerender } = render(<FilePicker label="Plik" caption="Plik (CSV/XLSX)" file={null} onChange={onChange} />)
    expect(screen.getByText('Plik (CSV/XLSX)')).toBeTruthy()
    expect(screen.getByText('Nie wybrano pliku')).toBeTruthy()
    const input = screen.getByLabelText('Plik') as HTMLInputElement
    expect(input.hidden).toBe(true)
    const click = vi.spyOn(input, 'click')
    fireEvent.click(screen.getByRole('button', { name: /Wybierz plik/ }))
    expect(click).toHaveBeenCalled()
    const f = new File(['x'], 'dane.xlsx')
    fireEvent.change(input, { target: { files: [f] } })
    expect(onChange).toHaveBeenCalledWith(f)
    rerender(<FilePicker label="Plik" file={f} onChange={onChange} />)
    expect(screen.getByText('dane.xlsx')).toBeTruthy()
  })
})
