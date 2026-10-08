// Tło i kula globusa 3D: gwiazdy, Ziemia (foto NASA + połysk oceanu), światła
// (terminator dzień/noc albo „reflektor" od kamery), atmosfera, ślady statków po
// wodzie + canvasy 2D (tekstura kuli, sprite'y etykiet/kropek/statków/wiatru).
// three przychodzi z leniwego importu w GlobeView — tu tylko typy.
import { paintVectorRegion, TERRAIN_TEX_W, type VectorOpts } from './globeVector'
import { loadReliefFor, type LoadedRelief } from './reliefTiles'
import type { Camera, Scene, WebGLRenderer } from 'three'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { EARTH_PHOTO_URL } from './earthPhoto'
import { borderSegments, countryBorderLines } from './globeBorders'
import { greatCirclePoints, sunDirection, type Vec3 } from './globeMath'
import { COUNTRIES, countryFill, HL, HL_FILL, LAND_PATH } from './mapStatic'
import type { LL } from './seaRoute'

type Three = typeof import('three')

/** Gwiazdy równomiernie na dalekiej sferze. */
export function addStars(THREE: Three, scene: Scene) {
  const n = 1200
  const pos = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) {
    const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2
    const s = Math.sqrt(1 - u * u)
    pos[i * 3] = 1800 * s * Math.cos(a)
    pos[i * 3 + 1] = 1800 * u
    pos[i * 3 + 2] = 1800 * s * Math.sin(a)
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({
    color: 0xcfe0ff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0.75,
  })))
}

/** Kula Ziemi. Najpierw tekstura wektorowa (natychmiast), po wczytaniu zdjęcia
    NASA podmiana w tym samym canvasie + onUpdate (pętla renderuje on-demand).
    Kolory państw / HL to osobna przezroczysta powłoka NAD łatami LOD (globeTiles),
    granice — linie 3D z world-atlas 50m (globeBorders), ostre przy każdym zoomie.
    Zwraca dispose + fade(mix): przy zbliżeniu (mapa wektorowa — globeVector) nakładka
    kolorów i linie granic gasną, bo region wektorowy rysuje je ostro sam. */
