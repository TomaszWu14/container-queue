import { SunMoonIcon, WindIcon } from 'lucide-react'
import { useState, type Dispatch, type SetStateAction } from 'react'
import { useT } from '../../i18n'
import { VIEW_PRESETS, type MapMode, type ViewPreset } from './globeMath'
import { WAREHOUSES } from './mapStatic'

// Warstwy mapy trackingu (makieta Tracking.html: #layers) + legenda (#legend).
// Stan sesji, bez persist — wydzielone z TrackingPage.
export function useMapLayers() {
  const [showWeather, setShowWeather] = useState(false)
  const [showGrid, setShowGrid] = useState(false)
  // warstwy z makiety Tracking.html (stan sesji, bez persist)
  const [showCountries, setShowCountries] = useState(true)
  const [showVessels, setShowVessels] = useState(true)
  const [showPortLabels, setShowPortLabels] = useState(true)
  const [showAllPorts, setShowAllPorts] = useState(true)
  const [showNames, setShowNames] = useState(true)
  const [showSuppliers, setShowSuppliers] = useState(true)
  const [showCountryColors, setShowCountryColors] = useState(true)
  const [showTerminator, setShowTerminator] = useState(true)
  // domyślnie mapa terenu (wektor + rzeźba); zdjęcie NASA na życzenie (decyzja usera 2026-10-01)
  const [showSatellite, setShowSatellite] = useState(false)
  return {
    showWeather, setShowWeather, showGrid, setShowGrid,
    showCountries, setShowCountries, showVessels, setShowVessels,
    showPortLabels, setShowPortLabels, showAllPorts, setShowAllPorts,
    showNames, setShowNames, showSuppliers, setShowSuppliers,
    showCountryColors, setShowCountryColors, showTerminator, setShowTerminator,
    showSatellite, setShowSatellite,
  }
}

export type MapLayersState = ReturnType<typeof useMapLayers>

type Toggle = Dispatch<SetStateAction<boolean>>

function LayerCheck({ checked, set, children }: { checked: boolean; set: Toggle; children: React.ReactNode }) {
  return (
    <label>
      <input type="checkbox" checked={checked}
             onChange={() => set(v => !v)} /> {children}
    </label>
  )
}

/** Panel warstw (makieta: #layers) — szkło w prawym górnym rogu mapy. */
export function MapLayersPanel({ layers: l, mapMode, setViewPreset }: {
  layers: MapLayersState
  mapMode: MapMode
  setViewPreset: (p: ViewPreset) => void
}) {
  const t = useT()
  // B9: zwijany jak legenda — na telefonie (< 768 px) domyślnie zwinięty, globus widoczny
  const wide = typeof window !== 'undefined' && !!window.matchMedia?.('(min-width: 768px)').matches
  return (
    <details className="map-glass map-layers" open={wide}>
      <summary><b>{t('mapLayers')}</b></summary>
      <div className="map-layers-body">
      {mapMode === '3d' && (
        <div className="map-views">
          <b>{t('ctlView')}</b>
          <div className="map-views-btns">
            <button type="button" onClick={() => setViewPreset({ ...VIEW_PRESETS.europe })}>{t('viewEurope')}</button>
            <button type="button" onClick={() => setViewPreset({ ...VIEW_PRESETS.asia })}>{t('viewAsia')}</button>
            <button type="button" onClick={() => setViewPreset({ ...VIEW_PRESETS.suez })}>{t('viewSuez')}</button>
            <button type="button" onClick={() => setViewPreset({ ...VIEW_PRESETS.globe })}>{t('viewGlobe')}</button>
          </div>
        </div>
      )}
      <LayerCheck checked={l.showCountries} set={l.setShowCountries}>{t('mapCountries')}</LayerCheck>
      <LayerCheck checked={l.showVessels} set={l.setShowVessels}>{t('mapVesselsLayer')}</LayerCheck>
      <LayerCheck checked={l.showPortLabels} set={l.setShowPortLabels}>{t('mapPortLabels')}</LayerCheck>
      <LayerCheck checked={l.showAllPorts} set={l.setShowAllPorts}>{t('mapAllPorts')}</LayerCheck>
      <LayerCheck checked={l.showNames} set={l.setShowNames}>{t('mapCountryNames')}</LayerCheck>
      <LayerCheck checked={l.showSuppliers} set={l.setShowSuppliers}>{t('mapSuppliers')}</LayerCheck>
      <LayerCheck checked={l.showCountryColors} set={l.setShowCountryColors}>{t('mapCountryColors')}</LayerCheck>
      <LayerCheck checked={l.showSatellite} set={l.setShowSatellite}>{t('mapSatellite')}</LayerCheck>
      {mapMode === '3d' && (
        <LayerCheck checked={l.showTerminator} set={l.setShowTerminator}><SunMoonIcon size={14} /> {t('mapTerminator')}</LayerCheck>
      )}
      {mapMode === '2d' && (
        <LayerCheck checked={l.showGrid} set={l.setShowGrid}>{t('mapGrid')}</LayerCheck>
      )}
      {/* pogoda dostępna w obu trybach: 2D przy statkach+trasa, 3D punkty trasy */}
      <LayerCheck checked={l.showWeather} set={l.setShowWeather}><WindIcon size={14} /> {t('mapWeather')}</LayerCheck>
      </div>
    </details>
  )
}

/** Legenda (makieta #legend) — pod warstwami; zwijana (C30), rozwinięta tylko na szerokim ekranie. */
export function MapLegendGlass() {
  const t = useT()
  const wide = typeof window !== 'undefined' && !!window.matchMedia?.('(min-width: 1600px)').matches
  return (
    <details className="map-glass map-legend-glass" open={wide}>
      <summary><b>{t('mapLegend')}</b></summary>
      <div className="row"><span className="sw" /> {t('legendSeaRoute')}</div>
      <div className="row"><span className="dot" style={{ background: '#2f8ef7' }} /> {t('legendKeyPort')}</div>
      <div className="row"><span className="dot dest" /> {t('legendDestPort')}</div>
      <div className="row"><span className="sq" /> {t('legendCountryActive')}</div>
      <div className="row"><span className="dot term" /> {t('legendTerminal')}</div>
      <div className="row"><span className="fab" /> {t('legendFactory')}</div>
      <div className="row wh-head">{t('legendWarehouses')}</div>
      {WAREHOUSES.map(w => (
        <div className="row" key={w.id}>
          <span className="wh" style={{ background: w.color }} /> {w.name} · {w.alt ? t('legendWhTransit') : w.company}
        </div>
      ))}
    </details>
  )
}
