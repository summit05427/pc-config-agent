/**
 * three.js 场景基础设施工厂：renderer/相机/控制器/后期合成/灯光/环境贴图/尺寸跟随。
 * 职责边界：只管「画布与循环」，不涉及模型内容；由调用方在组件挂载后创建并负责 dispose。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'

import {
  AMBIENT_LIGHT_INTENSITY,
  BLOOM_LAYER,
  BLOOM_RADIUS,
  BLOOM_STRENGTH,
  BLOOM_THRESHOLD,
  ENV_INTENSITY,
  FILL_LIGHT_INTENSITY,
  FILL_LIGHT_POSITION,
  INSIDE_LIGHT_INTENSITY,
  KEY_LIGHT_INTENSITY,
  KEY_LIGHT_POSITION,
  RIM_LIGHT_INTENSITY,
  RIM_LIGHT_POSITION,
} from './case-constants'

export interface ThreeSetup {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  controls: OrbitControls
  /** 机箱内部点光源（模型加载后按尺寸做平方补偿） */
  insidePointLight: THREE.PointLight
  /** 容器实时尺寸（响应式） */
  readonly size: { width: number; height: number }
  /** 注册容器尺寸变化回调（在画布重设尺寸后调用） */
  onResize: (callback: () => void) => void
  /** 是否已销毁（异步补间/加载完成时用于提前退出） */
  readonly isDisposed: boolean
  dispose: () => void
}

/** 释放网格几何体、材质与其贴图：卸载面板时避免 GPU 资源残留 */
function disposeObjectResources(root: THREE.Object3D): void {
  root.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    child.geometry.dispose()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((material) => {
      // 贴图键名按 three 常见命名枚举；只用 in 判断，避免把非贴图字段当纹理释放
      const textureKeys = [
        'map',
        'emissiveMap',
        'alphaMap',
        'normalMap',
        'roughnessMap',
        'metalnessMap',
        'aoMap',
        'envMap',
      ] as const
      const record = material as unknown as Record<string, unknown>
      textureKeys.forEach((key) => {
        const value = record[key]
        if (value instanceof THREE.Texture) value.dispose()
      })
      material.dispose()
    })
  })
}

