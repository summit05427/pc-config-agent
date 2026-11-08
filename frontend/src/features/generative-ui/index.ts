/**
 * Generative UI 的公共出口。
 *
 * 其他 feature 只从这里取渲染组件与切分函数，不直接深入 components/ 或 utils/，
 * 后续替换内部实现时调用方无需改动。
 */
export { OpenUiBlock } from './components/openui-block'
export { useOpenUiEnabled } from './hooks/use-openui'
export { splitUiBlocks } from './utils/split-ui-blocks'
export type {
  OpenUiFormSubmission,
  SplitUiBlocksResult,
  UiSegment,
} from './types'
