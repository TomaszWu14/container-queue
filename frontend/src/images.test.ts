// Strażnik obrazów (audyt UI S16 / UX-045, CODE-006): każdy <img> ma wymiary (width + height —
// przeglądarka rezerwuje miejsce, brak skoku układu/CLS) i loading="lazy" (zdjęcia poza ekranem
// nie blokują startu), a w src/assets nie leży plik, do którego nic się nie odwołuje
// (nieużywany blue-marble.jpg ważył 2,4 MB — globus korzysta z public/globe/*.webp).
import { readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { parseAst } from 'rolldown/parseAst'

const sources = import.meta.glob(['./**/*.{ts,tsx,css}', '!./**/*.test.{ts,tsx}'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

type Node = { type?: string; start: number; end: number; [k: string]: unknown }
type Attr = { type: string; name: { name: string } }

function imgProblems(path: string, src: string): string[] {
  const found: string[] = []
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { node.forEach(visit); return }
    const n = node as Node
    if (n.type === 'JSXOpeningElement') {
      const name = n.name as { type: string; name: string }
      if (name.type === 'JSXIdentifier' && name.name === 'img') {
        const attrs = new Set((n.attributes as Attr[])
          .filter(a => a.type === 'JSXAttribute').map(a => a.name.name))
        const missing = ['width', 'height', 'loading'].filter(a => !attrs.has(a))
        if (missing.length)
          found.push(`${path}:${src.slice(0, n.start).split('\n').length} <img> bez ${missing.join(', ')}`)
      }
    }
    for (const v of Object.values(n)) if (v && typeof v === 'object') visit(v)
  }
  visit(parseAst(src, { lang: 'tsx' }))
  return found
}

describe('obrazy (S16)', () => {
  it('każdy <img> ma width, height i loading', () => {
    const tsx = Object.entries(sources).filter(([p]) => p.endsWith('.tsx'))
    expect(tsx.length).toBeGreaterThan(50)
    expect(tsx.flatMap(([p, src]) => imgProblems(p, src))).toEqual([])
  })

  it('wykrywa <img> bez wymiarów, a akceptuje pełny komplet', () => {
    expect(imgProblems('x.tsx', 'const a = <img src={s} alt="" />')).toHaveLength(1)
    expect(imgProblems('x.tsx', 'const a = <img src={s} alt="" width={9} height={9} loading="lazy" />')).toEqual([])
  })

  it('w src/assets nie ma nieużywanych plików', () => {
    const dir = fileURLToPath(new URL('./assets', import.meta.url))
    let files: string[] = []
    try { files = readdirSync(dir) } catch { /* brak katalogu = brak plików */ }
    const code = Object.values(sources).join('\n')
    expect(files.filter(f => !code.includes(f))).toEqual([])
  })
})
