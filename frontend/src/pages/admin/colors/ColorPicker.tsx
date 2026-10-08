// Wybór jednego koloru: siatka 500 barw (25 jasności × 20 kolumn), pole #rrggbb i systemowy próbnik.
import { useMemo, useState } from 'react'
import { useT } from '../../../i18n'
import { palette } from './palette'

const HEX = /^#[0-9a-f]{6}$/

export function ColorPicker({ value, fallback, onPick, onReset }: {
  value: string, fallback: string, onPick: (hex: string) => void, onReset: () => void,
}) {
  const t = useT()
  const grid = useMemo(palette, [])
  const [typed, setTyped] = useState(value)
  const commit = (raw: string) => {
    const hex = raw.trim().toLowerCase()
    setTyped(hex)
    if (HEX.test(hex)) onPick(hex)
  }
  return (
    <div className="colpick">
      <div className="colpick-grid" role="listbox" aria-label={t('colPalette')}>
        {grid.flat().map(hex => (
          <button key={hex} type="button" role="option" aria-selected={hex === value} title={hex}
                  className={hex === value ? 'on' : ''} style={{ background: hex }}
                  onClick={() => { setTyped(hex); onPick(hex) }} />
        ))}
      </div>
      <div className="colpick-row">
        <label htmlFor="colpick-hex">{t('colHex')}</label>
        <input id="colpick-hex" value={typed} maxLength={7} spellCheck={false}
               aria-invalid={!HEX.test(typed)} onChange={e => commit(e.target.value)} />
        <input type="color" aria-label={t('colSystemPicker')} value={HEX.test(typed) ? typed : value}
               onChange={e => commit(e.target.value)} />
        <button type="button" className="btn small secondary" onClick={() => { setTyped(fallback); onReset() }}>
          {t('colResetOne')}
        </button>
      </div>
    </div>
  )
}
