/**
 * 机箱模型加载工厂：GLB 加载、朝向/居中/缩放、材质修复、相机适配、灯光补偿。
 * 职责边界：只管「模型内容进场」，不涉及交互；依赖 createThreeSetup 提供的基础设施。
 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader, DRACO_GLTF_CONFIG } from 'three/examples/jsm/loaders/DRACOLoader.js'

import type { ThreeSetup } from './case-scene'
import {
  CAMERA_DISTANCE_FACTOR,
  INSIDE_LIGHT_BASE_SIZE,
  INSIDE_LIGHT_INTENSITY,
  MODEL_FRONT_YAW,
  MODEL_SCALE,
  MODEL_URL,
} from './case-constants'
import { repairCaseMaterials } from './case-utils'

export interface CaseModelHandle {
  root: THREE.Group
  /** 模型最大维度（居中缩放后的世界尺寸），聚焦取景等按此比例计算 */
  readonly maxDim: number
}

/** 按模型尺寸与容器视野重新计算相机距离，保证模型完整入镜并留白 */
function fitCameraToModel(setup: ThreeSetup, maxDim: number): void {
  const { width, height } = setup.size
  if (width === 0 || height === 0) return
  const fitDistance = maxDim / 2 / Math.tan((setup.camera.fov * Math.PI) / 360)
  // 相机摆在正前方（+Z 轴上），distance 系数越大留白越多
  setup.camera.position.set(0, 0, fitDistance * CAMERA_DISTANCE_FACTOR)
  setup.controls.target.set(0, 0, 0)
}

/**
 * 加载机箱模型并完成全部进场处理；resolve 时模型已加入场景、相机已适配。
 * @param onProgress - 加载进度回调（0~100 百分比）；HTTP 未带 Content-Length 时无法计算，可不传
 */
export function loadCaseModel(
  setup: ThreeSetup,
  onProgress?: (percent: number) => void,
): Promise<CaseModelHandle> {
  const dracoLoader = new DRACOLoader()
  // 直接用 three 内置的 glTF 版解码器地址：经 Vite 打包后带 hash 发布，
  // 无需在 public 里重复放置解码器文件，也不会受部署子路径影响
  dracoLoader.setDecoderPath(DRACO_GLTF_CONFIG)
  const gltfLoader = new GLTFLoader()
  gltfLoader.setDRACOLoader(dracoLoader)

  return new Promise((resolve, reject) => {
    gltfLoader.load(
      MODEL_URL,
      (gltf) => {
        dracoLoader.dispose()
        // 组件已卸载时直接丢弃结果，避免向已销毁的场景添加模型
        if (setup.isDisposed) return

        const modelRoot = gltf.scene
        modelRoot.scale.set(MODEL_SCALE, MODEL_SCALE, MODEL_SCALE)
        // 正面校准：把模型绕 Y 轴转到正面朝 +Z（相机所在方向）
        modelRoot.rotation.y = MODEL_FRONT_YAW
        // 包围盒居中：把模型平移到世界原点
        const box = new THREE.Box3().setFromObject(modelRoot)
        const size = box.getSize(new THREE.Vector3())
        const center = box.getCenter(new THREE.Vector3())
        modelRoot.position.sub(center)
        // 居中后模型中心就是原点，轨道目标和内部点光源都对准原点
        setup.controls.target.set(0, 0, 0)
        setup.insidePointLight.position.set(0, 0, 0)

        repairCaseMaterials(modelRoot)

        const maxDim = Math.max(size.x, size.y, size.z)
        // 布局变化后容器尺寸与模型加载时不同，必须重算距离否则模型超出视野
        setup.onResize(() => fitCameraToModel(setup, maxDim))
        fitCameraToModel(setup, maxDim)
        // 点光源强度按模型尺寸平方补偿，缩放模型后内部照度不变
        setup.insidePointLight.intensity =
          INSIDE_LIGHT_INTENSITY * (maxDim / INSIDE_LIGHT_BASE_SIZE) ** 2
        // 轨道缩放限制跟随模型尺寸：写死数值在模型放大后会把相机钳住导致构图越界
        setup.controls.minDistance = maxDim * 0.25
        setup.controls.maxDistance = maxDim * 3
        setup.scene.add(modelRoot)
        resolve({ root: modelRoot, maxDim })
      },
      (progressEvent) => {
        // 进度透传给调用方；total=0 表示响应未带 Content-Length，无法算百分比
        if (!onProgress) return
        if (progressEvent.total > 0) {
          onProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100))
        }
      },
      (err) => {
        dracoLoader.dispose()
        console.error('机箱模型加载失败', err)
        reject(err)
      },
    )
  })
}
