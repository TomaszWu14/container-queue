// Strażnik audytu UI (PR 6): przycisk, którego jedyną treścią jest ikona (Lucide / <svg>)
// albo pojedynczy symbol (✕ ‹ › ⋯ + …), musi mieć nazwę: aria-label(ledby) albo title.
import { describe, expect, it } from 'vitest'
import { parseAst } from 'rolldown/parseAst'

const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

type N = { type?: string; start: number; end: number; [k: string]: unknown }
type Attr = { type: string; name: { name: string } }

const SYMBOL = /^[\s✕×‹›⋯…+−\-<>«»↑↓←→▲▼▸▾⟳↻]*$/u

// ikona = <svg>, komponent *Icon albo zaimportowany z lucide-react w tym pliku
const lucideNames = (src: string) => new Set((src.match(/import \{([^}]*)\} from 'lucide-react'/)?.[1] ?? '')
  .split(',').map(x => x.trim().split(/\s+as\s+/).pop()!).filter(Boolean))

function isIconOnly(children: N[], src: string): boolean {
  const lucide = lucideNames(src)
  const meaningful = children.filter(c =>
    !(c.type === 'JSXText' && !src.slice(c.start, c.end).trim()))
  if (meaningful.length === 0) return false
  const iconEl = (c: N) => c.type === 'JSXElement' && isIconOnly([c], src)
  return meaningful.every(c => {
    if (c.type === 'JSXText') return SYMBOL.test(src.slice(c.start, c.end))
    if (c.type === 'JSXExpressionContainer') {
      // {open ? <ChevronDownIcon /> : <ChevronRightIcon />} / {cond && <Icon />} / {'✕'}
      const e = c.expression as N & { consequent?: N; alternate?: N; right?: N; value?: unknown }
      if (e.type === 'ConditionalExpression') return iconEl(e.consequent as N) && iconEl(e.alternate as N)
      if (e.type === 'LogicalExpression') return iconEl(e.right as N)
      if (e.type === 'Literal' && typeof e.value === 'string') return SYMBOL.test(e.value)
      return false
    }
    if (c.type === 'JSXElement') {
      const name = (c.openingElement as { name: { type: string; name?: string } }).name
      return name.type === 'JSXIdentifier'
        && (name.name === 'svg' || /Icon$/.test(name.name ?? '') || lucide.has(name.name ?? ''))
    }
    return false
  })
}

function unnamed(path: string, src: string): string[] {
  const out: string[] = []
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { node.forEach(visit); return }
    const n = node as N
    if (n.type === 'JSXElement') {
      const op = n.openingElement as { name: { type: string; name?: string }; attributes: Attr[]; start: number }
      if (op.name.type === 'JSXIdentifier' && op.name.name === 'button') {
        const names = op.attributes.filter(a => a.type === 'JSXAttribute').map(a => a.name.name)
        const spread = op.attributes.some(a => a.type === 'JSXSpreadAttribute')
        const named = names.some(a => a === 'aria-label' || a === 'aria-labelledby' || a === 'title')
        if (!named && !spread && isIconOnly(n.children as N[], src))
          out.push(`${path}:${src.slice(0, op.start).split('\n').length}`)
      }
    }
    for (const v of Object.values(n)) if (v && typeof v === 'object') visit(v)
  }
  visit(parseAst(src, { lang: 'tsx' }))
  return out
}

describe('a11y — przyciski ikonowe mają nazwę', () => {
  it('żaden przycisk z samą ikoną/symbolem nie jest bez aria-label/title', () => {
    const offenders = Object.entries(sources).flatMap(([p, s]) => unnamed(p, s))
    expect(offenders).toEqual([])
  })

  it('detektor: łapie <button><XIcon /></button> i „✕”, przepuszcza tekst i aria-label', () => {
    expect(unnamed('x', 'const a = <button><XIcon size={14} /></button>')).toHaveLength(1)
    expect(unnamed('x', 'const a = <button>✕</button>')).toHaveLength(1)
    expect(unnamed('x', 'const a = <button aria-label="Zamknij"><XIcon /></button>')).toEqual([])
    expect(unnamed('x', "const a = <button><XIcon /> {t('close')}</button>")).toEqual([])
    expect(unnamed('x', 'const a = <button>Zapisz</button>')).toEqual([])
  })
})
