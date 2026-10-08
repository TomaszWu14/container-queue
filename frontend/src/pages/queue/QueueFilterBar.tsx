// Wiersz 1 kolejki (prawa część): wyszukiwarka (200→360px po focusie, skróty „/" i Ctrl+K),
// przełącznik edycji z kłódką, ikony Widok / Eksport, „+ Dodaj" i menu „⋯" (Wyczyść kolejkę,
// Załóż zlecenie; <1280px także Widok/Eksport/Edycja). Akcje na zaznaczeniu → BulkActionBar.
import { useEffect, useRef, useState } from 'react'
import { downloadFile, errorMessage } from '../../api'
import { useDismiss } from '../../ColumnFilter'
import { todayISO } from '../../dates'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import { LockIcon } from './cells'
import type { Module } from './config'
import type { QueueFilters } from './useQueueFilters'
import type { QueueMove } from './useQueueMove'
import type { ViewPrefs } from './useViewPrefs'
import SearchSuggest, { type Suggestion } from './SearchSuggest'
import ViewMenu, { ViewOptions } from './ViewControls'
import { Download, Ellipsis, Eraser, Package } from 'lucide-react'

// decyzja 17 — eksport bieżącego widoku (z filtrami, tak jak lista) vs cała kolejka
// (tylko zakładka/spółka/magazyn/tranzyt — bez filtrów kolumnowych i wyszukiwarki).
export function useQueueExport(viewParams: () => URLSearchParams, allParams: () => URLSearchParams) {
  const t = useT()
  const { showToast } = useToast()
  const [exportOpen, setExportOpen] = useState(false)
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState(false)
  const run = async (params: URLSearchParams, name: string) => {
    if (exporting) return
    setExporting(true)
    try {
      setExportError('')
      await downloadFile(`/api/containers/export/xlsx?${params}`, `${name}_${todayISO()}.xlsx`)
      showToast(t('toastExported'))
    } catch (err) {
      setExportError(errorMessage(err))
    } finally {
      setExporting(false)
    }
  }
  const exportXlsx = () => run(viewParams(), 'kolejka')
  const exportXlsxAll = () => run(allParams(), 'kolejka_cala')
  useDismiss(exportOpen, () => setExportOpen(false))
  return { exportOpen, setExportOpen, exportError, exporting, exportXlsx, exportXlsxAll }
}

export type QueueExport = ReturnType<typeof useQueueExport>

// „/" i Ctrl+K poza polami edycji → fokus wyszukiwarki kolejki. Nasłuch w fazie capture na
// window wyprzedza globalną paletę Ctrl+K (GlobalSearch), więc na kolejce wygrywa jej pole.
function isEditable(el: EventTarget | null) {
  const e = el as HTMLElement | null
  return !!e && (e.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName))
}
function useSearchShortcut(focus: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isEditable(e.target)) return
      const ctrlK = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'
      if (!ctrlK && !(e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey)) return
      e.preventDefault()
      e.stopPropagation()
      focus()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [focus])
}

