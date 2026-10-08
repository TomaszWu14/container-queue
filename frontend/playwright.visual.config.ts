import { defineConfig } from '@playwright/test'
import base from './playwright.config'
import { API, API_PORT } from './e2e/ports'

// Testy wizualne (toHaveScreenshot) kluczowych widoków — osobno od e2e, bo wzorce PNG są
// per system (font rendering): lokalnie `npm run e2e:visual`, aktualizacja `-- --update-snapshots`.
// Ten sam backend (e2e.db) i frontend co e2e.
// świeża baza przy każdym biegu (seed e2e i dane testu nie narastają → deterministyczne zrzuty)
const backend = {
  command: `python -c "import os; os.path.exists('visual.db') and os.remove('visual.db')" && python -m uvicorn app.main:app --port ${API_PORT}`,
  cwd: '../backend', url: `${API}/api/health`, reuseExistingServer: false, timeout: 30_000,
  env: { DATABASE_URL: 'sqlite:///./visual.db', RUN_BACKGROUND_JOBS: 'false', API_RATE_LIMIT_PER_MINUTE: '0',
         REQUIRE_2FA_ADMIN: 'false' },  // SEC-006: konto admin e2e bez TOTP
}

export default defineConfig({
  ...base,
  webServer: [backend, (base.webServer as object[])[1]],
  testDir: './e2e/visual',
  testIgnore: [],
  snapshotPathTemplate: '{testDir}/__screenshots__/{platform}/{arg}{ext}',
  // ciasny próg: 1% strony przepuszczał przesunięcie etykiet o ~10 px — sprawdzone na tej samej maszynie 0 szumu
  expect: { toHaveScreenshot: { maxDiffPixels: 50, animations: 'disabled', caret: 'hide' } },
})
