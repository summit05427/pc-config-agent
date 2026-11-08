/**
 * Java 服务的统一响应信封。
 *
 * 成功时 `code` 固定为 0，真实业务数据在 `data` 中；失败时 `message` 面向调用方，
 * 不包含堆栈、SQL 或服务器路径。
 */
export interface ApiEnvelope<T> {
  code: number
  errorType?: string
  message?: string
  data?: T
  requestId?: string
}

/** 分页响应的固定结构，服务端强制 page ≥ 1、1 ≤ size ≤ 100。 */
export interface PageResult<T> {
  list: T[]
  total: number
  page: number
  size: number
}
