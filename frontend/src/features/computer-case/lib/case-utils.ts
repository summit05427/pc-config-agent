/**
 * 机箱 3D 渲染纯函数工具：材质修复、发光分档、贴图合成。
 * 职责边界：只做「输入材质 → 输出修改」的无状态处理，不持有场景/相机引用。
 */
import * as THREE from 'three'

import {
  BLOOM_LAYER,
  COIL_STRIPE_BLACK,
  COIL_STRIPE_RED,
  COIL_STRIPE_RED_RATIO,
  COIL_STRIPE_REPEAT,
  EMISSIVE_COLOR_MAX_INTENSITY,
  EMISSIVE_COLOR_TARGET_LUMINANCE,
  EMISSIVE_DIM_OVERRIDES,
  EMISSIVE_INTENSITY_BOOST,
  EMISSIVE_MIN_LIGHTNESS,
  EMISSIVE_ONLY_DARKEN_COLOR,
  EMISSIVE_SATURATION_THRESHOLD,
  EMISSIVE_WHITE_INTENSITY,
  FAKE_METAL_FIX_METALNESS,
  FAKE_METAL_FIX_ROUGHNESS,
  FAKE_METAL_ROUGHNESS_THRESHOLD,
  GLASS_ENV_INTENSITY,
  GLASS_FRONT_EMISSIVE_INTENSITY,
  GLASS_MATERIAL_NAMES,
  GLASS_OPACITY,
  GLASS_TINT_COLOR,
  LOGO_MASK_URL,
  NO_MAP_DARKEN_COLOR,
} from './case-constants'

/** 生成径向 alpha 贴图：中心不透明、边缘平滑透明，把方形 Logo 板裁成圆形贴合泵体轮廓 */
function createRadialAlphaTexture(): THREE.CanvasTexture {
  const SIZE = 256
  const canvas = document.createElement('canvas')
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(SIZE / 2, SIZE / 2, 0, SIZE / 2, SIZE / 2, SIZE / 2)
  gradient.addColorStop(0.78, '#fff')
  gradient.addColorStop(0.94, '#000')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, SIZE, SIZE)
  return new THREE.CanvasTexture(canvas)
}

/**
 * 合成水冷头发光贴图：彩虹渐变 × ROG Logo 遮罩（白=发光、黑=熄灭）。
 * GLB 导出丢失了 Blender 的 Multiply 节点网络，此处用源文件补乘，
 * 还原「黑底 + 彩虹 Logo」图案；不修改共享的渐变贴图（RGB_Lighting 也在用）。
 */
async function applyLogoEmissiveMask(mat: THREE.MeshStandardMaterial): Promise<void> {
  const gradientImage = mat.emissiveMap?.image as CanvasImageSource | undefined
  if (!gradientImage) return
  const mask = new Image()
  mask.src = LOGO_MASK_URL
  try {
    await mask.decode()
  } catch {
    return // 遮罩图加载失败时保留原渐变，不阻塞渲染
  }
  const SIZE = 1024
  const canvas = document.createElement('canvas')
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(gradientImage, 0, 0, SIZE, SIZE)
  ctx.globalCompositeOperation = 'multiply'
  ctx.drawImage(mask, 0, 0, SIZE, SIZE)
  const texture = new THREE.CanvasTexture(canvas)
  // 与 GLB 贴图 UV 约定一致（flipY=false，v=0 对应图片顶部），否则 Logo 上下颠倒
  texture.flipY = false
  texture.colorSpace = THREE.SRGBColorSpace
  mat.emissiveMap = texture
  mat.needsUpdate = true
}

/**
 * 按发光贴图主色把自发光分档：白色系固定低压（防白爆成团）、彩色系按亮度反比补偿。
 * 缩小到 16x16 采样统计饱和度与亮度，一次执行开销可忽略。
 */
