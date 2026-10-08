// Zwolnienie sceny three: geometrie, materiały, ich tekstury, dodatkowe tekstury i kontekst WebGL.
import { describe, expect, it, vi } from 'vitest'
import { BoxGeometry, Mesh, MeshBasicMaterial, Scene, Sprite, SpriteMaterial, Texture } from 'three'
import { disposeThree } from './threeDispose'

describe('disposeThree', () => {
  it('zwalnia wszystko w scenie + forceContextLoss', () => {
    const scene = new Scene()
    const geo = new BoxGeometry(1, 1, 1)
    const map = new Texture()
    const mat = new MeshBasicMaterial({ map })
    const mesh = new Mesh(geo, mat)
    const sprMap = new Texture()
    const sprite = new Sprite(new SpriteMaterial({ map: sprMap }))
    mesh.add(sprite)                       // zagnieżdżone też (traverse)
    scene.add(mesh)
    const extra = new Texture()
    const spies = [geo, map, mat, sprMap, sprite.material, extra].map(o => vi.spyOn(o, 'dispose'))
    const renderer = { dispose: vi.fn(), forceContextLoss: vi.fn() }

    disposeThree(scene, renderer, [extra])

    spies.forEach(s => expect(s).toHaveBeenCalled())
    expect(renderer.dispose).toHaveBeenCalled()
    expect(renderer.forceContextLoss).toHaveBeenCalled()
  })
})
