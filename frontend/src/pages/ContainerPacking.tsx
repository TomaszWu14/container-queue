import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { formatNum } from '../dates'
import { prefersReducedMotion } from '../motion'
import { disposeThree } from '../threeDispose'

// Panel „Wypełnienie kontenera" — scena 3D (three.js) ładowana LENIWIE z ContainerPage
// (React.lazy), żeby three nie tuczyło głównego chunku.
// Dane z GET /api/containers/{id}/packing.

interface PackBox {
  x: number; y: number; z: number
  w: number; h: number; d: number
  sku: string; color: string; approximated: boolean
}
interface PackExcluded { order_no: string; material: string; reason: string }
export interface PackingData {
  status: 'ok' | 'no_data' | 'no_type' | 'no_items'
  boxes?: PackBox[]
  fill_pct?: number
  volume_used_m3?: number
  volume_total_m3?: number
  container_dims?: { l: number; w: number; h: number }
  excluded?: PackExcluded[]
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function Scene({ data }: { data: PackingData }) {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !data.boxes || !data.container_dims) return
    let disposed = false
    let cleanup = () => {}
    // dynamic import wewnątrz efektu — three zostaje w osobnym chunku
    Promise.all([
      import('three'),
      import('three/examples/jsm/controls/OrbitControls.js'),
    ]).then(([THREE, { OrbitControls }]) => {
      if (disposed || !mount) return
      const { l: L, w: W, h: H } = data.container_dims!
      const renderer = new THREE.WebGLRenderer({ antialias: true })
      renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))
      renderer.setSize(mount.clientWidth, 480)
      mount.appendChild(renderer.domElement)

      const scene = new THREE.Scene()
      scene.background = new THREE.Color(0x0b1020)
      scene.add(new THREE.HemisphereLight(0xbcd0ff, 0x404a66, 1.15))
      const sun = new THREE.DirectionalLight(0xfff2dc, 2.0)
      sun.position.set(1.2, 2.4, 1.0).multiplyScalar(1500)
      scene.add(sun)
      const fill = new THREE.DirectionalLight(0x9fc0ff, 0.6)
      fill.position.set(-1200, 700, -900)
      scene.add(fill)

      // podłoga + siatka
      const grid = new THREE.GridHelper(L * 3, 40, 0x2a3a66, 0x1a2440)
      scene.add(grid)

      // szkielet wnętrza kontenera
      const frame = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(L, H, W)),
        new THREE.LineBasicMaterial({ color: 0x5ff0e4 }))
      frame.position.set(0, H / 2, 0)
      scene.add(frame)

      // kartony: backend daje narożnik min (x wzdłuż L, y w górę, z wszerz)
      const edgeMat = new THREE.LineBasicMaterial({ color: 0x10131f, transparent: true, opacity: 0.35 })
      for (const b of data.boxes!) {
        const geo = new THREE.BoxGeometry(b.w * 0.97, b.h * 0.97, b.d * 0.97)
        const mat = new THREE.MeshStandardMaterial({
          color: b.color, roughness: 0.62, metalness: 0.04,
          transparent: b.approximated, opacity: b.approximated ? 0.45 : 1,
        })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.position.set(b.x + b.w / 2 - L / 2, b.y + b.h / 2, b.z + b.d / 2 - W / 2)
        if (!b.approximated) mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat))
        scene.add(mesh)
      }

      const camera = new THREE.PerspectiveCamera(45, mount.clientWidth / 480, 1, 30000)
      camera.position.set(L * 0.35, H * 1.6, Math.max(L, H) * 1.3 + W)
      const controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = !prefersReducedMotion() // bezwładność kamery = ruch (UX-040)
      controls.dampingFactor = 0.08
      controls.target.set(0, H / 2, 0)
      controls.update()

      // render on demand — GPU odpoczywa gdy kamera stoi
      let dirty = true
      controls.addEventListener('change', () => { dirty = true })
      const observer = new ResizeObserver(() => {
        renderer.setSize(mount.clientWidth, 480)
        camera.aspect = mount.clientWidth / 480
        camera.updateProjectionMatrix()
        dirty = true
      })
      observer.observe(mount)
      let raf = 0
      const loop = () => {
        raf = requestAnimationFrame(loop)
        const moving = controls.update()
        if (moving || dirty) { renderer.render(scene, camera); dirty = false }
      }
      loop()
      cleanup = () => {
        cancelAnimationFrame(raf)
        observer.disconnect()
        controls.dispose()
        disposeThree(scene, renderer)   // geometrie/materiały kartonów + kontekst WebGL
        mount.removeChild(renderer.domElement)
      }
    })
    return () => { disposed = true; cleanup() }
  }, [data])

  return <div ref={mountRef} data-testid="packing-scene" style={{ width: '100%' }} />
}

