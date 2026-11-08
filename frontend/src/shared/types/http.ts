/** 列表接口统一结构：list 永不为 null，total 为过滤后的总数 */
export interface PageResult<T> {
  list: T[]
  total: number
  page: number
  size: number
}
