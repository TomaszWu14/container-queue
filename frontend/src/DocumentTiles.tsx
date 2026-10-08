// Kafelki dokumentów dostawy (spec 2026-10-01-kafelki-dokumentow, wzór: compare dostawa_detail):
// PI · CI ⇄ PL · BL · SAD-DRAFT → SAD-PZ → SAD-PW. Stan z GET /containers/{id}/document-tiles
// (paczki faktur + załączniki z kodem kafelka + drafty SAD). Kafelki pokazują stan i otwierają
// plik — nie wgrywają (spec 2026-10-06 decyzja 1: jedyne wejście to poczekalnia „Dodaj dokumenty”).
// Kompakt = szuflada.
import { useCallback, useEffect, useState } from 'react'
import {
  AnchorIcon, ArrowLeftRightIcon, ArrowRightIcon, FileCheckIcon, FileTextIcon, ListChecksIcon,
  ReceiptIcon, ShieldCheckIcon, StampIcon,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api, downloadFile, errorMessage } from './api'
import { useT } from './i18n'

export type TileCode = 'PI' | 'CI' | 'PL' | 'BL' | 'SAD_DRAFT' | 'SAD_PZ' | 'SAD_PW'
type TileState = 'none' | 'present' | 'ok' | 'warn' | 'bad'
interface TileFile {
  source: 'invoice' | 'attachment' | 'sad_draft'; id: number; name: string; filename: string
  created_at: string; url: string | null
}
interface Tile { code: TileCode; state: TileState; required: boolean; files: TileFile[] }
export interface TilesResult { tiles: Tile[]; loaded: number; total: number; missing: TileCode[] }

// skrót, ikona (różna dla każdego typu); kolor w CSS po klasie dt-<kod>
export const TILE_META: Record<TileCode, { short: string; icon: LucideIcon }> = {
  PI: { short: 'PI', icon: FileCheckIcon },
  CI: { short: 'CI', icon: ReceiptIcon },
  PL: { short: 'PL', icon: ListChecksIcon },
  BL: { short: 'BL', icon: AnchorIcon },
  SAD_DRAFT: { short: 'SD', icon: FileTextIcon },
  SAD_PZ: { short: 'PZ', icon: StampIcon },
  SAD_PW: { short: 'PW', icon: ShieldCheckIcon },
}
// grupy jak w compare: para CI ⇄ PL i łańcuch obiegu SAD
const GROUPS: { codes: TileCode[]; link?: 'pair' | 'chain' }[] = [
  { codes: ['PI'] }, { codes: ['CI', 'PL'], link: 'pair' }, { codes: ['BL'] },
  { codes: ['SAD_DRAFT', 'SAD_PZ', 'SAD_PW'], link: 'chain' },
]

export const isTilesResult = (data: unknown): data is TilesResult =>
  !!data && typeof data === 'object' && Array.isArray((data as TilesResult).tiles)

export function useDocumentTiles(containerId: number) {
  const [result, setResult] = useState<TilesResult | null>(null)
  const load = useCallback(() => {
    api.get<TilesResult>(`/api/containers/${containerId}/document-tiles`)
      .then(r => setResult(isTilesResult(r) ? r : null)).catch(() => setResult(null))
  }, [containerId])
  useEffect(() => load(), [load])
  return { result, load }
}

/** Plik kafelka: PDF z paczki faktur otwiera się w karcie (inline), załącznik — pobranie. */
export function openTileFile(file: TileFile) {
  if (!file.url) return Promise.resolve()
  if (file.source === 'invoice') { window.open(file.url, '_blank', 'noopener'); return Promise.resolve() }
  return downloadFile(file.url, file.filename)
}

/** Kompakt (szuflada kolejki): małe kolorowe kwadraciki ze skrótem i kropką stanu;
 *  `onOpen` — klik przenosi do pełnych kafelków (zakładka Dokumenty). */