export function addEarth(
  THREE: Three, scene: Scene, renderer: WebGLRenderer, R: number,
  opts: VectorOpts, onUpdate: () => void,
): { dispose: () => void; fade: (mix: number) => void } {
  const aniso = renderer.capabilities.getMaxAnisotropy()
  // domyślnie mapa terenu (wektor + rzeźba, tokeny motywu); zdjęcie NASA tylko z warstwą „Zdjęcie satelitarne"
  const terrain = !opts.satellite
  const tw = Math.min(TERRAIN_TEX_W, renderer.capabilities.maxTextureSize)
  const paintTerrain = (rel?: LoadedRelief) => paintVectorRegion(canvas, WORLD_REGION, tw, tw / 2, opts, rel, 2.2)
  const canvas = document.createElement('canvas')
  if (terrain) paintTerrain(); else paintGlobeTexture(canvas, null)
  const tex = new THREE.CanvasTexture(canvas)
  tex.anisotropy = aniso
  tex.colorSpace = THREE.SRGBColorSpace
  const spec = new THREE.CanvasTexture(makeSpecularCanvas())
  const mat = new THREE.MeshPhongMaterial({
    map: tex, specularMap: spec, specular: new THREE.Color(0x4a5d72), shininess: 24,
  })
  // fresnel: niebieskawa mgiełka atmosfery ku krawędzi tarczy (w tym samym przebiegu)
  mat.onBeforeCompile = sh => {
    sh.fragmentShader = sh.fragmentShader.replace('#include <dithering_fragment>', `#include <dithering_fragment>
      float fres = pow(1.0 - max(dot(normal, normalize(vViewPosition)), 0.0), 3.2);
      gl_FragColor.rgb += vec3(0.42, 0.68, 1.0) * fres * 0.5;`)
  }
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(R, 96, 64), mat))
  const disposers: (() => void)[] = [() => { tex.dispose(); spec.dispose(); mat.dispose() }]
  const faders: ((mix: number) => void)[] = []
  if (!terrain && (opts.countryColors || opts.highlights)) {
    // powłoka nad łatami LOD (≤ R·1,0009): jej cięciwy 3,75° zapadają się o ~5e-4·R
    const otex = new THREE.CanvasTexture(paintCountryOverlay(opts.countryColors, opts.highlights))
    otex.anisotropy = aniso
    otex.colorSpace = THREE.SRGBColorSpace
    const omat = new THREE.MeshLambertMaterial({ map: otex, transparent: true, depthWrite: false })
    const og = new THREE.SphereGeometry(R * 1.0016, 96, 64)
    const omesh = new THREE.Mesh(og, omat)
    scene.add(omesh)
    faders.push(mix => { omat.opacity = 1 - mix; omesh.visible = mix < 1 })
    disposers.push(() => { otex.dispose(); omat.dispose(); og.dispose() })
  }
  if (!terrain && opts.countryColors) {
    const bg = new THREE.BufferGeometry()
    bg.setAttribute('position', new THREE.BufferAttribute(borderSegments(countryBorderLines(), R * 1.0022), 3))
    const bmat = new THREE.LineBasicMaterial({ color: 0xebf2fa, transparent: true, opacity: 0.38 })
    const lines = new THREE.LineSegments(bg, bmat)
    scene.add(lines)
    faders.push(mix => { bmat.opacity = 0.38 * (1 - mix); lines.visible = mix < 1 })
    disposers.push(() => { bg.dispose(); bmat.dispose() })
  }
  let disposed = false
  if (terrain) {
    void loadReliefFor(WORLD_REGION, tw / 360).then(rel => {
      if (disposed || !rel.length) return
      paintTerrain(rel)
      tex.needsUpdate = true
      onUpdate()
    })
  } else loadEarthPhoto().then(img => {
    if (disposed) return
    paintGlobeTexture(canvas, img)
    tex.needsUpdate = true
    onUpdate()
  }).catch(() => { /* brak zdjęcia (offline) — zostaje tekstura wektorowa */ })
  return {
    dispose: () => { disposed = true; disposers.forEach(d => d()) },
    fade: mix => faders.forEach(f => f(mix)),
  }
}

/** Światła: z terminatorem — słońce wg realnej daty UTC + ciemniejsza noc;
    bez — równe światło + delikatny „reflektor" od kamery (połysk oceanu w kadrze). */
export function addLights(THREE: Three, scene: Scene, camera: Camera, terminator: boolean) {
  scene.add(new THREE.AmbientLight(0xffffff, terminator ? 0.32 : 0.95))
  if (terminator) {
    const [sx, sy, sz] = sunDirection(new Date())
    const sun = new THREE.DirectionalLight(0xfff4de, 2.1)
    sun.position.set(sx * 1000, sy * 1000, sz * 1000)
    scene.add(sun)
  } else {
    // światło kierunkowe jako dziecko kamery: celuje w środek kuli, lekko z góry-lewej
    const head = new THREE.DirectionalLight(0xffffff, 0.75)
    head.position.set(-0.35, 0.45, 1)
    camera.add(head)
    scene.add(camera)
  }
}

/** Atmosfera — poświata za krawędzią kuli (rim, BackSide). Fresnel na tarczy
    siedzi w materiale Ziemi (addEarth), bez osobnej powłoki — jeden przebieg mniej. */
export function addAtmosphere(THREE: Three, scene: Scene, R: number) {
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(R * 1.045, 64, 48), new THREE.ShaderMaterial({
    side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `varying vec3 vN; void main(){
      float i = pow(0.62 - dot(vN, vec3(0.0,0.0,1.0)), 3.0);
      gl_FragColor = vec4(0.35, 0.6, 1.0, 1.0) * i; }`,
  })))
}

/** Polilinie po wodzie (seaTrail) → punkty 3D na sferze: wielki okrąg między
    kolejnymi punktami zwrotnymi, segmentacja co 2°. */
export function trailPoints(line: LL[], r: number): Vec3[] {
  const pts: Vec3[] = []
  for (let i = 1; i < line.length; i++) {
    const seg = greatCirclePoints(line[i - 1], line[i], 2, r)
    pts.push(...(i === 1 ? seg : seg.slice(1)))
  }
  return pts
}

