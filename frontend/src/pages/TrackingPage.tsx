import { GlobeIcon, MapIcon, SatelliteIcon } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { WORLD_W } from '../worldmap'
import { useVisibleInterval } from '../useVisibleInterval'
import { EmptyState, LoadError, Skeleton } from '../feedback'
import VesselCard from './tracking/VesselCard'
import VesselsTable from './tracking/VesselsTable'
import { ReplayControls, useVesselReplay } from './tracking/VesselReplay'
import type { FactoryCluster } from './tracking/MapDecor'
import { readMapMode, replayPointAt, storeMapMode, type MapMode, type ViewPreset } from './tracking/globeMath'
import type { Vessel } from './tracking/types'
import FlatMap from './tracking/FlatMap'
import { MapLayersPanel, MapLegendGlass, useMapLayers } from './tracking/MapLayers'
import { useMapView } from './tracking/useMapView'
import {
  FactoryPopup, PointTooltip, PortChips, StatusLegend, TrackedContainersTable,
} from './tracking/TrackingPanels'
import {
  clusterPoints, COMPANY_FILL, factoryClusters, keyPortStats, project, readMapPalette,
  type ContainerPortPos, type MapData, type MapPoint, type PortCongestion, type SupplierRow,
  type VesselWeather,
} from './tracking/trackingModel'
import { PageHeader } from '../PageHeader'

// globus 3D leniwie — three zostaje w tym samym osobnym chunku co panel pakowania
const GlobeView = lazy(() => import('./tracking/GlobeView'))

