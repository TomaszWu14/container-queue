// Porty backendu i panelu dla E2E (TEST-007). Domyślnie jak lokalnie (8000 / 5173);
// na runnerze CI inne (E2E_API_PORT / E2E_WEB_PORT w e2e.yml) — na hoście runnera działa
// panel Coolify na :8000, a Playwright w trybie CI odmawia startu na zajętym porcie.
export const API_PORT = process.env.E2E_API_PORT ?? '8000'
export const WEB_PORT = process.env.E2E_WEB_PORT ?? '5173'
export const API = `http://localhost:${API_PORT}`
export const WEB = `http://localhost:${WEB_PORT}`