/** 创建场景基础设施。必须在容器挂载后调用（需要 clientWidth/clientHeight） */
export function createThreeSetup(container: HTMLElement): ThreeSetup {
  const readSize = () => ({ width: container.clientWidth, height: container.clientHeight })
  const size = readSize()

  // 1. 场景：不设 scene.background，画布保持透明，透出页面自身的背景
  const scene = new THREE.Scene()

  // ============ 灯光：暗调摄影棚三点布光 ============
  const ambientLight = new THREE.AmbientLight(0xffffff, AMBIENT_LIGHT_INTENSITY)
  scene.add(ambientLight)
  const keyLight = new THREE.DirectionalLight(0xffffff, KEY_LIGHT_INTENSITY)
  keyLight.position.set(...KEY_LIGHT_POSITION)
  scene.add(keyLight)
  const fillLight = new THREE.DirectionalLight(0xffffff, FILL_LIGHT_INTENSITY)
  fillLight.position.set(...FILL_LIGHT_POSITION)
  scene.add(fillLight)
  const rimLight = new THREE.DirectionalLight(0xffffff, RIM_LIGHT_INTENSITY)
  rimLight.position.set(...RIM_LIGHT_POSITION)
  scene.add(rimLight)
  // 点光源：放在机箱中心照亮内部；距离传 0 表示不设照射范围上限，按物理规律自然衰减
  const insidePointLight = new THREE.PointLight(0xffffff, INSIDE_LIGHT_INTENSITY)
  scene.add(insidePointLight)
  // ==================================

  // 相机
  const camera = new THREE.PerspectiveCamera(75, size.width / size.height, 0.1, 1000)
  camera.position.z = 2

  // 渲染器：alpha 开启透明缓冲，画布背景透明
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  // 透明清屏（alpha=0）：配合 scene.background=null 让 canvas 无模型区域完全透明
  renderer.setClearColor(0x000000, 0)
  renderer.setSize(size.width, size.height)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  // ACES 色调映射：让高光过渡更自然，玻璃反光不会死白一块
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  container.appendChild(renderer.domElement)

  // 环境贴图：相当于给场景拍了一张「房间照片」，玻璃和金属的倒影都来自它
  const pmremGenerator = new THREE.PMREMGenerator(renderer)
  const roomEnvironment = new RoomEnvironment()
  const environmentTarget = pmremGenerator.fromScene(roomEnvironment, 0.04)
  scene.environment = environmentTarget.texture
  scene.environmentIntensity = ENV_INTENSITY
  // 环境贴图已生成到 render target，房间场景本身可立即释放
  roomEnvironment.dispose()
  pmremGenerator.dispose()

  // ============ 选择性 Bloom 双管线 ============
  // 单管线 Bloom 会把金属面镜面高光、点光源照度尖峰一起送进光晕（相机一动就闪烁白斑）。
  // 拆成两步：bloomComposer 只渲染 BLOOM_LAYER 图层（自发光件），产出纯光晕纹理；
  // finalComposer 渲染完整场景后把光晕纹理加法叠加再色调映射上屏。
  const bloomComposer = new EffectComposer(renderer)
  bloomComposer.renderToScreen = false // 辉光只产出中间纹理，上屏交给 finalComposer
  // 辉光是低频模糊纹理，1 倍像素比足够；与最终管线同用 DPR 2 会挤占 UI 合成带宽
  bloomComposer.setPixelRatio(1)
  bloomComposer.addPass(new RenderPass(scene, camera))
  bloomComposer.addPass(
    new UnrealBloomPass(
      new THREE.Vector2(size.width, size.height),
      BLOOM_STRENGTH,
      BLOOM_RADIUS,
      BLOOM_THRESHOLD,
    ),
  )

  // 加法混合着色器：把辉光纹理逐像素叠到全场景渲染结果上（含 alpha，背景透明区不受污染）
  const bloomBlendPass = new ShaderPass(
    new THREE.ShaderMaterial({
      uniforms: {
        baseTexture: { value: null },
        bloomTexture: { value: bloomComposer.renderTarget2.texture },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
        }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D baseTexture;
        uniform sampler2D bloomTexture;
        varying vec2 vUv;
        void main() {
          gl_FragColor = texture2D( baseTexture, vUv ) + texture2D( bloomTexture, vUv );
        }`,
      defines: {},
    }),
    'baseTexture',
  )

  const finalComposer = new EffectComposer(renderer)
  finalComposer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  finalComposer.addPass(new RenderPass(scene, camera))
  finalComposer.addPass(bloomBlendPass)
  finalComposer.addPass(new OutputPass())

  // 轨道控制器（min/maxDistance 由模型加载后按尺寸覆盖）
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.enablePan = true
  // 垂直俯仰范围：允许上下调整视角，但限制在略高于顶视/略低于底视之间，防止穿模或构图失控
  controls.minPolarAngle = Math.PI / 3
  controls.maxPolarAngle = (Math.PI * 2) / 3

  const resizeCallbacks = new Set<() => void>()

  const resizeObserver = new ResizeObserver(() => {
    const { width, height } = readSize()
    if (width === 0 || height === 0) return
    size.width = width
    size.height = height
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height)
    bloomComposer.setSize(width, height)
    finalComposer.setSize(width, height)
    resizeCallbacks.forEach((callback) => callback())
  })
  resizeObserver.observe(container)

  const animate = () => {
    frameId = requestAnimationFrame(animate)
    if (disposed) return
    controls.update()
    // 选择性 Bloom 两步渲染：辉光相机只看发光图层，随后恢复全图层渲染完整场景
    camera.layers.set(BLOOM_LAYER)
    bloomComposer.render()
    camera.layers.enableAll()
    finalComposer.render()
  }

  let disposed = false
  let frameId = 0
  frameId = requestAnimationFrame(animate)

  const dispose = (): void => {
    if (disposed) return
    disposed = true
    cancelAnimationFrame(frameId)
    resizeObserver.disconnect()
    controls.dispose()
    disposeObjectResources(scene)
    // 环境贴图由 PMREM 生成在独立 render target 中，需随场景一起释放
    environmentTarget.dispose()
    bloomComposer.dispose()
    finalComposer.dispose()
    renderer.dispose()
    // dispose 只释放 GPU 资源不移除元素；主动丢弃上下文，避免反复挂载累积 WebGL 上下文
    renderer.forceContextLoss()
    renderer.domElement.remove()
  }

  return {
    scene,
    camera,
    renderer,
    controls,
    insidePointLight,
    size,
    onResize: (callback) => resizeCallbacks.add(callback),
    get isDisposed() {
      return disposed
    },
    dispose,
  }
}