export default function QueueFilterBar(p: {
  f: QueueFilters
  mv: QueueMove
  prefs: ViewPrefs
  ex: QueueExport
  module: Module
  moduleCode?: string
  archive: boolean
  canEdit: boolean
  isAdmin: boolean
  loadError: string
  onFound: () => void
  onClearQueue: () => void
  onAdd: () => void
  onPickContainer: (s: Suggestion) => void
}) {
  const t = useT()
  const { f, mv, ex, archive, canEdit } = p
  const ref = useRef<HTMLDivElement>(null)
  const focusRef = useRef(() => ref.current?.querySelector<HTMLInputElement>('input.qsearch')?.focus())
  useSearchShortcut(focusRef.current)
  const [moreOpen, setMoreOpen] = useState(false)
  useDismiss(moreOpen, () => setMoreOpen(false))

  const editable = canEdit && !archive
  const canFound = editable && (p.module === 'borealis' || p.module === 'cobalt')
  const canClear = p.isAdmin && !archive && !!p.moduleCode
  const lockTitle = mv.moveUnlocked ? t('kqEditOnHint') : t('kqEditOffHint')
  const toggleEdit = () => mv.setMoveUnlocked(v => !v)
  const exportItems = (close: () => void) => (
    <>
      <button type="button" disabled={ex.exporting} onClick={() => { ex.exportXlsx(); close() }}>
        {t('exportView')}
      </button>
      <button type="button" disabled={ex.exporting} onClick={() => { ex.exportXlsxAll(); close() }}>
        {t('exportAll')}
      </button>
    </>
  )

  return (
    <div className="kq-actions" ref={ref} data-tour="filtry">
      <SearchSuggest value={f.q} onChange={f.setQ} onPick={p.onPickContainer} placeholder={t('search')}
                     completed={archive} />
      {ex.exportError && <span className="error">{ex.exportError}</span>}
      {p.loadError && <span className="error">{p.loadError}</span>}
      {editable && (
        // decyzja 10 — kłódka to ikona STANU (otwarta = edycja włączona), nie akcji
        <button type="button" className={`kq-ico lock-btn kq-wide${mv.moveUnlocked ? ' unlocked' : ''}`}
                aria-pressed={mv.moveUnlocked} aria-label={t('kqEdit')} title={lockTitle}
                onClick={toggleEdit}>
          <LockIcon open={mv.moveUnlocked} />
        </button>
      )}
      <span className="kq-wide"><ViewMenu p={p.prefs} /></span>
      <span className="kq-cols kq-wide" onClick={e => e.stopPropagation()}>
        <button type="button" className={`kq-ico export-btn${ex.exportOpen ? ' on' : ''}`}
                aria-label={t('exportXlsx')} title={t('exportXlsx')} aria-expanded={ex.exportOpen}
                disabled={ex.exporting} onClick={() => ex.setExportOpen(v => !v)}>
          <Download size={16} aria-hidden="true" />
        </button>
        {ex.exportOpen && <div className="export-menu">{exportItems(() => ex.setExportOpen(false))}</div>}
      </span>
      {/* D3: ręczne dodanie kontenera — jedyne wejście z UI (import pliku jest w adminie) */}
      {editable && (
        <button type="button" className="btn small kq-add" title={t('addContainer')} onClick={p.onAdd}>
          + {t('kqAdd')}
        </button>
      )}
      <span className="kq-cols" onClick={e => e.stopPropagation()}>
        <button type="button" className={`kq-ico kq-more-menu${canFound || canClear ? '' : ' kq-narrow'}${moreOpen ? ' on' : ''}`}
                aria-label={t('moreActions')} title={t('moreActions')} aria-expanded={moreOpen}
                onClick={() => setMoreOpen(o => !o)}><Ellipsis size={16} aria-hidden="true" /></button>
        {moreOpen && (
          <div className="kq-cols-pop kq-more-pop" role="menu" aria-label={t('moreActions')}>
            {editable && (
              <button type="button" className="kq-narrow" aria-pressed={mv.moveUnlocked} onClick={toggleEdit}>
                <LockIcon open={mv.moveUnlocked} /> {lockTitle}
              </button>
            )}
            <div className="kq-narrow kq-more-sec">
              <div className="kq-ct">{t('exportXlsx')}</div>
              {exportItems(() => setMoreOpen(false))}
            </div>
            <div className="kq-narrow kq-more-sec"><ViewOptions p={p.prefs} /></div>
            {canFound && <button type="button" onClick={() => { setMoreOpen(false); p.onFound() }}><Package size={16} aria-hidden="true" /> {t('foundOrder')}</button>}
            {canClear && (
              <button type="button" className="kq-danger" title={t('clearQueueHint')}
                      onClick={() => { setMoreOpen(false); p.onClearQueue() }}>
                <Eraser size={16} aria-hidden="true" /> {t('clearQueue')} ({p.moduleCode})
              </button>
            )}
          </div>
        )}
      </span>
    </div>
  )
}