function resolveEmissiveIntensity(mat: THREE.MeshStandardMaterial): number {
  // 点睛光效定向压低（风扇灯环/Logo 等），优先级高于通用分档
  for (const [namePart, intensity] of EMISSIVE_DIM_OVERRIDES) {
    if (mat.name.includes(namePart)) return intensity
  }
  // 无贴图时按 emissive 颜色本身判断（getHSL 的 s/l 分量）
  if (!mat.emissiveMap) {
    const hsl = { h: 0, s: 0, l: 0 }
    mat.emissive.getHSL(hsl)
    return hsl.s < EMISSIVE_SATURATION_THRESHOLD
      ? EMISSIVE_WHITE_INTENSITY
      : Math.min(
          EMISSIVE_COLOR_TARGET_LUMINANCE / Math.max(hsl.l, EMISSIVE_MIN_LIGHTNESS),
          EMISSIVE_COLOR_MAX_INTENSITY,
        )
  }
  const image = mat.emissiveMap.image as CanvasImageSource | undefined
  if (!image) return EMISSIVE_INTENSITY_BOOST
  // 缩到 16x16 采样：足以判断主色调，避免整图逐像素开销
  const SAMPLE_SIZE = 16
  const canvas = document.createElement('canvas')
  canvas.width = SAMPLE_SIZE
  canvas.height = SAMPLE_SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) return EMISSIVE_INTENSITY_BOOST
  ctx.drawImage(image, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
  const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
  let saturationSum = 0
  let lightnessSum = 0
  let pixelCount = 0
  for (let i = 0; i < data.length; i += 4) {
    // 循环边界由 data.length 保证，索引一定存在
    const r = data[i]! / 255
    const g = data[i + 1]! / 255
    const b = data[i + 2]! / 255
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    // 纯黑像素不参与统计（贴图留黑边不影响判断）
    if (max === 0) continue
    saturationSum += (max - min) / max
    lightnessSum += max
    pixelCount++
  }
  if (pixelCount === 0) return EMISSIVE_INTENSITY_BOOST
  const avgSaturation = saturationSum / pixelCount
  const avgLightness = lightnessSum / pixelCount
  return avgSaturation < EMISSIVE_SATURATION_THRESHOLD
    ? EMISSIVE_WHITE_INTENSITY
    : Math.min(
        EMISSIVE_COLOR_TARGET_LUMINANCE / Math.max(avgLightness, EMISSIVE_MIN_LIGHTNESS),
        EMISSIVE_COLOR_MAX_INTENSITY,
      )
}

/**
 * 生成水管线圈的红黑条纹贴图：条纹沿 UV U 方向交替（配合 repeat 形成环带状分段），
 * 还原弹簧束线罩的红黑交替观感。GLB 中线圈红色信息已丢失（见 case-constants 注释）。
 */
