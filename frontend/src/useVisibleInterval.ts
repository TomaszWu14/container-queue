import { useEffect, useRef } from 'react'

// Odpytywanie tylko w WIDOCZNEJ karcie: tick w ukrytej karcie jest pomijany (kilka otwartych
// kart × kilka liczników = stały ruch do serwera bez widza), a po powrocie do karty dane
// odświeżają się od razu, nie dopiero przy następnym ticku. Pierwsze pobranie robi wołający.
// `fn` przez ref — nowa funkcja w każdym renderze nie restartuje zegara.
export function useVisibleInterval(fn: () => void, ms: number): void {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    const run = () => { if (!document.hidden) ref.current() }
    const id = setInterval(run, ms)
    document.addEventListener('visibilitychange', run)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', run) }
  }, [ms])
}
