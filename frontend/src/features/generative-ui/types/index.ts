/** Generative UI 的公共类型：只描述前端契约，不依赖 OpenUI 运行时 */
export type UiSegment =
  | {
      readonly kind: 'markdown'
      readonly id: string
      readonly content: string
      readonly startOffset: number
    }
  | {
      readonly kind: 'openui'
      readonly id: string
      readonly content: string
      readonly startOffset: number
      /** 围栏是否闭合；流式期间尾块可能为 false */
      readonly isComplete: boolean
    }

export interface SplitUiBlocksResult {
  readonly segments: readonly UiSegment[]
  readonly hasOpenUi: boolean
  readonly hasIncompleteOpenUi: boolean
}

/** 组件状态记录带版本，组件升级后不错误恢复旧结构 */
export interface OpenUiStateRecord {
  readonly version: number
  readonly values: Record<string, unknown>
}

export type OpenUiFormFieldValue = string | number | boolean | readonly string[]

/**
 * 表单提交载荷。
 *
 * 只保留可安全序列化的标量、字符串数组，嵌套对象与函数一律丢弃，
 * 避免把运行时内部结构（组件实例、事件对象）带进对话消息。
 */
export interface OpenUiFormSubmission {
  readonly formName?: string
  readonly fields: Readonly<Record<string, OpenUiFormFieldValue>>
  readonly message: string
}

/**
 * 渲染器对宿主暴露的契约。
 *
 * 动作只以回调形式出现，具体打开链接与发送消息由调用方决定；
 * 这样 P4 接入消息列表时可以直接复用现有提交流程，不需要在渲染层复制业务逻辑。
 */
export interface OpenUiRendererProps {
  readonly response: string
  readonly isStreaming?: boolean
  readonly initialState?: Record<string, unknown>
  readonly onStateUpdate?: (state: Record<string, unknown>) => void
  readonly onOpenUrl?: (url: string) => void
  readonly onContinueConversation?: (message: string) => void
  /** 表单提交时优先回调；未提供时字段文本会并入 onContinueConversation 的消息 */
  readonly onSubmitForm?: (submission: OpenUiFormSubmission) => void
  readonly className?: string
}