function createCoilStripeTexture(): THREE.CanvasTexture {
  const WIDTH = 256
  const HEIGHT = 8
  const canvas = document.createElement('canvas')
  canvas.width = WIDTH
  canvas.height = HEIGHT
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = COIL_STRIPE_RED
  ctx.fillRect(0, 0, WIDTH * COIL_STRIPE_RED_RATIO, HEIGHT)
  ctx.fillStyle = COIL_STRIPE_BLACK
  ctx.fillRect(WIDTH * COIL_STRIPE_RED_RATIO, 0, WIDTH, HEIGHT)
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.repeat.set(COIL_STRIPE_REPEAT, 1)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/**
 * 水管线圈定向处理：线圈体（Wires_Wires_*）与平滑水管共用 Tubes 材质，必须克隆后
 * 单独赋条纹贴图，否则平滑水管会一起被染成红黑条纹。
 */
function applyCoilStripes(mesh: THREE.Mesh): void {
  const source = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material
  if (!(source instanceof THREE.MeshStandardMaterial)) return
  const coilMat = source.clone()
  coilMat.map = createCoilStripeTexture()
  coilMat.color.setHex(0xffffff)
  // 弹簧罩是烤漆金属丝质感：中等金属度 + 中低粗糙度，让红段有光泽反射
  coilMat.metalness = 0.35
  coilMat.roughness = 0.45
  mesh.material = coilMat
}

/** 玻璃识别：材质名会被 Blender 导出错乱，用「网格名 + 材质名」双重判断 */
function isGlassMaterial(meshName: string, mat: THREE.MeshStandardMaterial): boolean {
  return meshName.toLowerCase().includes('glass') || GLASS_MATERIAL_NAMES.has(mat.name)
}

/** 玻璃恢复透明质感；命中玻璃时返回 true，调用方不再走普通材质分支 */
function repairGlassMaterial(meshName: string, mat: THREE.MeshStandardMaterial): boolean {
  if (!isGlassMaterial(meshName, mat)) return false

  mat.transparent = true
  mat.opacity = GLASS_OPACITY
  mat.metalness = 0
  // 低粗糙度让环境反射边缘锐利，是「钢化玻璃」观感的关键
  mat.roughness = 0.02
  // 单独拉高玻璃反射（与全局 ENV_INTENSITY 相乘），否则玻璃反射被压没显得像塑料膜
  mat.envMapIntensity = GLASS_ENV_INTENSITY
  // 压暗白底色贴图，避免玻璃呈灰蒙蒙蒙罩
  mat.color.setHex(GLASS_TINT_COLOR)
  // 透明面不写深度缓冲：避免玻璃提前截断内部件的渲染排序
  mat.depthWrite = false

  if (mat.name === 'GlassFront') {
    // 装饰发光侧板：不透明黑底 + ROG 图案发光。
    // 不能走玻璃的透明度——透明混合会同时稀释 emissive，图案会淡到不可见
    mat.transparent = false
    mat.opacity = 1
    mat.depthWrite = true
    mat.color.setHex(0x000000)
    // emissive 底色置白让贴图原色透出；双面渲染保证内外侧都能看到图案
    mat.emissive.setHex(0xffffff)
    mat.emissiveIntensity = GLASS_FRONT_EMISSIVE_INTENSITY
    mat.side = THREE.DoubleSide
  } else {
    // 观景门玻璃保持透亮无图案，避免遮挡内部视线
    mat.emissiveIntensity = 0
  }
  return true
}

/** 单个网格材质的完整修复流程（玻璃已在上游短路返回） */
function repairMeshMaterial(mesh: THREE.Mesh, mat: THREE.MeshStandardMaterial): void {
  // 水冷头 Logo 板：径向 alphaMap 裁圆贴合泵体轮廓；
  // GLB 缺失 Logo 遮罩，用源文件异步补乘合成（完成后 needsUpdate 自动刷新）
  if (mat.name === 'LogoWaterCooling') {
    mat.transparent = true
    mat.alphaMap = createRadialAlphaTexture()
    void applyLogoEmissiveMask(mat)
  }
  // 水管线圈体：红黑条纹定向还原（在无贴图压暗之前处理，避免被 NO_MAP_DARKEN 覆盖）
  if (mesh.name.startsWith('Wires_Wires')) {
    applyCoilStripes(mesh)
    return
  }
  if (mat.metalness > 0.9 && mat.roughness >= FAKE_METAL_ROUGHNESS_THRESHOLD) {
    mat.metalness = FAKE_METAL_FIX_METALNESS
    mat.roughness = FAKE_METAL_FIX_ROUGHNESS
  }
  // 无贴图且不发光的材质压暗为深灰黑（否则一律显示为浅灰白）
  if (!mat.map && !mat.emissiveMap && mat.emissive.getHex() === 0) {
    mat.color.setHex(NO_MAP_DARKEN_COLOR)
  }
  // 仅自发光无漫反射贴图的材质（Logo/灯条底板）压黑底色，让 emissiveMap 图案显形
  if (!mat.map && mat.emissiveMap) {
    mat.color.setHex(EMISSIVE_ONLY_DARKEN_COLOR)
  }
  // 自发光分档：有贴图的按贴图色彩判断；无贴图但 emissive 有色的（RGB 灯条）按颜色判断
  if (mat.emissiveMap || mat.emissive.getHex() !== 0) {
    mat.emissiveIntensity = resolveEmissiveIntensity(mat)
  }
  // 选择性 Bloom：真正发光的网格额外挂到辉光图层，辉光相机只渲染该图层，
  // 把机身镜面高光排除出光晕管线。保留 layer 0，射线拾取/锚点投影不受影响。
  if (mat.emissiveIntensity > 0 && (mat.emissiveMap || mat.emissive.getHex() !== 0)) {
    mesh.layers.enable(BLOOM_LAYER)
  }
}

/**
 * 机箱模型材质修复（GLB 导出缺陷的集中处理）：
 * 1) 玻璃类强制恢复透明质感（导出把玻璃设成不透明假金属 → 白色实心板的根因）
 * 2) 假金属修复（metalness=1 + roughness=1 → 压低，消除面板灰白化）
 * 3) 其余按贴图色彩分档（白色低压防白爆，彩色高压保发光感）
 */
export function repairCaseMaterials(modelRoot: THREE.Group): void {
  modelRoot.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((mat) => {
      if (!(mat instanceof THREE.MeshStandardMaterial)) return
      if (repairGlassMaterial(child.name, mat)) return
      repairMeshMaterial(child, mat)
    })
  })
}
