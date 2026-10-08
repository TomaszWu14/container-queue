// Jedno miejsce kopiowania do schowka. navigator.clipboard istnieje tylko w bezpiecznym
// kontekście (HTTPS/localhost) — instancja bez TLS chodzi po HTTP (http://192.0.2.10:81),
// więc tam API jest undefined i trzeba zejść do ukrytego textarea + execCommand('copy').
import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { useT } from './i18n'
import { useToast } from './feedback'

export async function copyToClipboard(text: string): Promise<void> {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return } catch { /* np. iframe bez uprawnień → fallback */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    if (!document.execCommand('copy')) throw new Error('execCommand copy failed')
  } finally {
    ta.remove()
  }
}

// Ikona ⧉ → ✓ na 1,5 s + toast. Klik nie może zaznaczać/rozwijać wiersza (stopPropagation).
export function CopyButton({ text, title }: { text: string; title?: string }) {
  const t = useT()
  const { showToast } = useToast()
  const [done, setDone] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const onClick = (e: MouseEvent) => {
    e.stopPropagation()
    copyToClipboard(text).then(() => {
      setDone(true)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setDone(false), 1500)
      showToast(t('copied'), 'success')
    }).catch(() => showToast(t('copyFailed'), 'error'))
  }
  return (
    <button type="button" className="copy-btn" data-copy={text} title={title ?? t('copyNo')}
            aria-label={title ?? t('copyNo')} onClick={onClick}>{done ? '✓' : '⧉'}</button>
  )
}
