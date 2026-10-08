import { useCallback, useRef, useState } from 'react'

// Blokada podwójnego wysłania: `busy` (do disabled przycisku) na czas akcji, a drugie
// wywołanie `run` w trakcie jest ignorowane — przez ref, bo dwa kliknięcia w tej samej
// klatce nie zdążą zobaczyć nowego stanu. Błędy obsługuje wołający (toast / setError).
export function useBusy() {
  const [busy, setBusy] = useState(false)
  const running = useRef(false)
  const run = useCallback(async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (running.current) return undefined
    running.current = true
    setBusy(true)
    try { return await fn() } finally { running.current = false; setBusy(false) }
  }, [])
  return { busy, run }
}