/* ---- canvasy 2D ---- */

const TEX_W = 4096, TEX_H = 2048
const WORLD_REGION = { lonMin: -180, lonMax: 180, latMin: -90, latMax: 90 }

/* Zdjęcie Ziemi (NASA Blue Marble, domena publiczna — public/globe/README.md):
   ładowane leniwie, raz na sesję; przebudowa sceny (dane co 5 min) go nie pobiera. */
const PHOTO_URL = EARTH_PHOTO_URL
let photo: Promise<HTMLImageElement> | null = null
export function loadEarthPhoto(): Promise<HTMLImageElement> {
  if (!photo) {
    photo = new Promise((resolve, reject) => {
      const img = new Image()
      img.decoding = 'async'
      img.onload = () => resolve(img)
      img.onerror = () => { photo = null; reject(new Error('earth photo')) }
      img.src = PHOTO_URL
    })
  }
  return photo
}

/** Tekstura kuli: zdjęcie NASA albo (zanim się wczyta / błąd sieci) ocean gradient
    + terra z paths 2D z kreską wybrzeża, jak płaska mapa. Kolory państw osobno
    (paintCountryOverlay). */
export function paintGlobeTexture(canvas: HTMLCanvasElement, img: HTMLImageElement | null): HTMLCanvasElement {
  canvas.width = TEX_W; canvas.height = TEX_H
  const ctx = canvas.getContext('2d')!
  if (img) {
    ctx.drawImage(img, 0, 0, TEX_W, TEX_H)
    return canvas
  }
  // ocean — ciemny gradient (paleta map-ocean z mapy 2D)
  const og = ctx.createLinearGradient(0, 0, 0, TEX_H)
  og.addColorStop(0, '#0a2038'); og.addColorStop(0.42, '#0e2c4e')
  og.addColorStop(0.62, '#0c2846'); og.addColorStop(1, '#071627')
  ctx.fillStyle = og; ctx.fillRect(0, 0, TEX_W, TEX_H)
  ctx.save()
  ctx.scale(TEX_W / WORLD_W, TEX_H / WORLD_H)
  const land = new Path2D(LAND_PATH)
  // ląd — ten sam gradient terra co #map-terra na mapie 2D
  const tg = ctx.createLinearGradient(0, 0, 0, WORLD_H)
  const stops: [number, string][] = [
    [0, '#e9f0f3'], [0.09, '#aab5a4'], [0.16, '#556e44'], [0.24, '#5d7c43'],
    [0.315, '#8b9557'], [0.365, '#cbb47c'], [0.43, '#a79f5d'], [0.5, '#3f6a33'],
    [0.575, '#6f8042'], [0.645, '#b29a67'], [0.71, '#7d8a4e'], [0.8, '#8b9880'],
    [0.93, '#dfe7ea'], [1, '#f3f7f8'],
  ]
  for (const [o, c] of stops) tg.addColorStop(o, c)
  ctx.fillStyle = tg
  ctx.fill(land)
  ctx.strokeStyle = 'rgba(226,240,255,.5)'
  ctx.lineWidth = 0.5
  ctx.stroke(land)
  ctx.restore()
  return canvas
}

/** Przezroczysta nakładka: kolory państw (ta sama deterministyczna paleta co
    CountryColors 2D) + podświetlenia krajów na trasie (HL). Bez obrysów — granice
    rysuje warstwa linii 3D. */
export function paintCountryOverlay(countryColors: boolean, highlights: boolean): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = TEX_W; canvas.height = TEX_H
  const ctx = canvas.getContext('2d')!
  ctx.scale(TEX_W / WORLD_W, TEX_H / WORLD_H)
  if (countryColors) for (const c of COUNTRIES) {
    ctx.fillStyle = countryFill(c)
    ctx.fill(new Path2D(c.path))
  }
  if (highlights) for (const c of COUNTRIES) {
    if (!HL[c.id]) continue
    ctx.fillStyle = HL_FILL[HL[c.id]]
    ctx.fill(new Path2D(c.path))
  }
  return canvas
}