export function DocumentTilesCompact({ result, onOpen }: { result: TilesResult; onOpen?: () => void }) {
  const t = useT()
  // spany z rolami listy — kompakt bywa w przycisku (szuflada), a <ul> w <button> to zły HTML
  const list = (
    <span className="dt-compact" role="list" aria-label={t('dtTitle')}>
      {result.tiles.map(tile => (
        <span key={tile.code} role="listitem"
              className={`dt-sq dt-${tile.code} st-${tile.state}${tile.required && tile.state === 'none' ? ' miss' : ''}`}
              title={`${t(`dtName_${tile.code}`)} — ${t(`dtState_${tile.state}`)}`}>
          {TILE_META[tile.code].short}
        </span>
      ))}
    </span>
  )
  if (!onOpen) return list
  const missing = result.missing.length ? ` · ${t('dtMissing')}: ${result.missing.length}` : ''
  return (
    <button type="button" className="dt-compact-btn" onClick={onOpen}
            title={`${t('dtTitle')} ${result.loaded}/${result.total}${missing}`}>{list}</button>
  )
}

/** Szuflada kolejki: kwadraciki pobierają stan sami (komponent nie renderuje nic do odpowiedzi). */
export function DrawerDocumentTiles({ containerId, onOpen }: { containerId: number; onOpen: () => void }) {
  const { result } = useDocumentTiles(containerId)
  return result ? <DocumentTilesCompact result={result} onOpen={onOpen} /> : null
}

export default function DocumentTiles({ containerId }: { containerId: number }) {
  const t = useT()
  const { result } = useDocumentTiles(containerId)
  const [error, setError] = useState('')
  const [managed, setManaged] = useState<TileCode | null>(null)
  const open = (file: TileFile) => openTileFile(file).catch(err => setError(errorMessage(err)))

  if (!result) return null
  const byCode = new Map(result.tiles.map(tile => [tile.code, tile]))
  const tileView = (code: TileCode) => {
    const tile = byCode.get(code)!
    const Icon = TILE_META[code].icon
    const latest = tile.files[0]
    return (
      <div key={code} className={`dt-tile dt-${code}`}>
        {/* pusty kafelek nic nie robi — nowe pliki tylko przez „Dodaj dokumenty” powyżej */}
        <button type="button" className="dt-main" onClick={() => latest && open(latest)} disabled={!latest}
                title={latest ? t('dtOpen') : undefined}>
          <span className="dt-icon"><Icon size={18} aria-hidden="true" /></span>
          <span className={`dt-led st-${tile.state}`} role="img" aria-label={t(`dtState_${tile.state}`)} />
          <b className="dt-code">{code.replace('_', '-')}</b>
          <span className="dt-name">{t(`dtName_${code}`)}</span>
          <span className="dt-file">{latest ? latest.name : t('dtNoFile')}
            {tile.files.length > 1 && <span className="dt-more"> +{tile.files.length - 1}</span>}</span>
        </button>
        {tile.files.length > 0 && (
          <button type="button" className="dt-manage" aria-expanded={managed === code}
                  onClick={() => setManaged(m => (m === code ? null : code))}>{t('dtManage')}</button>
        )}
        {managed === code && (
          <ul className="dt-list">
            {tile.files.map(f => (
              <li key={`${f.source}-${f.id}`}>
                <button type="button" className="link-btn" disabled={!f.url}
                        onClick={() => open(f)}>{f.name}</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return (
    <section className="panel dt-panel" aria-label={t('dtTitle')}>
      <h3 className="dt-head">
        {t('dtTitle')}
        <span className="muted"> {result.loaded}/{result.total} {t('dtLoaded')}</span>
        {result.missing.length > 0 && (
          <span className="dt-missing"> · {t('dtMissing')}: {result.missing.map(c => t(`dtName_${c}`)).join(', ')}</span>
        )}
      </h3>
      {error && <p className="error">{error}</p>}
      <div className="dt-groups">
        {GROUPS.map(g => (
          <div key={g.codes.join('-')} className="dt-group">
            {g.codes.map((code, i) => (
              <span key={code} className="dt-cell">
                {i > 0 && (g.link === 'pair'
                  ? <ArrowLeftRightIcon className="dt-link" size={16} aria-hidden="true" />
                  : <ArrowRightIcon className="dt-link" size={16} aria-hidden="true" />)}
                {tileView(code)}
              </span>
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}
