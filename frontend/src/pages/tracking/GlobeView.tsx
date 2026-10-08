import { CameraIcon } from 'lucide-react'
// Wirtualny globus 3D (styl Marble/Google Earth) — domyślny widok /sledzenie.
// Te same dane i warstwy co płaska mapa (TrackingPage): statki AIS + traile,
// porty + etykiety, fabryki dostawców, magazyny, kolory państw, terminator.
// three ładowane LENIWIE (dynamic import w efekcie) — ten sam wzorzec i chunk
// co panel pakowania kontenera (ContainerPacking). Kula = zdjęcie NASA Blue Marble
// (globeScene), ślady statków po wodzie (seaRoute — też leniwie).
import { useEffect, useRef, useState } from 'react'
import { useT } from '../../i18n'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { COUNTRIES, CPORTS_MINOR, HL, KEY_PORTS, PL_NAMES, WAREHOUSES } from './mapStatic'
import {
  canExportCanvas, declutterLabels, downloadCanvasPng, isFrontFacing,
  labelBox, latLonToVec3, thinByDistance, type LabelBox, type Vec3,
} from './globeMath'
import {
  addAtmosphere, addEarth, addLights, addStars, makeDotCanvas, makeFactoryCanvas,
  makeGhostCanvas, makeLabelCanvas, makeVesselCanvas, makeWindCanvas, trailPoints,
} from './globeScene'
import { createGlobeTiles } from './globeTiles'
import { createGlobeVector } from './globeVector'
import type { FactoryCluster } from './MapDecor'
import type { Vessel } from './types'
import { prefersReducedMotion } from '../../motion'
import { disposeThree } from '../../threeDispose'

export interface RouteWeatherPoint {
  lat: number
  lon: number
  wind_kmh: number | null
  wind_dir: number | null
  wave_m: number | null
}

export interface GlobePoint {
  id: number
  container_no: string
  lat?: number
  lon?: number
  status: string
  location: string
  is_special?: boolean
}

interface GlobeProps {
  vessels: Vessel[]
  points: GlobePoint[]
  factories: FactoryCluster[]
  /* px/py świata (płaska projekcja) → z powrotem na lat/lon do kuli */
  containerPorts: { name: string; cc: string; lon: number; lat: number }[]
  statusColor: Record<string, string>
  showCountryColors: boolean
  showCountries: boolean
  showVessels: boolean
  showPortLabels: boolean
  showAllPorts: boolean
  showNames: boolean
  showTerminator: boolean
  showSatellite: boolean    // zdjęcie NASA zamiast mapy terenu
  /* warstwa Pogoda: wiatr/fala w punktach pozostałej trasy statków */
  showWeather: boolean
  routeWeather: RouteWeatherPoint[]
  /* replay rejsu: punkt trailu pod suwakiem (wspólne kontrolki z 2D) — null = wyłączony */
  replayPoint: [number, number] | null
  /* preset widoku (Europa/Azja/Suez/Cały glob): skok kamery; nowy obiekt = nowy skok */
  viewPreset?: { lat: number; lon: number; distMul: number } | null
  activeVesselId: number | null
  onVesselClick: (v: Vessel) => void
  onPointClick: (p: GlobePoint) => void
  onFactoryClick: (f: FactoryCluster) => void
}

export function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

const R = 100                 // promień globusa (jednostki sceny)

