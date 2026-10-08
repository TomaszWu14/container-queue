import { defineConfig } from '@playwright/test'
import { API, API_PORT, WEB, WEB_PORT } from './e2e/ports'

// E2E (nie w blocking CI — .github/workflows/e2e.yml: co noc + ręcznie, self-hosted; TEST-007):
// odpala backend (uvicorn, SQLite dev) + frontend (vite dev) i klika w prawdziwej przeglądarce.
export default defineConfig({
  testDir: './e2e',
  testIgnore: ['visual/**'],   // testy wizualne: playwright.visual.config.ts (npm run e2e:visual)
  fullyParallel: false,   // wspólny backend/baza — testy po kolei, bez wyścigów o stan
  workers: 1,             // jeden worker: wszystkie specy dzielą ten sam backend + e2e.db
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  globalSetup: './e2e/global-setup.ts',
  outputDir: 'test-results',
  use: {
    baseURL: WEB,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command: `python -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: '../backend',
      url: `${API}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: { DATABASE_URL: 'sqlite:///./e2e.db', RUN_BACKGROUND_JOBS: 'false', API_RATE_LIMIT_PER_MINUTE: '0',
             REQUIRE_2FA_ADMIN: 'false' },  // SEC-006: konto admin e2e bez TOTP
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      url: WEB,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: { VITE_API_TARGET: API },   // proxy /api z vite.config.ts
    },
  ],
})