export default function TrackingPage() {
  const t = useT()
  const user = useUser()
  const navigate = useNavigate()
  // globus: kolory statusów z tokenów ciemnego motywu (canvas potrzebuje wartości, nie var())
  const mapStatusColor = useMemo(() => readMapPalette().status, [])
  const [data, setData] = useState<MapData | null>(null)
  const [active, setActive] = useState<MapPoint | null>(null)
  // na dotyku/klawiaturze tap/Enter „przypina" tooltip (hover go tylko podgląda)
  const [pinned, setPinned] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  // pusty stan (C30): bez danych globus zwinięty; user może go jednak rozwinąć
  const [showMapAnyway, setShowMapAnyway] = useState(false)
  const isAdmin = user?.role === 'admin'
  // F1: guard przed setState po odmontowaniu (odpowiedzi API po wyjściu ze strony)
  const mounted = useRef(true)
  // StrictMode odpala efekt mount→cleanup→mount: bez ponownego `= true` flaga
  // zostawała false na zawsze i WSZYSTKIE odpowiedzi API były odrzucane (pusta mapa)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  const [vessels, setVessels] = useState<Vessel[]>([])
  const [vesselsError, setVesselsError] = useState(false)
  const [activeVessel, setActiveVessel] = useState<Vessel | null>(null)
  // W7: strażnik kolejności — starsza odpowiedź (interval load) nie może
  // nadpisać nowszej; ten sam wzorzec co loadSeq w ContainerPage
  const loadSeq = useRef(0)
  const [weather, setWeather] = useState<Record<number, VesselWeather>>({})
  const [congestion, setCongestion] = useState<PortCongestion[]>([])
  const layers = useMapLayers()
  // globus 3D (Marble) domyślny; wybór 2D/3D zapamiętany w localStorage
  const [mapMode, setMapMode] = useState<MapMode>(readMapMode)
  const switchMode = (m: MapMode) => { setMapMode(m); storeMapMode(m) }
  // preset widoku globu (WIDOK: Europa/Azja/Suez/Cały glob) — nowy obiekt = nowy skok
  const [viewPreset, setViewPreset] = useState<ViewPreset | null>(null)
  // fabryki dostawców: słownik z importu LFA1 (raz na wejście — dane zmieniają się rzadko)
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([])
  const [activeFactory, setActiveFactory] = useState<FactoryCluster | null>(null)
  useEffect(() => {
    api.get<SupplierRow[]>('/api/suppliers')
      .then(list => { if (mounted.current && Array.isArray(list)) setSuppliers(list) })
      .catch(() => {})   // warstwa dekoracyjna — brak słownika nie psuje mapy
  }, [])
  // warstwa „Wszystkie porty kontenerowe": słownik z importu (tylko ze współrzędnymi).
  // Pusto (nie zaimportowano) → MapDecor używa statycznej listy z makiety (fallback).
  const [containerPorts, setContainerPorts] = useState<ContainerPortPos[]>([])
  useEffect(() => {
    api.get<{ code: string; name: string; country_code: string; lat: number; lon: number }[]>(
      '/api/container-ports?with_coords=true')
      .then(list => {
        if (mounted.current && Array.isArray(list)) {
          setContainerPorts(list.map(p => ({ name: p.name, cc: p.country_code, lon: p.lon, lat: p.lat })))
        }
      })
      .catch(() => {})   // warstwa dekoracyjna — fallback na statyczną listę
  }, [])
  // zoom/pan mapy 2D (viewBox, wheel, pomiar szerokości SVG)
  const mv = useMapView()
  const { view, setView } = mv
  const replay = useVesselReplay()
  useEffect(() => { replay.setOpen(false); replay.setIndex(0) }, [activeVessel?.id])   // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    const seq = ++loadSeq.current
    setLoadError('')
    api.get<MapData>('/api/tracking/map').then(d => { if (mounted.current && seq === loadSeq.current) { setData(d); setLoading(false) } })
      .catch(err => { if (mounted.current && seq === loadSeq.current) { setLoadError(errorMessage(err)); setLoading(false) } })
    // warstwa AIS jest niezależna od trackingu kontenerów — jej błąd nie psuje mapy
    api.get<PortCongestion[]>('/api/tracking/congestion')
      .then(c => { if (mounted.current && seq === loadSeq.current && Array.isArray(c)) setCongestion(c) })
      .catch(() => {})   // trend dekoracyjny — brak danych nie psuje mapy
    api.get<({ vessel_id: number } & VesselWeather)[]>('/api/tracking/weather')
      .then(w => { if (mounted.current && seq === loadSeq.current && Array.isArray(w))
        setWeather(Object.fromEntries(w.map(x => [x.vessel_id, x]))) })
      // dekoracyjne — brak pogody nie blokuje mapy, ale błąd niech zostawi ślad w konsoli
      .catch(err => console.warn('tracking/weather fetch failed', err))
    api.get<Vessel[]>('/api/tracking/vessels')
      // Array.isArray: tarcza na nieoczekiwany kształt odpowiedzi (proxy/błąd HTML)
      // czytelność tabeli: opóźnione na górze, potem z pozycją, „uczące się" na dole
      .then(v => { if (mounted.current && seq === loadSeq.current && Array.isArray(v)) {
        setVesselsError(false)
        setVessels([...v].sort((a, b) => (b.delayed - a.delayed)
          || Number(b.eta_alert) - Number(a.eta_alert)
          || Number(b.predicted_late) - Number(a.predicted_late)
          || Number(b.lat != null) - Number(a.lat != null)
          || a.name.localeCompare(b.name)))
      } })
      // W8: awaria warstwy AIS nie może zniknąć w ciszy — user widzi pusty statek bez wyjaśnienia
      .catch(() => { if (mounted.current && seq === loadSeq.current) setVesselsError(true) })
  }, [])
  useEffect(() => { load() }, [load])
  // widok deklaruje automatyczne odświeżanie — cyklicznie pobieramy świeże pozycje (widoczna karta)
  useVisibleInterval(load, 5 * 60 * 1000)

  // klastrowanie zależne od zoomu: punkty bliżej niż ~16 px ekranu zlewają się
  // w jeden badge z licznikiem (przy dużym zbliżeniu rozpadają się na pojedyncze)
  const clusterDist = 16 * (view.w / (mv.svgW || WORLD_W))
  const { grouped, pointClusterKey } = clusterPoints(data?.points ?? [], clusterDist)
  const { portCounts, portAnchored, chipPorts } = keyPortStats(data?.points ?? [], vessels)
  // nic do pokazania na mapie (ani kontenera z pozycją, ani statku) → pusty stan zamiast globusa;
  // awaria warstwy AIS to nie „brak statków" — wtedy mapa zostaje (z komunikatem błędu)
  const mapHidden = !!data && data.tracked === 0 && !showMapAnyway && !vesselsError
    && !vessels.some(v => v.lat != null && v.lon != null)
  // tablice dla globusa memoizowane: to zależności efektu budującego scenę WebGL — nowa
  // tablica przy każdym renderze (suwak replayu, klik statku) przebudowywała cały globus
  const factories = useMemo(() => layers.showSuppliers ? factoryClusters(suppliers) : [],
    [layers.showSuppliers, suppliers])
  const globeVessels = useMemo(() => vessels.filter(v => v.lat != null && v.lon != null), [vessels])
  const globePoints = useMemo(() => data?.points ?? [], [data])
  const routeWeather = useMemo(() => layers.showWeather
    ? Object.values(weather).flatMap(w => w.route ?? []) : [], [layers.showWeather, weather])
  const onFactoryClick = (f: FactoryCluster) => {
    if (f.suppliers.length === 1) navigate(`/dostawcy/${f.suppliers[0].id}`)
    else { setActive(null); setActiveVessel(null); setActiveFactory(f) }
  }

  return (
    <main className="page">
      <PageHeader title={t('trackingMap')} subtitle={t('mapAutoRefresh')} />

      {loading && !data && <Skeleton rows={4} />}
      {!loading && loadError && !data && <LoadError message={loadError} onRetry={load} />}

      <PortChips chipPorts={chipPorts} portAnchored={portAnchored} portCounts={portCounts}
                 congestion={congestion} onZoom={mv.zoomToPort} />
      {data && data.tracked === 0 && (
        <EmptyState icon={SatelliteIcon}
                    title={data.total === 0 ? t('mapNoContainers') : t('mapNoPositions')}
                    hint={mapHidden ? t('mapEmptyHint') : undefined}>
          {mapHidden && (
            <button className="btn secondary" onClick={() => setShowMapAnyway(true)}>
              <GlobeIcon size={14} /> {t('mapShowAnyway')}
            </button>
          )}
        </EmptyState>
      )}

      {!mapHidden && <>
      {/* C7: wspólny baner błędu nad mapą (zawija tekst, ma „Spróbuj ponownie”) — dawny szary pasek
          mono na mapie był ucięty na telefonie i zasłaniał przycisk 2D */}
      {vesselsError && <div className="map-layer-error"><LoadError message={t('aisLayerError')} onRetry={load} /></div>}
      <div className="map-wrap panel" style={{ padding: 0 }}>
        {mapMode === '3d' && (
          <Suspense fallback={<div className="globe-wrap" />}>
            <GlobeView
              vessels={globeVessels}
              points={globePoints}
              factories={factories}
              containerPorts={containerPorts}
              statusColor={mapStatusColor}
              showCountryColors={layers.showCountryColors}
              showCountries={layers.showCountries}
              showVessels={layers.showVessels}
              showPortLabels={layers.showPortLabels}
              showAllPorts={layers.showAllPorts}
              showNames={layers.showNames}
              showTerminator={layers.showTerminator}
              showSatellite={layers.showSatellite}
              showWeather={layers.showWeather}
              routeWeather={routeWeather}
              replayPoint={activeVessel && replay.open
                ? replayPointAt(activeVessel.trail, replay.index)
                : null}
              viewPreset={viewPreset}
              activeVesselId={activeVessel?.id ?? null}
              onVesselClick={v => { setActive(null); setPinned(false); setActiveFactory(null)
                setActiveVessel(av => av?.id === v.id ? null : v) }}
              onPointClick={p => {
                const full = data?.points.find(x => x.id === p.id)
                if (full) { setActiveVessel(null); setActiveFactory(null); setActive(full); setPinned(true) }
              }}
              onFactoryClick={onFactoryClick} />
          </Suspense>
        )}
        {mapMode === '2d' && (
          <FlatMap mv={mv} layers={layers} grouped={grouped} vessels={vessels} weather={weather}
                   active={active} setActive={setActive} pinned={pinned} setPinned={setPinned}
                   activeVessel={activeVessel} setActiveVessel={setActiveVessel}
                   replayOpen={replay.open} replayIndex={replay.index}
                   portCounts={portCounts} containerPorts={containerPorts}
                   factories={factories} onFactoryClick={onFactoryClick} />
        )}
        {/* przełącznik 2D/3D — róg mapy, wybór zapamiętany w localStorage */}
        <button className="map-mode-toggle"
                title={mapMode === '3d' ? t('mapMode2d') : t('mapMode3d')}
                onClick={() => switchMode(mapMode === '3d' ? '2d' : '3d')}>
          {mapMode === '3d' ? <><MapIcon size={14} /> 2D</> : <><GlobeIcon size={14} /> 3D</>}
        </button>
        {/* warstwy + legenda w jednej kolumnie: legenda nie przykrywa warstw (C30, 1366 px) */}
        <div className="map-side">
          <MapLayersPanel layers={layers} mapMode={mapMode} setViewPreset={setViewPreset} />
          <MapLegendGlass />
        </div>
        {/* zoombar (makieta) — lewy dolny róg; globus zoomuje kółkiem/OrbitControls */}
        {mapMode === '2d' && <div className="map-zoombar">
          <button title={t('mapZoomIn')} onClick={() => mv.zoomCenter(1 / 1.7)}>+</button>
          <button title={t('mapZoomOut')} onClick={() => mv.zoomCenter(1.7)}>−</button>
          {view.w < WORLD_W && (
            <button className="wide map-zoom-reset"
                    onClick={() => setView({ x: 0, y: 0, w: WORLD_W })}>
              ⤢ {t('mapResetZoom')}
            </button>
          )}
        </div>}
        {activeFactory && <FactoryPopup factory={activeFactory} onClose={() => setActiveFactory(null)} />}
        {activeVessel && (
          <VesselCard vessel={activeVessel} companyColor={COMPANY_FILL}
                      weather={weather[activeVessel.id]}
                      canEdit={user?.role === 'admin' || user?.role === 'logistics'}
                      isAdmin={isAdmin}
                      onClose={() => setActiveVessel(null)}
                      onOpenContainer={id => navigate(`/kontenery/${id}`)}>
            <ReplayControls vessel={activeVessel} open={replay.open} setOpen={replay.setOpen}
                            index={replay.index} setIndex={replay.setIndex} />
          </VesselCard>
        )}
        {active && (() => {
          const key = pointClusterKey.get(active.id)
          const clusterSize = key ? grouped.get(key)?.length ?? 1 : 1
          return <PointTooltip active={active} pinned={pinned} clusterSize={clusterSize}
                               onClose={() => { setPinned(false); setActive(null) }} />
        })()}
      </div>

      <StatusLegend data={data} />
      </>}

      <VesselsTable vessels={vessels} activeVessel={activeVessel} setActiveVessel={setActiveVessel}
                    setActive={setActive} setPinned={setPinned} view={view} setView={setView}
                    project={project} />

      {data && data.points.length + data.unlocated.length > 0 && <TrackedContainersTable data={data} />}
    </main>
  )
}
