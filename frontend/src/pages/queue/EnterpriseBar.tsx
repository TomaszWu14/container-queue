import { FlagIcon, StarIcon, XIcon } from 'lucide-react'
// Kolejka: wiersz 2 (36px) — zakładki widoków z licznikami + zapisane widoki po lewej; zakres,
// chipy filtrów, „+ Filtr", Wyczyść i Grupuj po prawej. Breadcrumb/H1/pasek KPI usunięte
// (liczby są w zakładkach widoków).
import { useState } from 'react'
import type { ReactNode } from 'react'
import { TransportPick } from '../../TransportBadge'
import { useLocation } from 'react-router-dom'
import { useDismiss } from '../../ColumnFilter'
import { useT } from '../../i18n'
import { GROUP_MODES, QUEUE_VIEWS } from './enterprise'
import type { QueueView } from './enterprise'
import RangeControl from './RangeControl'
import SavedViewTabs, { sameSearch } from './SavedViewTabs'
import type { ViewPrefs } from './useViewPrefs'
import type { FilterOpts, QueueFilters } from './useQueueFilters'

type Chip = { key: string; label: string; onClear: () => void }

export function EnterpriseFilters({ f, opts, chips, archive, counts, prefs }: {
  f: QueueFilters
  opts: FilterOpts
  chips: Chip[]
  archive: boolean
  counts: Record<QueueView, number> | null  // null = błąd wczytania, bez fałszywych zer
  prefs: ViewPrefs
}) {
  const t = useT()
  const location = useLocation()
  // aktywny zapisany widok przejmuje podświetlenie od wbudowanej zakładki
  const savedActive = prefs.savedViews.some(v => sameSearch(location.search, v.search))
  return (
    <div className="kq-filters" aria-label={t('activeFilters')}>
      {/* filtry listy (bez paneli) → przyciski przełączające, nie role="tab" (axe: aria-required-children) */}
      <div className="kq-tabs" role="group" aria-label={t('kqViews')}>
        {QUEUE_VIEWS.map(v => (
          <button key={v} type="button" aria-pressed={!savedActive && f.view === v}
                  className={!savedActive && f.view === v ? 'active' : ''} onClick={() => f.setView(v)}>
            {v === 'mine' && <><StarIcon size={14} />{' '}</>}{t(`kqView_${v}`)} {counts && <span className={`kq-tab-n mono v-${v}${counts[v] ? '' : ' zero'}`}>{counts[v]}</span>}
          </button>
        ))}
        <SavedViewTabs p={prefs} />
      </div>
      <span className="spacer" />
      <RangeControl f={f} archive={archive} />
      <span className="kq-sep" aria-hidden="true" />
      {chips.map(chip => <FilterChip key={chip.key} label={chip.label} onClear={chip.onClear} />)}
      <AddFilter f={f} opts={opts} />
      {chips.length > 0 && (
        <button type="button" className="kq-clear" onClick={f.clearAllFilters}>{t('clearAllChips')}</button>
      )}
      <span className="kq-sep" aria-hidden="true" />
      {/* A15: etykieta + segment w jednym elemencie — przy zawijaniu paska idą razem */}
      <span className="kq-grp">
        <span className="kq-grp-label">{t('kqGroupBy')}:</span>
        <span className="seg" role="group" aria-label={t('kqGroupBy')} title={t('kqGroupBy')}>
          {GROUP_MODES.map(g => (
            <button key={g} type="button" className={prefs.groupBy === g ? 'active' : ''}
                    onClick={() => prefs.setGroupBy(g)}>{t(`kqGroup_${g}`)}</button>
          ))}
        </span>
      </span>
    </div>
  )
}

// chip „<klucz>: <b>wartość</b> ✕" — etykieta z activeFilterChips ma postać „klucz: wartość"
function FilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  const t = useT()
  const i = label.indexOf(': ')
  const body: ReactNode = i < 0 ? <b>{label}</b>
    : <><span className="kq-chip-k">{label.slice(0, i)}:</span> <b>{label.slice(i + 2)}</b></>
  return (
    <span className="kq-chip" title={label}>
      {body}
      <button type="button" className="chip-x" title={t('removeFilter')}
              aria-label={t('removeFilter')} onClick={onClear}><XIcon size={14} /></button>
    </span>
  )
}

// „+ Filtr" — popover z filtrami, które wcześniej siedziały w nagłówkach kolumn (URL = źródło prawdy)
function AddFilter({ f, opts }: { f: QueueFilters; opts: FilterOpts }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  useDismiss(open, () => setOpen(false))
  const lists: [string, string, (v: string) => void, { value: string; label: string }[]][] = [
    [t('status'), f.status, f.setStatus, opts.statusOpts],
    [t('customs'), f.customs, f.setCustoms, opts.customsOpts],
    [t('supplier'), f.supplierId, f.setSupplierId, opts.supplierOpts],
    [t('forwarder'), f.forwarderId, f.setForwarderId, opts.forwarderOpts],
    [t('warehouse'), f.warehouseId, f.setWarehouseId, opts.warehouseOpts],
  ]
  const texts: [string, string, (v: string) => void][] = [
    [t('vessel'), f.vessel, f.setVessel],
    [t('orderNumbers'), f.orderNo, f.setOrderNo],
    [t('sentNoCol'), f.sentNo, f.setSentNo],
  ]
  return (
    <span className="kq-addfilter" onClick={e => e.stopPropagation()}>
      <button type="button" className="kq-addfilter-btn" aria-expanded={open}
              onClick={() => setOpen(o => !o)}>+ {t('kqAddFilter')}</button>
      {open && (
        <div className="kq-filter-pop">
          {lists.filter(([, , , options]) => options.length > 0).map(([label, value, set, options]) => (
            <label key={label}>{label}
              <select value={value} onChange={e => set(e.target.value)}>
                <option value="">—</option>
                {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
          ))}
          <div className="kq-filter-field">{t('transport')}
            <TransportPick label={t('transport')} value={f.transport} onChange={f.setTransport} />
          </div>
          {texts.map(([label, value, set]) => (
            <label key={label}>{label}
              <input type="text" defaultValue={value}
                     onKeyDown={e => { if (e.key === 'Enter') set(e.currentTarget.value.trim()) }}
                     onBlur={e => set(e.target.value.trim())} />
            </label>
          ))}
          <label className="row" title={t('specialOnlyHint')}>
            <input type="checkbox" checked={f.specialOnly} onChange={e => f.setSpecialOnly(e.target.checked)} />
            <FlagIcon size={14} /> {t('specialOnly')}
          </label>
        </div>
      )}
    </span>
  )
}
