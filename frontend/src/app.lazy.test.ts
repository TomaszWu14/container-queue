// Strażnik podziału kodu (PERF-006): App ładuje statycznie tylko strony startowe (pulpit, kolejka)
// i ekrany hasła; każda inna strona trasy to React.lazy → osobny chunk. Dawniej wszystkie ~35 stron
// trafiały do index.js (1,36 MB, gzip 407 kB); po zmianie główny chunk < 500 kB (gzip ≈ 147 kB).
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const src = readFileSync(new URL('./App.tsx', import.meta.url), 'utf-8')
const EAGER = new Set(['./pages/DashboardPage', './pages/QueuePage', './pages/AuthPages'])

describe('App — strony tras ładowane leniwie', () => {
  it('statyczne importy stron tylko dla stron startowych', () => {
    const eager = [...src.matchAll(/^import [^\n]* from '(\.\/pages\/[\w/]+)'$/gm)].map(m => m[1])
    expect(eager.filter(p => !EAGER.has(p))).toEqual([])
  })

  it('reszta stron przez lazy(), trasy w <Suspense> z szkieletem strony', () => {
    expect(src.match(/= lazy\(\(\) => import\('\.\/pages\//g)?.length).toBeGreaterThanOrEqual(30)
    expect(src.match(/<Suspense fallback=\{pageFallback\}>/g)).toHaveLength(2)
  })
})
