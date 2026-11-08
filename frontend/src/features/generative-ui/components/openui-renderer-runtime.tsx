import { Renderer, type ActionEvent } from '@openuidev/react-lang'

import { cn } from '@/shared/lib/utils'

import { dispatchOpenUiAction } from '../library/actions'
import { OPENUI_LIBRARY } from '../library'
import type { OpenUiRendererProps } from '../types'

/**
 * 真实渲染层。
 *
 * 这个模块只在开关打开时被懒加载，OpenUI 运行时不进入普通聊天的首屏包体。
 * Renderer 只接受纯 OpenUI Lang；Markdown 与 UI 块的切分由上层 splitter 完成。
 */
export function OpenUiRendererRuntime({
  response,
  isStreaming = false,
  initialState,
  onStateUpdate,
  onOpenUrl,
  onContinueConversation,
  onSubmitForm,
  className,
}: OpenUiRendererProps) {
  const handleAction = (event: ActionEvent): void => {
    // 所有动作都必须经过白名单；未注册类型与非法 URL 在桥接层丢弃
    dispatchOpenUiAction(event, {
      ...(onOpenUrl ? { onOpenUrl } : {}),
      ...(onContinueConversation ? { onContinueConversation } : {}),
      ...(onSubmitForm ? { onSubmitForm } : {}),
    })
  }

  return (
    <div className={cn('openui-theme-scope min-w-0 text-sm text-foreground', className)}>
      <Renderer
        response={response}
        library={OPENUI_LIBRARY}
        isStreaming={isStreaming}
        initialState={initialState}
        onStateUpdate={onStateUpdate}
        onAction={handleAction}
      />
    </div>
  )
}
