// Pełne zwolnienie sceny three (globus /sledzenie, pakowanie kontenera): geometrie, materiały
// i ich tekstury + kontekst WebGL. Samo renderer.dispose() zostawia zasoby sceny w GPU, a
// przeglądarka trzyma ograniczoną liczbę kontekstów (~16) — bez forceContextLoss każdy
// remount zostawiał kontekst do GC i po kilkunastu „WARNING: Too many active WebGL contexts”.
// Tylko typy z three — moduł nie wciąga three do głównego chunku.
import type { Material, Object3D, Texture, WebGLRenderer } from 'three'

type Disposable = Object3D & { geometry?: { dispose(): void }; material?: Material | Material[] }

export function disposeThree(scene: Object3D, renderer: Pick<WebGLRenderer, 'dispose' | 'forceContextLoss'>,
                             extra: Iterable<Texture> = []): void {
  scene.traverse(obj => {
    const o = obj as Disposable
    o.geometry?.dispose()
    for (const m of ([] as Material[]).concat(o.material ?? [])) {
      for (const v of Object.values(m)) if ((v as Texture | null)?.isTexture) (v as Texture).dispose()
      m.dispose()
    }
  })
  for (const tx of extra) tx.dispose()
  renderer.dispose()
  renderer.forceContextLoss()
}
