// Po wdrożeniu stare chunki (assets/Strona-<hash>.js) znikają z serwera — otwarta karta przy
// pierwszym wejściu na lazy-stronę dostaje błąd importu. Vite zgłasza go zdarzeniem
// `vite:preloadError`: przeładowujemy raz (nowy index.html → nowe chunki). Flaga w
// sessionStorage chroni przed pętlą przeładowań, gdy chunk naprawdę nie istnieje.
const FLAG = 'timporye_chunk_reload'
const WINDOW_MS = 60_000

export function handlePreloadError(event: Event, reload = () => window.location.reload()): void {
  try {
    const last = Number(sessionStorage.getItem(FLAG) || 0)
    if (Date.now() - last < WINDOW_MS) return   // już próbowaliśmy — niech pokaże ErrorBoundary
    sessionStorage.setItem(FLAG, String(Date.now()))
  } catch { return }                             // brak sessionStorage → bez ryzyka pętli
  event.preventDefault()                         // nie rzucaj błędu — i tak przeładowujemy
  reload()
}

export function installChunkReload(): void {
  window.addEventListener('vite:preloadError', e => handlePreloadError(e))
}
