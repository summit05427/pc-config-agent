/**
 * 组件标记点工厂：按网格名定位 3D 锚点，供导航聚焦使用。
 * 职责边界：只管「网格名 → 锚点对象」；导航 UI 与选中态由面板负责。
 */
import * as THREE from 'three'

import { CASE_MARKERS } from './case-constants'
import type { MarkerConfig } from './case-constants'
import type { CaseModelHandle } from './case-model'

export interface CaseMarker {
  readonly config: MarkerConfig
  /** 3D 锚点对象（挂在目标网格上，点击聚焦时读取世界坐标） */
  readonly anchor: THREE.Object3D
}

/** 在模型中按名称前缀找到目标网格，并在其包围盒中心挂一个锚点空对象 */
function resolveAnchor(modelRoot: THREE.Group, config: MarkerConfig): THREE.Object3D | null {
  const hits: THREE.Mesh[] = []
  modelRoot.traverse((child) => {
    if (child instanceof THREE.Mesh && child.name.startsWith(config.meshNamePrefix)) {
      hits.push(child)
    }
  })
  const target = hits[0]
  if (!target) return null
  const box = new THREE.Box3().setFromObject(target)
  const center = box.getCenter(new THREE.Vector3())
  // 转成目标网格的局部坐标后挂为子对象：模型旋转/移动时锚点自动跟随
  target.worldToLocal(center)
  const anchor = new THREE.Object3D()
  anchor.position.copy(center)
  target.add(anchor)
  return anchor
}

/**
 * 创建组件标记点。必须在模型加载完成（loadCaseModel resolve）后调用。
 * 标记以导航按钮的形式渲染，不需要每帧把 3D 坐标投影到屏幕。
 */
export function createCaseMarkers(handle: CaseModelHandle): CaseMarker[] {
  const markers: CaseMarker[] = []

  // 关键：模型 add 进场景后尚未渲染过，全链 matrixWorld 还是单位阵。
  // 不先刷新的话，包围盒中心与 worldToLocal 会基于过期矩阵互逆，锚点会被错误写到 geometry 局部坐标
  handle.root.updateMatrixWorld(true)

  for (const config of CASE_MARKERS) {
    const anchor = resolveAnchor(handle.root, config)
    // 网格名未命中（模型改动）时跳过该标记，不影响其余标记
    if (!anchor) {
      console.warn(`标记 ${config.id} 未找到网格 ${config.meshNamePrefix}`)
      continue
    }
    markers.push({ config, anchor })
  }

  return markers
}
