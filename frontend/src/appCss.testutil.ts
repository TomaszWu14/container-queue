// Tylko dla testów-strażników CSS: globalne style aplikacji (dawny styles.css) jako jeden
// tekst — pliki src/styles/NN-*.css sklejone w kolejności numeracji (= kolejność importu w main.tsx).
import { readdirSync, readFileSync } from 'node:fs'

export function readAppCss(): string {
  const dir = `${process.cwd()}/src/styles`
  return readdirSync(dir).filter(f => f.endsWith('.css')).sort()
    .map(f => readFileSync(`${dir}/${f}`, 'utf-8')).join('')
}
