/**
 * 机箱 3D 渲染全部调参常量。
 * 职责边界：只放「数字与配置」，不放逻辑；调渲染效果优先改这个文件。
 * 移植自 Vue 版 computer-case，资源路径与模型文件名保持不变。
 */

// ============ 模型与相机 ============

// 模型初始朝向（绕 Y 轴）：把玻璃侧板斜对相机透出内部 RGB、前脸在右露出
export const MODEL_FRONT_YAW = Math.PI / 3
// 模型统一缩放（GLB 原始尺寸过大）
export const MODEL_SCALE = 0.03
// GLB 资源路径（public/ComputerCase6.glb）
export const MODEL_URL = '/ComputerCase6.glb'
// 相机距离系数：1 表示模型刚好贴满视野，>1 留白越多（默认取 2.1，让机箱四周留出呼吸空间）
export const CAMERA_DISTANCE_FACTOR = 2.1
// 点击标记后飞向目标组件的取景距离（相对模型最大维度的比例）
export const FOCUS_DISTANCE_FACTOR = 0.45
// 相机补间时长（毫秒）
export const FOCUS_DURATION_MS = 800

// ============ 灯光（暗调摄影棚三点布光） ============

// 环境光：极低强度仅消除死黑，主要环境照明由环境贴图承担
export const AMBIENT_LIGHT_INTENSITY = 0.08
// 主光 key：右前上方，塑造机箱面板立体感（强度过高会把拉丝金属板打爆成白板）
export const KEY_LIGHT_INTENSITY = 0.8
export const KEY_LIGHT_POSITION: readonly [number, number, number] = [4, 6, 8]
// 补光 fill：左前方低强度，填充暗部让黑色本体细节可辨
export const FILL_LIGHT_INTENSITY = 0.25
export const FILL_LIGHT_POSITION: readonly [number, number, number] = [-6, 2, 4]
// 轮廓光 rim：后上方，勾勒机箱顶部与侧边的高光边缘
export const RIM_LIGHT_INTENSITY = 0.5
export const RIM_LIGHT_POSITION: readonly [number, number, number] = [0, 8, -6]
// 机箱内部点光源基准强度（在基准尺寸下标定）：只负责照亮内部结构，RGB 亮度主要来自自发光
export const INSIDE_LIGHT_INTENSITY = 2.5
// 点光源标定基准尺寸：scale=0.01 时的模型最大维度（约 6.2，由相机距离反推实测）。
// 物理衰减下照度 ∝ 强度/距离²，模型缩放后内部部件离光源更远，强度须按尺寸平方补偿。
export const INSIDE_LIGHT_BASE_SIZE = 6.2

// ============ 材质修复 ============

// 玻璃类材质名单：GLB 导出后材质名可能错乱，同时用网格名做兜底识别
export const GLASS_MATERIAL_NAMES = new Set(['GlassDoor', 'GlassFront'])
// 「假金属」粗糙度下限：Blender 导出异常导致 metalness=1 且 roughness=1，
// 完全粗糙的纯金属会把环境光均匀漫反射成灰白色（黑色机箱变白板的根因）
export const FAKE_METAL_ROUGHNESS_THRESHOLD = 0.8
// 假金属修复目标：压低金属度让贴图深色回归「黑色哑光」，保留少量金属反射质感
export const FAKE_METAL_FIX_METALNESS = 0.25
export const FAKE_METAL_FIX_ROUGHNESS = 0.75
// 玻璃透明度：钢化玻璃轻微蒙罩、内部 RGB 清晰可见
export const GLASS_OPACITY = 0.22
// 玻璃底色压暗：玻璃贴图是白底色，不压会形成灰蒙蒙蒙罩
export const GLASS_TINT_COLOR = 0x555555
// 玻璃环境反射增强倍率：与全局 ENV_INTENSITY 相乘后有效值约 1.2
export const GLASS_ENV_INTENSITY = 8
// 侧板玻璃（GlassFront）自带的 ROG 几何发光图案强度
export const GLASS_FRONT_EMISSIVE_INTENSITY = 1.2
// 无贴图材质压暗色：模型所有材质底色都是 #e7e7e7，真实颜色依赖贴图
export const NO_MAP_DARKEN_COLOR = 0x2a2a2a
// 仅自发光材质（无漫反射贴图但有 emissiveMap）底色压黑，让发光图案显形
export const EMISSIVE_ONLY_DARKEN_COLOR = 0x141414
// 水冷头 Logo 遮罩源文件（public/textures）
export const LOGO_MASK_URL = '/textures/AsusRog.jpg'

