// Ekran „Trwa wgrywanie nowej wersji” (prośba 2026-09-30). Wdrożenie = kilkadziesiąt sekund
// bez serwera: zamiast losowych błędów „Brak połączenia” pokazujemy jeden czytelny komunikat, sami
// sprawdzamy /api/health co kilka sekund, a gdy serwer wróci z NOWĄ wersją — przeładowujemy stronę
// (inaczej karta zostałaby na starym kodzie, np. bez nowych funkcji paska). Po LONG_MS bez serwera
// dochodzi prośba o kontakt. Wersja zmieniona bez przerwy (np. wdrożenie w tle) → pasek „Odśwież”.
import { useCallback, useEffect, useRef, useState } from 'react'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { useT } from './i18n'

export const SERVER_DOWN_EVENT = 'timporye:server-unreachable'
export const CONTACT = 'admin@example.com'
const UP_EVERY_MS = 60_000
const DOWN_EVERY_MS = 5_000
const CONFIRM_MS = 3_000       // jedna nieudana próba to jeszcze nie wdrożenie (chwilowa sieć)
const LONG_MS = 5 * 60_000

type Health = { ok: boolean; build: string | null }

async function check(): Promise<Health> {
  try {
    const r = await fetch('/api/health', { cache: 'no-store', signal: AbortSignal.timeout?.(8_000) })
    if (!r.ok) return { ok: false, build: null }
    const h = await r.json() as { version?: string; built_at?: string }
    return { ok: true, build: `${h.version ?? ''}|${h.built_at ?? ''}` }
  } catch {
    return { ok: false, build: null }
  }
}

export default function DeployWatch({ reload = () => window.location.reload() }: { reload?: () => void }) {
  const t = useT()
  const [downSince, setDownSince] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [newVersion, setNewVersion] = useState(false)
  const build = useRef<string | null>(null)
  const down = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const probe = useCallback(async (confirming = false) => {
    clearTimeout(timer.current)
    const h = await check()
    if (h.ok) {
      const changed = build.current !== null && h.build !== build.current
      build.current ??= h.build
      if (down.current && changed) { reload(); return }      // wróciło po wdrożeniu → nowy kod
      if (changed) setNewVersion(true)
      down.current = false
      setDownSince(null)
      timer.current = setTimeout(() => probe(), UP_EVERY_MS)
    } else if (!down.current && !confirming) {
      timer.current = setTimeout(() => probe(true), CONFIRM_MS)
    } else {
      if (!down.current) { down.current = true; setDownSince(Date.now()) }
      timer.current = setTimeout(() => probe(), DOWN_EVERY_MS)
    }
  }, [reload])

  useEffect(() => {
    probe()
    const onDown = () => { if (!down.current) probe() }   // api.ts: żądanie bez serwera → sprawdź od razu
    window.addEventListener(SERVER_DOWN_EVENT, onDown)
    return () => { clearTimeout(timer.current); window.removeEventListener(SERVER_DOWN_EVENT, onDown) }
  }, [probe])

  useEffect(() => {
    if (downSince === null) return
    const id = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(id)
  }, [downSince])

  if (downSince !== null) {
    const long = now - downSince >= LONG_MS
    return (
      <div className="deploy-overlay" role="alertdialog" aria-modal="true" aria-labelledby="deploy-title">
        <div className="deploy-card">
          <LoaderCircle className="deploy-spin" size={32} aria-hidden="true" />
          <h2 id="deploy-title">{t('deployTitle')}</h2>
          <p>{t('deployWait')}</p>
          {long && (
            <p className="deploy-long" role="status">
              {t('deployLong')} <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
            </p>
          )}
        </div>
      </div>
    )
  }
  if (newVersion) {
    return (
      <div className="deploy-banner" role="status">
        {t('deployNewVersion')}
        <button type="button" className="btn small" onClick={reload}>
          <RefreshCw size={14} aria-hidden="true" /> {t('deployRefresh')}
        </button>
      </div>
    )
  }
  return null
}
