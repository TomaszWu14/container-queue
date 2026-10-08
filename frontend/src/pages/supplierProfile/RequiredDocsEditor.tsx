// „Wymagane dokumenty” dostawcy (spec 2026-10-06 decyzja 16): zestaw kafelków, których brak liczy
// się jako brak (kafelki, kolejka, ostrzeżenie przy zmianie statusu). null = domyślny (wszystkie).
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { TILE_META, type TileCode } from '../../DocumentTiles'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'

const CODES = Object.keys(TILE_META) as TileCode[]

export default function RequiredDocsEditor({ supplierId, value, canEdit, onSaved }: {
  supplierId: number
  value: TileCode[] | null | undefined
  canEdit: boolean
  onSaved: (codes: TileCode[] | null) => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const [picked, setPicked] = useState<Set<TileCode>>(new Set(value ?? CODES))
  const [busy, setBusy] = useState(false)

  const save = async (codes: TileCode[] | null) => {
    setBusy(true)
    try {
      const res = await api.put<{ required_docs: TileCode[] | null }>(
        `/api/suppliers/${supplierId}/required-docs`, { codes })
      setPicked(new Set(res.required_docs ?? CODES))
      onSaved(res.required_docs)
      showToast(t('rqdSaved'), 'success')
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  const toggle = (code: TileCode) => setPicked(prev => {
    const next = new Set(prev)
    if (!next.delete(code)) next.add(code)
    return next
  })

  return (
    <fieldset className="sdp-required" disabled={!canEdit || busy}>
      <legend>
        {t('rqdTitle')} <span className="sdp-pill">{value ? t('rqdCustom') : t('rqdDefault')}</span>
      </legend>
      <p className="muted txt-xs">{t('rqdHint')}</p>
      <div className="sdp-chips">
        {CODES.map(code => (
          <label key={code} className="chip" title={t(`dtName_${code}`)}>
            <input type="checkbox" checked={picked.has(code)} onChange={() => toggle(code)} />
            {' '}{TILE_META[code].short} · {t(`dtName_${code}`)}
          </label>
        ))}
      </div>
      {canEdit && (
        <div className="row" style={{ gap: 8, marginTop: 8 }}>
          <button type="button" className="btn small"
                  onClick={() => save(CODES.filter(c => picked.has(c)))}>{t('rqdSave')}</button>
          <button type="button" className="btn small secondary" disabled={!value}
                  onClick={() => save(null)}>{t('rqdReset')}</button>
        </div>
      )}
    </fieldset>
  )
}