// ============ 水管线圈红黑条纹（Wires 网格）============

// 线圈体（Wires_Wires_0）与平滑水管共用 Tubes 材质且无颜色贴图（红色信息在导出时丢失）
export const COIL_STRIPE_RED = '#b32223'
export const COIL_STRIPE_BLACK = '#141414'
/** 红段在单周期内的占比：红段为主、黑段间隔较短 */
export const COIL_STRIPE_RED_RATIO = 0.62
/** 条纹沿 UV U 方向的重复周期数，产生环带状分段 */
export const COIL_STRIPE_REPEAT = 4

// ============ 环境与自发光分档 ============

// 环境贴图反射强度：只提供金属/玻璃的反射质感
export const ENV_INTENSITY = 0.15
// 自发光增强倍数：超过 ~1.5 后 ACES 色调映射会把彩色压向白色
export const EMISSIVE_INTENSITY_BOOST = 1.4
// 白色系发光件强度：白光贴图过高会把扇面整个白爆成光团
export const EMISSIVE_WHITE_INTENSITY = 0.8
// 彩色系目标视觉亮度：按贴图亮度反比补偿强度
export const EMISSIVE_COLOR_TARGET_LUMINANCE = 1.6
// 亮度补偿下限：防止暗贴图把强度推得过高产生噪点
export const EMISSIVE_MIN_LIGHTNESS = 0.25
// 彩色系强度上限：暗贴图补偿值过大时截断
export const EMISSIVE_COLOR_MAX_INTENSITY = 3.5
// 饱和度分档阈值（HSV 近似）：低于该值视为白色/灰白系发光
export const EMISSIVE_SATURATION_THRESHOLD = 0.25
// 点睛光效低强度覆盖（按材质名子串匹配，先命中先用）
export const EMISSIVE_DIM_OVERRIDES: ReadonlyArray<readonly [string, number]> = [
  ['AsusRogThor_corpus', 0.8], // 电源区 REPUBLIC 文字与 ROG Logo
  ['CoolerRGB', 0.2], // 风扇 RGB 灯环
  ['RGB_Lighting', 0.2], // 泵体 RGB 灯环
  ['LogoWaterCooling', 1.2], // 水冷头 Logo
]

// ============ 辉光（后期合成） ============

// 选择性 Bloom 图层号：自发光网格额外挂到此图层
export const BLOOM_LAYER = 1
// 辉光强度：光晕亮度
export const BLOOM_STRENGTH = 0.5
// 辉光半径：光晕扩散范围
export const BLOOM_RADIUS = 0.5
// 辉光阈值：只有亮度超过此值的像素产生光晕
export const BLOOM_THRESHOLD = 0.85

// ============ 组件标记点 ============

/** 标记点配置：运行时按网格名前缀匹配定位，无需手工填 3D 坐标（模型换版本自适应） */
export interface MarkerConfig {
  /** 唯一标识，同时用于选中态判断 */
  id: string
  /** 标记显示名 */
  label: string
  /** 目标网格名前缀（GLB traverse 按 startsWith 命中第一个） */
  meshNamePrefix: string
}

export const CASE_MARKERS: readonly MarkerConfig[] = [
  { id: 'cpu', label: 'CPU', meshNamePrefix: 'LogoWaterCooling' },
  // 冷排（顶部 360 水冷排热区）；CPU 裸片被泵头遮挡、硬盘在模型中无对应网格
  { id: 'radiator', label: '散热', meshNamePrefix: 'Radiator360' },
  { id: 'ram', label: '内存', meshNamePrefix: 'TridenZ5Black1' },
  { id: 'gpu', label: '显卡', meshNamePrefix: 'AsusRog3090' },
  { id: 'motherboard', label: '主板', meshNamePrefix: 'AsusMotherboard' },
  { id: 'psu', label: '电源', meshNamePrefix: 'PowerSupply' },
]
