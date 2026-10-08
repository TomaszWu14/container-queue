/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { globSync, readFileSync, realpathSync } from 'node:fs'
import { defineConfig, searchForWorkspaceRoot } from 'vite'
import { configDefaults } from 'vitest/config'

// Testy w wątkach (pool threads) są ~2x szybsze niż w procesach (forks) — głównie tańszy start
// świeżego jsdom na plik. Wyjątek: plik ustawiający process.env.TZ — strefa czasowa jest wspólna
// dla całego procesu, więc w wątku zmiana nie działa; takie pliki idą w forks (wykrywane same).
const TZ_TESTS = globSync('src/**/*.test.{ts,tsx}')
  .filter(f => readFileSync(f, 'utf8').includes('process.env.TZ'))
  .map(f => f.replaceAll('\\', '/'))   // Windows: globSync zwraca „\”, include/exclude chcą „/”

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // worktree z node_modules jako junction/symlink do innego katalogu: bez rzeczywistej ścieżki
    // vite odrzuca (403) pliki spoza allow-listy — m.in. czcionki @fontsource (IBM Plex), więc
    // zrzuty i testy wizualne renderowały się czcionką zastępczą
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), realpathSync('node_modules')] },
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  // e2e/ to testy Playwright (własny runner) — vitest ma je pomijać, inaczej wywala
  // się na „Playwright Test did not expect test() to be called here".
  test: {
    exclude: [...configDefaults.exclude, 'e2e/**'],
    setupFiles: ['src/test-setup.ts'],
    // testy DOM kolejki/trackingu realnie trwają 2–6 s przy pełnym przebiegu (świeży jsdom na
    // plik + rozgrzewka renderu pod równoległym obciążeniem); domyślne 5 s dawało losowe
    // timeouty. Jedno miejsce zamiast vi.setConfig per plik.
    testTimeout: 15000,
    projects: [
      { extends: true, test: { name: 'threads', pool: 'threads', exclude: [...configDefaults.exclude, 'e2e/**', ...TZ_TESTS] } },
      { extends: true, test: { name: 'tz', pool: 'forks', include: TZ_TESTS } },
    ],
  },
})
