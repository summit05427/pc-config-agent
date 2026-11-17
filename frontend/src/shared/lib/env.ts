/**
 * 环境变量唯一读取出口。
 *
 * 业务代码不直接访问 `import.meta.env`，避免同一地址在不同模块出现多份来源。
 * 生产环境的必填项与格式由 `scripts/check-env.mjs` 在构建前拦截；这里对缺失值
 * 保留开发/测试可用的兜底，保证单元测试与本地空配置也能启动。
 */

const APP_ENVS = ['development', 'production'] as const
const DEFAULT_API_BASE_URL = '/api/v1'
const DEFAULT_API_V2_BASE_URL = '/api/v2'
const API_V1_PATH_SUFFIX = '/v1'
const DEFAULT_AGENT_BASE_URL = '/agent/api/v1'
const DEFAULT_API_TIMEOUT = 10_000
const DEFAULT_APP_TITLE = 'PC Build Agent'
const DEFAULT_APP_ENV = 'development'

export type AppEnv = (typeof APP_ENVS)[number]

export interface AppEnvConfig {
  readonly title: string
  readonly appEnv: AppEnv
  readonly apiBaseUrl: string
  /** v2 语义端点与 v1 同源，只把版本段替换为 `/v2` */
  readonly apiV2BaseUrl: string
  readonly agentBaseUrl: string
  readonly apiTimeout: number
  readonly useMock: boolean
  /** 生成式 UI 开关，默认关闭；关闭时 OpenUI 相关代码不会进入渲染路径 */
  readonly openUiEnabled: boolean
  /** 是否展示工具执行轨迹（仅开发排查用）；面向用户的默认视图只保留思考过程 */
  readonly showExecutionTrace: boolean
}

const isAppEnv = (value: string): value is AppEnv => APP_ENVS.some((item) => item === value)

const readString = (value: string | undefined, fallback: string): string =>
  value && value.trim().length > 0 ? value : fallback

const toPositiveNumber = (value: string | undefined, fallback: number): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

/**
 * 派生 v2 基址。
 *
 * axios 会把请求地址拼到 `baseURL` 之后，直接请求 `/v2/models` 会得到
 * `/api/v1/v2/models`，与 Java 的 `/api/v2/models` 不符；这里显式拆出 v2 基址，
 * 避免各调用点自行拼接版本段。前缀不是 `/v1` 时退回默认相对路径。
 */
const toApiV2BaseUrl = (apiBaseUrl: string): string =>
  apiBaseUrl.endsWith(API_V1_PATH_SUFFIX)
    ? `${apiBaseUrl.slice(0, -API_V1_PATH_SUFFIX.length)}/v2`
    : DEFAULT_API_V2_BASE_URL

const readEnv = (): AppEnvConfig => {
  const rawAppEnv = readString(import.meta.env.VITE_APP_ENV, DEFAULT_APP_ENV)
  const apiBaseUrl = readString(import.meta.env.VITE_API_BASE_URL, DEFAULT_API_BASE_URL)

  return {
    title: readString(import.meta.env.VITE_APP_TITLE, DEFAULT_APP_TITLE),
    appEnv: isAppEnv(rawAppEnv) ? rawAppEnv : DEFAULT_APP_ENV,
    apiBaseUrl,
    apiV2BaseUrl: toApiV2BaseUrl(apiBaseUrl),
    agentBaseUrl: readString(import.meta.env.VITE_AGENT_BASE_URL, DEFAULT_AGENT_BASE_URL),
    apiTimeout: toPositiveNumber(import.meta.env.VITE_API_TIMEOUT, DEFAULT_API_TIMEOUT),
    useMock: import.meta.env.VITE_USE_MOCK === 'true',
    openUiEnabled: import.meta.env.VITE_OPENUI_ENABLED === 'true',
    showExecutionTrace: import.meta.env.VITE_SHOW_EXECUTION_TRACE === 'true',
  }
}

export const env: AppEnvConfig = Object.freeze(readEnv())