export default function ContainerPackingPanel({ containerId }: { containerId: number }) {
  const t = useT()
  const [data, setData] = useState<PackingData | null>(null)
  const [error, setError] = useState('')
  const webgl = hasWebGL()

  useEffect(() => {
    setData(null)
    setError('')
    api.get<PackingData>(`/api/containers/${containerId}/packing`)
      .then(setData).catch(err => setError(errorMessage(err)))
  }, [containerId])

  if (error) return <div className="panel"><h3>{t('packTitle')}</h3><p className="error">{error}</p></div>
  if (!data) return null
  if (data.status === 'no_type') {
    return <div className="panel"><h3>{t('packTitle')}</h3>
      <p style={{ color: 'var(--muted)' }}>{t('packNoType')}</p></div>
  }
  if (data.status === 'no_items') return null   // brak pozycji = panel nie wnosi nic (jak ItemsPanel)

  const pct = data.fill_pct ?? 0
  const hudColor = pct > 100 ? '#f87171' : pct >= 85 ? '#34d399' : '#fbbf24'
  const hasApprox = (data.boxes ?? []).some(b => b.approximated)

  return (
    <div className="panel">
      <h3>{t('packTitle')}</h3>
      {data.status === 'no_data' ? (
        <p style={{ color: 'var(--muted)' }}>{t('packNoData')}</p>
      ) : (
        <div style={{ position: 'relative' }}>
          {webgl
            ? <Scene data={data} />
            : <p style={{ color: 'var(--muted)' }}>{t('packNoWebgl')}</p>}
          {/* HUD wypełnienia */}
          <div data-testid="packing-hud" style={{
            position: 'absolute', top: 12, right: 12, pointerEvents: 'none',
            background: 'rgba(8,12,24,.78)', border: '1px solid rgba(127,214,207,.4)',
            borderRadius: 12, padding: '10px 14px', minWidth: 170, color: '#eaf2ff',
          }}>
            <div style={{ fontSize: 11, letterSpacing: '.6px', textTransform: 'uppercase', color: '#9fb0d0' }}>
              {t('packFill')}
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1.05, color: hudColor }}>
              {formatNum(pct, 1)}<span style={{ fontSize: 16 }}>%</span>
            </div>
            <div style={{ fontSize: 12, color: '#9fb0d0', marginTop: 4 }}>
              {formatNum(data.volume_used_m3 ?? 0, 1)} / {formatNum(data.volume_total_m3 ?? 0, 1)} m³
            </div>
          </div>
          {hasApprox && (
            <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 8 }}>{t('packApproxLegend')}</p>
          )}
        </div>
      )}
      {(data.excluded ?? []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <h4 style={{ margin: '0 0 6px' }}>{t('packExcluded')} ({data.excluded!.length})</h4>
          <table className="grid">
            <thead><tr><th>{t('order')}</th><th>REF</th><th>{t('packReason')}</th></tr></thead>
            <tbody>
              {data.excluded!.map((e, i) => (
                <tr key={i}>
                  <td className="mono">{e.order_no}</td>
                  <td className="mono">{e.material}</td>
                  <td>{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12, marginTop: 6 }}>
            <Link to="/master-data/jednostki-materialow">{t('packGoMarm')}</Link>
          </p>
        </div>
      )}
    </div>
  )
}
