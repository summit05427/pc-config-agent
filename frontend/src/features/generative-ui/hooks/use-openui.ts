import { env } from '@/shared/lib/env'

/**
 * 生成式 UI 的前端开关。
 *
 * 默认关闭；关闭时渲染入口直接返回空，调用方仍按普通 Markdown 展示原始内容，
 * 因此切换开关不会影响现有聊天链路。
 */
export function useOpenUiEnabled(): boolean {
  return env.openUiEnabled
}
