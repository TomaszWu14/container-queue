// Globalna konfiguracja vitest (setupFiles w vite.config.ts).
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// getByRole domyślnie sprawdza widoczność każdego kandydata (getComputedStyle na nim i całym
// łańcuchu przodków) — na dużym DOM kolejki jedno getAllByRole('tab') trwało ~0,4 s, a pod
// równoległym obciążeniem kilka sekund, stąd timeouty 5 s w testach kolejki/trackingu.
// jsdom i tak nie ładuje naszego CSS, więc ta kontrola niewiele wnosi; ukrycie sprawdzamy jawnie.
// asyncUtilTimeout: pierwszy render dużej strony (kolejka) w świeżym workerze to ~1–2 s rozgrzewki
// JIT, a przy 11 równoległych workerach jsdom — kilka razy dłużej. Domyślne 1 s waitFor/findBy
// wtedy nie wystarcza (stąd losowe porażki pierwszego testu w pliku), więc jedno miejsce zamiast
// { timeout } rozrzuconych po testach.
configure({ defaultHidden: true, asyncUtilTimeout: 5000 })

// setPref() odkłada zapis profilu o 1,2 s — gdy plik testów kończył się wcześniej, timer odpalał
// po zniszczeniu jsdom („localStorage is not defined” = nieobsłużony błąd, czerwone CI na #698).
// Import dynamiczny: statyczny ładowałby prefs (i api) przed vi.mock('./api') w plikach testów.
afterEach(async () => { (await import('./prefs')).cancelPendingPrefs() })

// Bez `globals: true` Testing Library NIE odmontowuje sam po teście. Plik bez własnego cleanup()
// zostawiał zamontowaną stronę z pracą Reacta w kolejce; w pool threads (#893) odpalała ona po
// zniszczeniu jsdom („window is not defined” = nieobsłużony błąd, czerwone CI przy 784/784 zielonych).
afterEach(cleanup)
