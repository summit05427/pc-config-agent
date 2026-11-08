/**
 * 登录态的唯一出口：内存令牌、刷新单飞与 401 决策。
 *
 * 两个请求适配器（axios 处理 Java 信封、fetch 处理 Agent 裸 JSON / SSE）只负责搬运请求，
 * 不再各自推导「401 该不该刷新、何时清理、何时跳转」。刷新实现与全局跳转由启动处
 * `configureAuth` 显式注入，core 不反向依赖 feature 与 router。
 */

export const AUTHORIZATION_HEADER = 'Authorization'

const BEARER_PREFIX = 'Bearer '

type RefreshHandler = () => Promise<string | null>
type UnauthorizedHandler = () => void

/**
 * 401 之后的行为策略，由调用方按端点的语义声明。
 *
 * - `default`：先刷新并重放一次，刷新失败才清理令牌并跳转
 * - `no-refresh`：跳过刷新，但仍执行清理与全局跳转（如 logout）
 * - `no-redirect`：跳过刷新与全局跳转，401 原样交给调用方（如 login / refresh）
 */
export type AuthPolicy = 'default' | 'no-refresh' | 'no-redirect'

export type UnauthorizedAction = 'replay' | 'redirect' | 'reject'

export interface AuthConfig {
  /** 用 HttpOnly Cookie 换取新 Access Token，失败返回 null */
  refresh: RefreshHandler
  /** 全局 401 收尾：清理登录态并跳转登录页 */
  onUnauthorized: UnauthorizedHandler
}

export interface UnauthorizedContext {
  policy?: AuthPolicy
  /** 已因 401 重放过一次，避免刷新成功但接口仍 401 时无限循环 */
  isReplayed?: boolean
}

// Access Token 只存内存：刷新页面后由 HttpOnly Cookie 换取新令牌，
// 禁止写入 localStorage / sessionStorage / Zustand 持久化，避免 XSS 直接窃取
let accessToken = ''
let refreshHandler: RefreshHandler | null = null
let unauthorizedHandler: UnauthorizedHandler | null = null
// 并发 401 共用同一个刷新 Promise，保证服务端只看到一次轮换
let pendingRefresh: Promise<string | null> | null = null
// 并发 401 只处理一次全局跳转
let isUnauthorizedHandled = false

/** 启动时装配刷新与跳转实现；测试可在每个用例前重新装配 */
export const configureAuth = ({ refresh, onUnauthorized }: AuthConfig): void => {
  refreshHandler = refresh
  unauthorizedHandler = onUnauthorized
  pendingRefresh = null
  isUnauthorizedHandled = false
}

/**
 * 接受一个已生效的 Access Token。
 *
 * 与「重置 401 单飞标记」绑定：新会话建立后允许下一次 401 再次触发全局跳转，
 * 调用方不再需要记得同时调用两个函数。
 */
export const acceptToken = (token: string): void => {
  accessToken = token
  isUnauthorizedHandled = false
}

/**
 * 丢弃内存令牌。
 *
 * 同时取消进行中的刷新引用，避免其完成后把旧令牌写回。
 */
export const clearToken = (): void => {
  accessToken = ''
  pendingRefresh = null
}

export const getAccessToken = (): string => accessToken

/** 统一的 Authorization 头；未登录返回空对象，便于直接展开合并 */
export const authHeader = (): Record<string, string> =>
  accessToken ? { [AUTHORIZATION_HEADER]: `${BEARER_PREFIX}${accessToken}` } : {}

/**
 * 触发一次刷新（带单飞）。
 *
 * 并发调用共享同一个 Promise；刷新失败返回 null，由调用方清理登录态。
 * 未装配刷新实现时直接返回 null，便于单测与未登录场景。
 */
export const refreshOnce = (): Promise<string | null> => {
  if (!refreshHandler) {
    return Promise.resolve(null)
  }

  if (!pendingRefresh) {
    pendingRefresh = refreshHandler()
      .catch(() => null)
      .finally(() => {
        pendingRefresh = null
      })
  }

  return pendingRefresh
}

const notifyUnauthorizedOnce = (): void => {
  if (isUnauthorizedHandled || !unauthorizedHandler) {
    return
  }

  isUnauthorizedHandled = true
  unauthorizedHandler()
}

/**
 * 401 决策：刷新并重放、清理后跳转，或原样交给调用方。
 *
 * 副作用（清令牌、触发跳转）只发生在这里，两个适配器按返回值执行重放与错误归一化。
 */
export const handleUnauthorized = async (
  context: UnauthorizedContext = {},
): Promise<UnauthorizedAction> => {
  const policy = context.policy ?? 'default'

  if (policy === 'no-redirect') {
    return 'reject'
  }

  if (policy === 'default' && !context.isReplayed) {
    const token = await refreshOnce()
    if (token) {
      return 'replay'
    }
  }

  clearToken()
  notifyUnauthorizedOnce()
  return 'redirect'
}

/** 测试专用：清空令牌、进行中的刷新与已装配的适配器 */
export const resetAuthForTests = (): void => {
  accessToken = ''
  refreshHandler = null
  unauthorizedHandler = null
  pendingRefresh = null
  isUnauthorizedHandled = false
}