/** Maska połysku (specularMap): ocean biały = odbija słońce, ląd czarny = matowy. */
export function makeSpecularCanvas(): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = 2048; c.height = 1024
  const ctx = c.getContext('2d')!
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, c.width, c.height)
  ctx.scale(c.width / WORLD_W, c.height / WORLD_H)
  ctx.fillStyle = '#000000'
  ctx.fill(new Path2D(LAND_PATH))
  return c
}

/** Sprite tekstowy (etykieta) — canvas z paint-order stroke jak na mapie 2D. */
export function makeLabelCanvas(text: string, px: number, color: string, weight = 600): HTMLCanvasElement {
  const pad = 6
  const c = document.createElement('canvas')
  const ctx = c.getContext('2d')!
  const font = `${weight} ${px * 2}px Inter, system-ui, sans-serif`
  ctx.font = font
  c.width = Math.ceil(ctx.measureText(text).width) + pad * 2
  c.height = px * 2 + pad * 2
  const ctx2 = c.getContext('2d')!
  ctx2.font = font
  ctx2.textBaseline = 'middle'
  ctx2.lineJoin = 'round'
  ctx2.strokeStyle = 'rgba(4,12,24,.85)'
  ctx2.lineWidth = 5
  ctx2.strokeText(text, pad, c.height / 2)
  ctx2.fillStyle = color
  ctx2.fillText(text, pad, c.height / 2)
  return c
}

export function makeDotCanvas(color: string, ring = '#ffffff'): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 32
  const ctx = c.getContext('2d')!
  ctx.beginPath(); ctx.arc(16, 16, 12, 0, Math.PI * 2)
  ctx.fillStyle = color; ctx.fill()
  ctx.lineWidth = 3; ctx.strokeStyle = ring; ctx.stroke()
  return c
}

/* strzałka wiatru na trasie: grot w górę, obrót przez SpriteMaterial.rotation */
export function makeWindCanvas(danger: boolean): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 36
  const ctx = c.getContext('2d')!
  ctx.translate(18, 18)
  ctx.strokeStyle = danger ? '#ff5c4d' : '#4fd1a5'
  ctx.lineWidth = 3
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(0, 12); ctx.lineTo(0, -12)
  ctx.moveTo(-6, -5); ctx.lineTo(0, -12); ctx.lineTo(6, -5)
  ctx.stroke()
  return c
}

/* duch replayu: przerywany okrąg jak GhostMarker na mapie 2D */
export function makeGhostCanvas(): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 40
  const ctx = c.getContext('2d')!
  ctx.strokeStyle = '#f5a623'
  ctx.lineWidth = 2.4
  ctx.setLineDash([5, 4])
  ctx.beginPath(); ctx.arc(20, 20, 15, 0, Math.PI * 2); ctx.stroke()
  ctx.setLineDash([])
  ctx.fillStyle = '#f5a623'
  ctx.beginPath(); ctx.arc(20, 20, 4, 0, Math.PI * 2); ctx.fill()
  return c
}

/* strzałka statku (billboard skierowany do kamery — stały rozmiar ekranowy) */
export function makeVesselCanvas(active: boolean): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 48
  const ctx = c.getContext('2d')!
  ctx.translate(24, 24)
  ctx.beginPath()
  ctx.moveTo(0, -14); ctx.lineTo(10, 12); ctx.lineTo(0, 6); ctx.lineTo(-10, 12)
  ctx.closePath()
  ctx.fillStyle = '#f5a623'; ctx.fill()
  ctx.lineWidth = 2.5; ctx.strokeStyle = active ? '#ffffff' : 'rgba(8,20,36,.9)'; ctx.stroke()
  return c
}

/* fabryka dostawcy — zielony romb (klaster), jak na mapie 2D */
export function makeFactoryCanvas(): HTMLCanvasElement {
  const c = document.createElement('canvas'); c.width = c.height = 36
  const ctx = c.getContext('2d')!
  ctx.translate(18, 18); ctx.rotate(Math.PI / 4)
  ctx.fillStyle = '#7ac74f'; ctx.strokeStyle = '#0a1626'; ctx.lineWidth = 2.5
  ctx.fillRect(-9, -9, 18, 18); ctx.strokeRect(-9, -9, 18, 18)
  return c
}
