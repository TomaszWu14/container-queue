// Mini-kafelki dokumentów w wierszu kolejki (spec 2026-10-06 decyzja 28): PI·CI·PL·BL·SAD + „⏳ N”
// części w poczekalni. Jedno żądanie GET /api/document-tiles?ids=… na listę (nie per wiersz),
// stan i kolory jak w DocumentTiles (klasy dt-sq / dt-<kod> / st-<stan>).
import { memo, useEffect, useState } from 'react'
import { api } from '../../api'
import { useT } from '../../i18n'

export const MINI_CODES = ['PI', 'CI', 'PL', 'BL', 'SAD'] as const
type MiniCode = typeof MINI_CODES[number]
type TileState = 'none' | 'present' | 'ok' | 'warn' | 'bad'
export interface DocMini { codes: Record<MiniCode, TileState>; missing: MiniCode[]; intake_pending: number }
export type DocTilesMap = Record<number, DocMini>

const CHUNK = 500        // limit paczki po stronie API (BULK_MAX)
const DEBOUNCE_MS = 300  // filtry/odświeżenia w serii → jedno żądanie

const isMini = (v: unknown): v is DocMini =>
  !!v && typeof v === 'object' && !!(v as DocMini).codes && Array.isArray((v as DocMini).missing)

/** Mapa id → mini-kafelki dla podanych kontenerów. Pobiera ponownie dopiero przy zmianie zestawu id.
 *  ponytail: stan po edycji dokumentów odświeża się przy następnej zmianie listy / przeładowaniu. */
export function useDocTiles(ids: number[], enabled: boolean): DocTilesMap {
  const [map, setMap] = useState<DocTilesMap>({})
  const key = ids.join(',')
  useEffect(() => {
    if (!enabled || !key) return
    let cancelled = false
    const timer = setTimeout(async () => {
      const list = key.split(',')
      const next: DocTilesMap = {}
      for (let i = 0; i < list.length; i += CHUNK) {
        try {
          const part = await api.get<Record<string, unknown>>(`/api/document-tiles?ids=${list.slice(i, i + CHUNK).join(',')}`)
          for (const [id, v] of Object.entries(part ?? {})) if (isMini(v)) next[Number(id)] = v
        } catch { /* kafelki nie mogą wywalić kolejki — brak danych = pusta komórka */ }
        if (cancelled) return
      }
      setMap(next)
    }, DEBOUNCE_MS)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [key, enabled])
  return map
}

const NAME: Record<MiniCode, string> = {
  PI: 'dtName_PI', CI: 'dtName_CI', PL: 'dtName_PL', BL: 'dtName_BL', SAD: 'kqDocSad',
}

/** Pasek 5 kwadracików + znacznik poczekalni; memo — wiersz przerysowuje się tylko przy nowych danych. */
export const MiniDocTiles = memo(function MiniDocTiles({ d }: { d: DocMini }) {
  const t = useT()
  return (
    <span className="dt-compact dt-mini" role="list" aria-label={t('dtTitle')}>
      {MINI_CODES.map(code => {
        const state = d.codes[code] ?? 'none'
        const miss = d.missing.includes(code)
        return (
          <span key={code} role="listitem" title={`${t(NAME[code])} — ${t(`dtState_${state}`)}${miss ? ` · ${t('dtMissing')}` : ''}`}
                className={`dt-sq dt-${code === 'SAD' ? 'SAD_PW' : code} st-${state}${miss ? ' miss' : ''}`}>
            {code}
          </span>
        )
      })}
      {d.intake_pending > 0 && (
        <span className="dt-intake mono" title={t('kqDocIntake').replace('{n}', String(d.intake_pending))}>
          ⏳ {d.intake_pending}
        </span>
      )}
    </span>
  )
})
