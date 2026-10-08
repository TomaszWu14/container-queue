import { useEffect, useState } from 'react'
import { useT } from './i18n'

// #65 — onboarding: 5 dymków przy pierwszym wejściu (localStorage 'onboarded' brak).
// Kotwiczone do [data-tour="..."] w DOM; gdy selektor nie istnieje na bieżącej
// stronie (np. krok "filtry" poza Kolejką), dymek wyśrodkowany (fallback).
const STEPS: { sel: string; key: string }[] = [
  { sel: '[data-tour="kolejka"]', key: 'obStep1' },
  { sel: '[data-tour="filtry"]', key: 'obStep2' },
  { sel: '[data-tour="widok"]', key: 'obStep3' },
  { sel: '[data-tour="ctrlk"]', key: 'obStep4' },
  { sel: '[data-tour="sledzenie"]', key: 'obStep5' },
]

export default function Onboarding() {
  const t = useT()
  const [step, setStep] = useState(0)
  const [active, setActive] = useState(() => !localStorage.getItem('onboarded'))
  const [rect, setRect] = useState<DOMRect | null>(null)

  useEffect(() => {
    if (!active) return
    // schowana kotwica (np. link „Kolejka” w zwiniętym menu na telefonie) ma prostokąt 0×0 —
    // traktujemy jak brak kotwicy (dymek wyśrodkowany), zamiast stawiać go w rogu (10, 0)
    const r = document.querySelector(STEPS[step].sel)?.getBoundingClientRect()
    setRect(r && r.width > 0 && r.height > 0 ? r : null)
  }, [active, step])

  if (!active) return null

  const finish = () => { localStorage.setItem('onboarded', '1'); setActive(false) }
  const next = () => (step < STEPS.length - 1 ? setStep(step + 1) : finish())

  const style = rect
    // pełne piksele — ułamkowe współrzędne (skalowanie 125/150%) rozmywały tekst dymka
    ? { top: Math.round(rect.bottom + 10), left: Math.round(Math.min(rect.left, window.innerWidth - 300)) }
    : undefined

  return (
    <div className={`ob-overlay${rect ? '' : ' ob-center'}`}>
      <div className="ob-bubble" style={style}>
        <p>{t(STEPS[step].key)}</p>
        <div className="ob-actions">
          <button type="button" className="btn ghost" onClick={finish}>{t('obPomin')}</button>
          <button type="button" className="btn" onClick={next}>{t('obDalej')}</button>
        </div>
        <span className="ob-dots">{STEPS.map((_, i) => (
          <i key={i} className={i === step ? 'on' : ''} />
        ))}</span>
      </div>
    </div>
  )
}
