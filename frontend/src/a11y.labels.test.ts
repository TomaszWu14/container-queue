// Strażnik audytu UI S1: każde pole formularza ma nazwę dostępną dla czytnika ekranu —
// <label>/<Field> wokół, aria-label(ledby), id (htmlFor) albo title. Ukryte pola
// (type=hidden, atrybut hidden, display:none — np. input pliku otwierany przyciskiem) pomijamy.
import { describe, expect, it } from 'vitest'
import { parseAst } from 'rolldown/parseAst'

const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

type Node = { type?: string; start: number; end: number; [k: string]: unknown }
type Attr = { type: string; name: { name: string }; value: Node | null }

function unlabeled(path: string, src: string): string[] {
  const found: string[] = []
  const visit = (node: unknown, inLabel: boolean) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { node.forEach(n => visit(n, inLabel)); return }
    const n = node as Node
    let label = inLabel
    if (n.type === 'JSXElement') {
      const op = n.openingElement as { name: { type: string; name: string }; attributes: Attr[]; start: number }
      const tag = op.name.type === 'JSXIdentifier' ? op.name.name : ''
      if (tag === 'label' || tag === 'Field') label = true
      if (['input', 'select', 'textarea'].includes(tag) && !label) {
        const attrs: Record<string, string> = {}
        let spread = false
        for (const a of op.attributes) {
          if (a.type === 'JSXSpreadAttribute') { spread = true; continue }
          attrs[a.name.name] = a.value ? src.slice(a.value.start, a.value.end) : 'true'
        }
        const named = attrs['aria-label'] || attrs['aria-labelledby'] || attrs.id || attrs.title
        const hidden = attrs.hidden || /['"]hidden['"]/.test(attrs.type ?? '') || /display:\s*'none'/.test(attrs.style ?? '')
        if (!named && !hidden && !spread)
          found.push(`${path}:${src.slice(0, op.start).split('\n').length} <${tag}>`)
      }
    }
    for (const v of Object.values(n)) if (v && typeof v === 'object') visit(v, label)
  }
  visit(parseAst(src, { lang: 'tsx' }), false)
  return found
}

describe('a11y — etykiety pól (S1)', () => {
  it('żadne pole formularza nie jest bez nazwy', () => {
    const offenders = Object.entries(sources).flatMap(([path, src]) => unlabeled(path, src))
    expect(Object.keys(sources).length).toBeGreaterThan(50)
    expect(offenders).toEqual([])
  })

  it('wykrywa pole bez etykiety, a akceptuje <label>, <Field> i aria-label', () => {
    expect(unlabeled('x.tsx', 'const a = <div><input value={v} /></div>')).toHaveLength(1)
    expect(unlabeled('x.tsx', 'const a = <label>Nazwa <input value={v} /></label>')).toEqual([])
    expect(unlabeled('x.tsx', 'const a = <Field label="N"><select /></Field>')).toEqual([])
    expect(unlabeled('x.tsx', 'const a = <input aria-label="N" />')).toEqual([])
    expect(unlabeled('x.tsx', 'const a = <input type="file" style={{ display: \'none\' }} />')).toEqual([])
  })
})