export default function GlobeView(props: GlobeProps) {
  const t = useT()
  const mountRef = useRef<HTMLDivElement>(null)
  // pozycja kamery przetrwa przebudowę sceny (odświeżenie danych co 5 min)
  const camState = useRef<{ pos: Vec3 } | null>(null)
  const webgl = hasWebGL()

  const {
    vessels, points, factories, containerPorts, statusColor,
    showCountryColors, showCountries, showVessels, showPortLabels, showAllPorts,
    showNames, showTerminator, showSatellite, showWeather, routeWeather,
    onVesselClick, onPointClick, onFactoryClick,
  } = props
  // callbacki przez ref — zmiana handlera nie przebudowuje całej sceny
  const handlers = useRef({ onVesselClick, onPointClick, onFactoryClick })
  handlers.current = { onVesselClick, onPointClick, onFactoryClick }
  // punkt replayu przez ref — suwak zmienia się co chwilę, a przebudowa całej sceny
  // przy każdym ticku suwaka byłaby nieakceptowalnie droga; pętla rAF czyta ref
  const replayRef = useRef<[number, number] | null>(null)
  replayRef.current = props.replayPoint
  // preset widoku przez ref — skok kamery bez przebudowy sceny (jak duch replayu)
  const presetRef = useRef<GlobeProps['viewPreset']>(null)
  presetRef.current = props.viewPreset
  // aktywny statek przez ref — klik podmienia teksturę jednego sprite'a, bez przebudowy sceny
  const activeRef = useRef<number | null>(null)
  activeRef.current = props.activeVesselId
  // eksport PNG: funkcja wystawiana przez efekt po zbudowaniu renderera
  const exportRef = useRef<(() => void) | null>(null)
  const [canExport, setCanExport] = useState(false)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !webgl) return
    let disposed = false
    let cleanup = () => {}
    Promise.all([
      import('three'),
      import('three/examples/jsm/controls/OrbitControls.js'),
      import('./seaRoute'),
    ]).then(([THREE, { OrbitControls }, { seaTrail }]) => {
      if (disposed || !mount) return
      const W = () => mount.clientWidth || 800
      const H = () => Math.max(320, Math.round(W() / 2))
      const renderer = new THREE.WebGLRenderer({ antialias: true })
      renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
      renderer.setSize(W(), H())
      mount.appendChild(renderer.domElement)

      const scene = new THREE.Scene()
      scene.background = new THREE.Color(0x04080f)

      addStars(THREE, scene)
      const camera = new THREE.PerspectiveCamera(45, W() / H(), 1, 5000)
      const p0 = camState.current?.pos ?? latLonToVec3(35, 40, R * 3.1)  // Europa/Azja w kadrze
      camera.position.set(p0[0], p0[1], p0[2])
      const controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = !prefersReducedMotion() // bezwładność kamery = ruch (UX-040)
      controls.dampingFactor = 0.07
      controls.rotateSpeed = 0.45
      controls.minDistance = R * 1.06      // zoom ~do poziomu portu
      controls.maxDistance = R * 5
      controls.enablePan = false
      controls.zoomSpeed = 0.8

      /* --- kula (foto NASA, leniwie) + światła/terminator + atmosfera --- */
      let dirty = true
      const layerOpts = { countryColors: showCountryColors, highlights: showCountries, satellite: showSatellite }
      const earth = addEarth(THREE, scene, renderer, R, layerOpts, () => { dirty = true })
      const lod = showSatellite ? createGlobeTiles(THREE, scene, renderer, R, () => { dirty = true }) : null  // kafelki zdjęcia
      const vec = createGlobeVector(THREE, scene, renderer, R, layerOpts, () => { dirty = true })  // z bliska mapa wektorowa
      addLights(THREE, scene, camera, showTerminator)
      addAtmosphere(THREE, scene, R)

      /* ---- markery + etykiety z cullingiem horyzontu/odległości ---- */
      const texCache = new Map<string, InstanceType<typeof THREE.CanvasTexture>>()
      const canvasTex = (key: string, make: () => HTMLCanvasElement) => {
        let tx = texCache.get(key)
        if (!tx) { tx = new THREE.CanvasTexture(make()); tx.colorSpace = THREE.SRGBColorSpace; texCache.set(key, tx) }
        return tx
      }
      // culling: obiekt + wektor pozycji + maks. odległość kamery, przy której go pokazujemy.
      // sx/sy: bazowa skala sprite'a — dla etykiet (isLabel) skalujemy ją z zoomem, żeby
      // przy oddaleniu tekst malał i przestawał na siebie nachodzić (dot/statek zostają stałe).
      const culled: { obj: InstanceType<typeof THREE.Object3D>; p: Vec3; maxDist: number
        sx?: number; sy?: number; pri?: number; centerY?: number }[] = []
      const clickables: InstanceType<typeof THREE.Sprite>[] = []
      // sizeAttenuation=false → skala sprite'a w jednostkach ekranu (stały rozmiar)
      const SPR = 0.058
      const addSprite = (
        p: Vec3, tx: InstanceType<typeof THREE.CanvasTexture>, wPx: number, hPx: number,
        opts: { maxDist?: number; click?: object; centerY?: number; lift?: number
          rot?: number; isLabel?: boolean; pri?: number } = {},
      ) => {
        const m = new THREE.SpriteMaterial({ map: tx, sizeAttenuation: false, depthTest: false })
        if (opts.rot != null) m.rotation = opts.rot
        const s = new THREE.Sprite(m)
        const lift = opts.lift ?? 1.004
        s.position.set(p[0] * lift, p[1] * lift, p[2] * lift)
        const sx = wPx * SPR / 32, sy = hPx * SPR / 32
        s.scale.set(sx, sy, 1)
        if (opts.centerY != null) s.center.set(0.5, opts.centerY)
        s.renderOrder = 10
        if (opts.click) { s.userData = opts.click; clickables.push(s) }
        // etykiety zapamiętują bazową skalę → updateCulling skaluje je z zoomem
        culled.push({ obj: s, p, maxDist: opts.maxDist ?? Infinity,
          ...(opts.isLabel ? { sx, sy, pri: opts.pri ?? 0, centerY: opts.centerY ?? 0.5 } : {}) })
        scene.add(s)
        return s
      }
      const addLabel = (
        lat: number, lon: number, text: string, px: number, color: string,
        opts: { maxDist?: number; weight?: number; dy?: number; pri?: number } = {},
      ) => {
        const canvas = makeLabelCanvas(text, px, color, opts.weight ?? 600)
        const tx = new THREE.CanvasTexture(canvas)
        tx.colorSpace = THREE.SRGBColorSpace
        addSprite(latLonToVec3(lat, lon, R), tx, canvas.width / 2, canvas.height / 2,
          { maxDist: opts.maxDist, centerY: opts.dy ?? -0.35, isLabel: true,
            // priorytet odkolizjonowania: domyślnie wg wielkości czcionki (porty docelowe
            // i magazyny są większe niż statki), z opcjonalnym boostem dla śledzonych
            pri: opts.pri ?? px })
      }

      /* porty kontenerowe ze słownika (fallback: statyczna lista z makiety) — Points */
      const allPorts = containerPorts.length ? containerPorts : CPORTS_MINOR
      if (showAllPorts) {
        const pos = new Float32Array(allPorts.length * 3)
        allPorts.forEach((p, i) => {
          const v = latLonToVec3(p.lat, p.lon, R * 1.001)
          pos[i * 3] = v[0]; pos[i * 3 + 1] = v[1]; pos[i * 3 + 2] = v[2]
        })
        const g = new THREE.BufferGeometry()
        g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
        scene.add(new THREE.Points(g, new THREE.PointsMaterial({
          color: 0x8fd3e8, size: 3.4, sizeAttenuation: false,
        })))
        // etykiety tylko blisko + rozrzedzone (culling kolizji)
        for (const i of thinByDistance(allPorts, 2.2)) {
          const p = allPorts[i]
          addLabel(p.lat, p.lon, p.name, 9, 'rgba(190,225,240,.95)', { maxDist: R * 1.55, weight: 500 })
        }
      }

      /* kluczowe porty: kropki w kolorze roli + etykieta od średniego zoomu */
      if (showPortLabels) for (const p of KEY_PORTS) {
        const col = p.role === 'dest' ? '#ffd166' : p.role === 'origin' ? '#e9a13b' : '#2f8ef7'
        addSprite(latLonToVec3(p.lat, p.lon, R), canvasTex(`dot-${col}`, () => makeDotCanvas(col)), 9, 9)
        addLabel(p.lat, p.lon, p.name.toUpperCase(), p.role === 'dest' ? 12 : 10.5,
          p.role === 'dest' ? '#ffe9ae' : '#eaf4ff', { maxDist: R * 3.4, weight: 700 })
      }

      /* magazyny docelowe */
      if (showPortLabels) for (const w of WAREHOUSES) {
        addSprite(latLonToVec3(w.lat, w.lon, R), canvasTex(`wh-${w.color}`, () => makeDotCanvas(w.color)), 10, 10)
        addLabel(w.lat, w.lon, w.name, 10.5, w.color, { maxDist: R * 3.4, weight: 700 })
      }

      /* nazwy krajów — HL zawsze, reszta przy zbliżeniu */
      if (showNames) for (const c of COUNTRIES) {
        const nm = PL_NAMES[c.name]
        if (!nm || !c.cx) continue
        const tier = HL[c.id]
        // cx/cy są w px świata → z powrotem na lat/lon
        const lat = 90 - c.cy / WORLD_H * 180
        const lon = c.cx / WORLD_W * 360 - 180
        addLabel(lat, lon, nm.toUpperCase(), tier ? 10.5 : 9,
          tier === 'dest' ? 'rgba(255,233,174,.95)' : tier ? 'rgba(222,236,255,.9)' : 'rgba(208,226,248,.7)',
          { maxDist: tier ? Infinity : R * 2.1, weight: 700, dy: 0.5 })
      }

      /* fabryki dostawców — zielony romb (klaster) + licznik; te same klastry co 2D */
      const factTex = canvasTex('factory', makeFactoryCanvas)
      for (const f of factories) {
        // x/y w px świata → lat/lon
        const lat = 90 - f.y / WORLD_H * 180
        const lon = f.x / WORLD_W * 360 - 180
        addSprite(latLonToVec3(lat, lon, R), factTex, 10, 10, { click: { type: 'factory', f } })
        if (f.city) addLabel(lat, lon, `${f.city} · ${f.suppliers.length}`, 9,
          'rgba(196,238,180,.95)', { maxDist: R * 1.8 })
      }

      /* kontenery (punkty trackingu) — kolor statusu, klik = tooltip jak 2D */
      for (const pt of points) {
        if (pt.lat == null || pt.lon == null) continue
        const col = statusColor[pt.status] ?? '#3b82f6'
        // „specjalny": czerwony obrys + większy sprite — wyróżnienie do śledzenia
        const tex = pt.is_special
          ? canvasTex(`dot-${col}-sp`, () => makeDotCanvas(col, '#d92d20'))
          : canvasTex(`dot-${col}`, () => makeDotCanvas(col))
        addSprite(latLonToVec3(pt.lat, pt.lon, R), tex,
          pt.is_special ? 15 : 12, pt.is_special ? 15 : 12, { click: { type: 'point', pt } })
      }

      /* statki AIS: billboard + trail PO WODZIE (seaRoute) + etykieta nazwy */
      const vesselSprites = new Map<number, InstanceType<typeof THREE.Sprite>>()
      if (showVessels) {
        const trailMat = new THREE.LineBasicMaterial({
          color: 0xf5a623, transparent: true, opacity: 0.55 })
        for (const v of vessels) {
          if (v.lat == null || v.lon == null) continue
          const path: [number, number][] = [...v.trail, [v.lat, v.lon]]
          // kolejne fixy łączy trasa po wodzie (A* po masce lądu), nie goły łuk —
          // odcinek bez drogi po wodzie przerywa linię zamiast iść po lądzie
          for (const line of seaTrail(path)) {
            const g = new THREE.BufferGeometry()
            g.setAttribute('position', new THREE.BufferAttribute(
              new Float32Array(trailPoints(line, R * 1.003).flat()), 3))
            scene.add(new THREE.Line(g, trailMat))
          }
          vesselSprites.set(v.id, addSprite(latLonToVec3(v.lat, v.lon, R),
            canvasTex('vessel', () => makeVesselCanvas(false)), 14, 14, { click: { type: 'vessel', v } }))
          // ★ tuż nad statkiem: wiezie mój obserwowany kontener (kolor trasy AIS); nazwa wyżej
          const starred = !!v.watched?.length
          addLabel(v.lat, v.lon, v.name, 9.5, '#eaf4ff', { maxDist: R * 3.2, dy: starred ? -1.9 : -0.8 })
          if (starred) addLabel(v.lat, v.lon, '★', 14, 'rgb(245,166,35)', { dy: -0.35, pri: 99 })
        }
      }

      /* pogoda na pozostałej trasie: strzałki wiatru (DOKĄD wieje) + wysokość fali */
      if (showWeather) for (const w of routeWeather) {
        if (w.wind_dir == null && w.wave_m == null) continue
        const danger = (w.wind_kmh ?? 0) > 50
        if (w.wind_dir != null) {
          // rotation sprite'a jest przeciwna do ruchu wskazówek; kierunek meteo = skąd wieje
          addSprite(latLonToVec3(w.lat, w.lon, R), canvasTex(`wind-${danger}`,
            () => makeWindCanvas(danger)), 11, 11,
            { rot: -((w.wind_dir + 180) % 360) * Math.PI / 180, maxDist: R * 4 })
        }
        if (w.wave_m != null) {
          addLabel(w.lat, w.lon, `🌊 ${w.wave_m} m`, 8.5,
            danger ? '#ffb4ab' : 'rgba(170,220,240,.9)', { maxDist: R * 2.6 })
        }
      }

      /* duch replayu (wspólny suwak z 2D) — pozycja czytana z ref w pętli rAF,
         żeby przewijanie suwaka nie przebudowywało sceny */
      const ghost = new THREE.Sprite(new THREE.SpriteMaterial({
        map: canvasTex('ghost', makeGhostCanvas), sizeAttenuation: false, depthTest: false,
      }))
      ghost.scale.set(20 * SPR / 32, 20 * SPR / 32, 1)
      ghost.renderOrder = 11
      ghost.visible = false
      scene.add(ghost)
      let lastGhost: [number, number] | null = null
      let lastActive: number | null = null
      const markVessel = (id: number | null, on: boolean) => {
        const s = id == null ? undefined : vesselSprites.get(id)
        if (!s) return
        s.material.map = canvasTex(on ? 'vessel-a' : 'vessel', () => makeVesselCanvas(on))
        s.scale.set((on ? 17 : 14) * SPR / 32, (on ? 17 : 14) * SPR / 32, 1)
      }
      let lastPreset: GlobeProps['viewPreset'] = null

      /* ---- culling: horyzont (dot z kierunkiem kamery) + progi odległości ---- */
      const _pv = new THREE.Vector3()   // reużywany do rzutu etykiet na ekran
      const updateCulling = () => {
        const c: Vec3 = [camera.position.x, camera.position.y, camera.position.z]
        const dist = camera.position.length()
        // skala etykiet zależna od zoomu: blisko (≈R*1.06) pełny rozmiar, daleko (≈R*5)
        // ~0.55× — tekst maleje przy oddaleniu, więc nazwy przestają na siebie nachodzić
        const t = Math.min(1, Math.max(0, (dist - R * 1.06) / (R * 5 - R * 1.06)))
        const labelScale = 1.1 - 0.55 * t
        for (const e of culled) {
          e.obj.visible = dist <= e.maxDist && isFrontFacing(e.p, c, R)
          if (e.sx != null && e.obj.visible) {
            (e.obj as InstanceType<typeof THREE.Sprite>).scale.set(
              e.sx * labelScale, (e.sy ?? e.sx) * labelScale, 1)
          }
        }
        // odkolizjonowanie: rzut widocznych etykiet na ekran, ukryj nachodzące o niższym
        // priorytecie (porty docelowe/magazyny > statki). Bliżej środka ekranu = ważniejsze
        // przy remisie priorytetu → sortujemy wg odległości od kamery (bliżej = pierwsze).
        const vh = renderer.domElement.clientHeight, vw = renderer.domElement.clientWidth
        const labels = culled.filter(e => e.sx != null && e.obj.visible)
        labels.sort((a, b) =>
          camera.position.distanceToSquared(a.obj.position) -
          camera.position.distanceToSquared(b.obj.position))
        const boxes: LabelBox[] = labels.map(e => {
          _pv.copy(e.obj.position).project(camera)
          // B12: tekst wisi nad punktem (center.y < 0) → prostokąt przesunięty razem z nim
          return labelBox((_pv.x * 0.5 + 0.5) * vw, (-_pv.y * 0.5 + 0.5) * vh,
            (e.sx! * labelScale) * vh * 0.5, (e.sy ?? e.sx!) * labelScale * vh * 0.5,
            e.centerY ?? 0.5, e.pri ?? 0)
        })
        const hidden = declutterLabels(boxes)
        hidden.forEach(i => { labels[i].obj.visible = false })
      }
      updateCulling()
      // pierwsza klatka synchronicznie — bez czekania na rAF (ukryta karta go throttluje)
      controls.update()
      renderer.render(scene, camera)

      /* ---- klik: raycast po sprite'ach (statek / kontener / fabryka) ---- */
      const ray = new THREE.Raycaster()
      const ndc = new THREE.Vector2()
      let downAt: { x: number; y: number } | null = null
      const onDown = (e: PointerEvent) => { downAt = { x: e.clientX, y: e.clientY } }
      const onUp = (e: PointerEvent) => {
        if (!downAt || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 5) return
        const r = renderer.domElement.getBoundingClientRect()
        ndc.set((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
        ray.setFromCamera(ndc, camera)
        const hits = ray.intersectObjects(clickables.filter(s => s.visible), false)
        const u = hits[0]?.object?.userData as { type?: string; v?: Vessel; pt?: GlobePoint; f?: FactoryCluster } | undefined
        if (!u?.type) return
        if (u.type === 'vessel' && u.v) handlers.current.onVesselClick(u.v)
        else if (u.type === 'point' && u.pt) handlers.current.onPointClick(u.pt)
        else if (u.type === 'factory' && u.f) handlers.current.onFactoryClick(u.f)
      }
      renderer.domElement.addEventListener('pointerdown', onDown)
      renderer.domElement.addEventListener('pointerup', onUp)

      /* ---- pętla: render on demand + pauza gdy karta niewidoczna ---- */
      controls.addEventListener('change', () => { dirty = true })
      const observer = new ResizeObserver(() => {
        renderer.setSize(W(), H())
        camera.aspect = W() / H()
        camera.updateProjectionMatrix()
        dirty = true
      })
      observer.observe(mount)
      let raf = 0
      const loop = () => {
        raf = requestAnimationFrame(loop)
        // duch replayu: suwak zmienia ref bez przebudowy sceny
        // preset widoku: nowy obiekt (klik „Europa/Azja/…") → skok kamery nad region
        const vp = presetRef.current
        if (vp !== lastPreset) {
          lastPreset = vp
          if (vp) {
            const cp = latLonToVec3(vp.lat, vp.lon, R * vp.distMul)
            camera.position.set(cp[0], cp[1], cp[2])
            controls.update()
            dirty = true
          }
        }
        if (activeRef.current !== lastActive) {   // wyróżnienie klikniętego statku
          markVessel(lastActive, false); markVessel(activeRef.current, true)
          lastActive = activeRef.current; dirty = true
        }
        const rp = replayRef.current
        if (rp !== lastGhost) {
          lastGhost = rp
          if (rp) {
            const gp = latLonToVec3(rp[0], rp[1], R * 1.006)
            ghost.position.set(gp[0], gp[1], gp[2])
            ghost.visible = true
          } else {
            ghost.visible = false
          }
          dirty = true
        }
        const moving = controls.update()
        if (moving || dirty) {
          lod?.update(camera)
          earth.fade(vec.update(camera))
          updateCulling()
          renderer.render(scene, camera)
          dirty = false
          camState.current = { pos: [camera.position.x, camera.position.y, camera.position.z] }
        }
      }
      const onVis = () => {
        if (document.hidden) { cancelAnimationFrame(raf); raf = 0 }
        else if (!raf) { dirty = true; loop() }
      }
      document.addEventListener('visibilitychange', onVis)
      if (!document.hidden) loop()

      /* eksport PNG: render synchroniczny tuż przed toBlob (patrz downloadCanvasPng) */
      exportRef.current = () => { controls.update(); renderer.render(scene, camera); downloadCanvasPng(renderer.domElement) }
      setCanExport(canExportCanvas(renderer.domElement))

      cleanup = () => {
        exportRef.current = null
        cancelAnimationFrame(raf)
        document.removeEventListener('visibilitychange', onVis)
        renderer.domElement.removeEventListener('pointerdown', onDown)
        renderer.domElement.removeEventListener('pointerup', onUp)
        observer.disconnect()
        controls.dispose(); earth.dispose(); lod?.dispose(); vec.dispose()
        disposeThree(scene, renderer, texCache.values())   // geometrie/materiały/tekstury + kontekst
        texCache.clear()
        if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
      }
    })
    return () => { disposed = true; cleanup() }
    // przebudowa przy zmianie danych/warstw (rodzic memoizuje tablice!); kamera przeżywa w camState
  }, [vessels, points, factories, containerPorts, statusColor, showCountryColors,
    showCountries, showVessels, showPortLabels, showAllPorts, showNames,
    showTerminator, showSatellite, showWeather, routeWeather, webgl])

  if (!webgl) {
    return (
      <div className="globe-wrap" data-testid="globe-fallback"
           style={{ display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>
        {t('globeNoWebgl')}
      </div>
    )
  }
  return (
    <div style={{ position: 'relative' }}>
      <div ref={mountRef} className="globe-wrap" data-testid="globe-scene" />
      {canExport && (
        <button className="btn small secondary" data-testid="globe-export"
                title={t('exportPng')} aria-label={t('exportPng')}
                // B10: pod przełącznikiem 2D/3D (.map-mode-toggle: left/top 12px, ~31px wys.) — wcześniej
                // leżał dokładnie pod nim i wystawał jako biały prostokąt
                style={{ position: 'absolute', left: 12, top: 52 }}
                onClick={() => exportRef.current?.()}>
          <CameraIcon size={14} />
        </button>
      )}
    </div>
  )
}
