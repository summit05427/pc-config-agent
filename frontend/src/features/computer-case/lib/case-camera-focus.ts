/**
 * 相机聚焦工厂：点击导航项后把相机缓动飞到能看清组件的方位；支持一键复位。
 * 职责边界：只管「相机运动」，不涉及标记定位；补间期间锁定轨道控制器避免拖拽打架。
 */
import * as THREE from 'three'

import type { ThreeSetup } from './case-scene'
import { FOCUS_DISTANCE_FACTOR, FOCUS_DURATION_MS } from './case-constants'

/** easeInOutCubic：先加速后减速，飞行动画观感自然 */
function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2
}

export interface CameraFocus {
  /** 飞向目标组件：自动挑选「不被机身遮挡」的观察方位（用户在背面点击时相机会环绕过去） */
  focusOn: (anchor: THREE.Object3D) => void
  /** 复位到模型全景视角 */
  resetView: () => void
}

/** 创建相机聚焦控制器。须在模型加载完成后调用；maxDim 用于计算取景距离 */
export function createCameraFocus(
  setup: ThreeSetup,
  modelRoot: THREE.Group,
  maxDim: number,
): CameraFocus {
  const { camera, controls } = setup
  // 记录全景基准位（fit 相机后的位置与目标点），复位时飞回
  const homeCameraPos = camera.position.clone()
  const homeTarget = controls.target.clone()
  // 全景方位（开放面朝向）：模型加载后所有组件都面向该方位，是兜底的「正确角度」
  const homeAzimuth = Math.atan2(homeCameraPos.z, homeCameraPos.x)

  const raycaster = new THREE.Raycaster()
  /** 当前飞行动画的 rAF 句柄（新飞行打断旧飞行，避免两个补间并行互写相机） */
  let flightRafId = 0

  /** obj 是否为 target 自身或其后代（锚点是目标网格的子对象，据此判断射线首碰是否为目标本身） */
  function isSelfOrDescendant(target: THREE.Object3D, obj: THREE.Object3D): boolean {
    let cur: THREE.Object3D | null = obj
    while (cur) {
      if (cur === target) return true
      cur = cur.parent
    }
    return false
  }

  /** 从观察点看向目标中心，射线首碰是目标自身（或其子网格）才视为可见，被机身挡住则不可见 */
  function isVisibleFrom(
    targetMesh: THREE.Object3D | null,
    pos: THREE.Vector3,
    target: THREE.Vector3,
  ): boolean {
    if (!targetMesh) return true
    const dir = target.clone().sub(pos)
    const distance = dir.length()
    raycaster.set(pos, dir.normalize())
    raycaster.far = distance
    const hits = raycaster.intersectObject(modelRoot, true)
    const firstHit = hits[0]
    return !firstHit || isSelfOrDescendant(targetMesh, firstHit.object)
  }

  /** 绕机箱的球面插值飞行：水平面内插值「方位角 + 半径」、垂直方向插值高度 */
  function orbitFlyTo(endTarget: THREE.Vector3, endPos: THREE.Vector3): void {
    // 打断进行中的飞行：连续点击时以最新点击为准
    if (flightRafId) cancelAnimationFrame(flightRafId)
    // 消费掉轨道控制器的残余阻尼速度（拖拽惯性）：非阻尼模式下 update 会把残量一次性施加并清零。
    // 必须在捕获起点前做，否则飞行期间每帧 update 都会把残量「踢」到补间位姿上（点击时画面抽搐的根因）
    controls.enableDamping = false
    controls.update()
    const startPos = camera.position.clone()
    const startTarget = controls.target.clone()
    const startRadius = Math.hypot(startPos.x, startPos.z)
    const endRadius = Math.hypot(endPos.x, endPos.z)
    const startAzimuth = Math.atan2(startPos.z, startPos.x)
    let dAzimuth = Math.atan2(endPos.z, endPos.x) - startAzimuth
    // 方位角取最短旋转路径（±π 内），避免就近 360° 大回环
    if (dAzimuth > Math.PI) dAzimuth -= Math.PI * 2
    if (dAzimuth < -Math.PI) dAzimuth += Math.PI * 2
    const startY = startPos.y
    const dY = endPos.y - startY
    const start = performance.now()
    controls.enabled = false
    const step = (now: number): void => {
      if (setup.isDisposed) return
      // t 必须双端 clamp：rAF 帧时间戳可能早于点击时记录的 start，
      // 若 t<0 则缓动系数为负，相机会被写到补间反向延长线上（单帧远景＝点击闪屏根因）
      const t = Math.min(Math.max((now - start) / FOCUS_DURATION_MS, 0), 1)
      const k = easeInOutCubic(t)
      const azimuth = startAzimuth + dAzimuth * k
      const radius = startRadius + (endRadius - startRadius) * k
      camera.position.set(Math.cos(azimuth) * radius, startY + dY * k, Math.sin(azimuth) * radius)
      controls.target.lerpVectors(startTarget, endTarget, k)
      if (t < 1) {
        flightRafId = requestAnimationFrame(step)
      } else {
        flightRafId = 0
        controls.enableDamping = true
        controls.enabled = true
      }
    }
    flightRafId = requestAnimationFrame(step)
  }

  return {
    focusOn(anchor) {
      const worldTarget = anchor.getWorldPosition(new THREE.Vector3())
      // 锚点挂载在目标网格上（见 case-markers.resolveAnchor），用于射线可见性判断
      const targetMesh = anchor.parent
      const dist = maxDim * FOCUS_DISTANCE_FACTOR

      // 候选方位（水平面单位方向），按优先级取第一个「看得清组件」的：
      // 1) 当前观察方位（不必要时不环绕，路径最自然）
      // 2) 全景开放面方位（用户转到背面时的「正确角度」）
      // 3) 机箱中心→组件的向外方位及其 ±90° 旋转（组件朝向特殊侧面的兜底）
      const currentDir = camera.position.clone().sub(controls.target).setY(0)
      const currentAzimuth =
        currentDir.lengthSq() > 1e-6 ? Math.atan2(currentDir.z, currentDir.x) : homeAzimuth
      const radial = new THREE.Vector3(worldTarget.x, 0, worldTarget.z)
      const radialAzimuth = radial.lengthSq() > 1e-6 ? Math.atan2(radial.z, radial.x) : homeAzimuth
      const candidateAzimuths = [
        currentAzimuth,
        homeAzimuth,
        radialAzimuth,
        radialAzimuth + Math.PI / 2,
        radialAzimuth - Math.PI / 2,
      ]

      let chosenAzimuth = candidateAzimuths[candidateAzimuths.length - 1]!
      for (const azimuth of candidateAzimuths) {
        const dir = new THREE.Vector3(Math.cos(azimuth), 0, Math.sin(azimuth))
        const pos = worldTarget.clone().addScaledVector(dir, dist)
        if (isVisibleFrom(targetMesh, pos, worldTarget)) {
          chosenAzimuth = azimuth
          break
        }
      }

      const endPos = worldTarget
        .clone()
        .addScaledVector(
          new THREE.Vector3(Math.cos(chosenAzimuth), 0, Math.sin(chosenAzimuth)),
          dist,
        )
      orbitFlyTo(worldTarget.clone(), endPos)
    },
    resetView() {
      orbitFlyTo(homeTarget.clone(), homeCameraPos.clone())
    },
  }
}
