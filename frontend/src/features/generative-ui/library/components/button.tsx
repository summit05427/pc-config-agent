import {
  action,
  defineComponent,
  useFormName,
  useIsStreaming,
  useTriggerAction,
} from '@openuidev/react-lang'
import { Button as OpenUiButton } from '@openuidev/react-ui/Button'
import { useEffect, useState } from 'react'
import { z } from 'zod'

type LangButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost'

/**
 * Lang 契约的四种语气到官方 Button 变体的映射。
 *
 * 官方只有 primary / secondary / tertiary 三档：outline 与 ghost 都是低强调操作，
 * 分别落到 secondary（带边框）与 tertiary（无边框），避免在适配层自造配色。
 */
const VARIANT_MAP: Record<LangButtonVariant, 'primary' | 'secondary' | 'tertiary'> = {
  primary: 'primary',
  secondary: 'secondary',
  outline: 'secondary',
  ghost: 'tertiary',
}

/** 确认态自动复原时间，避免用户误点后按钮一直停留在危险样式 */
const CONFIRM_RESET_MS = 3000
const DEFAULT_CONFIRM_MESSAGE = '再次点击确认'

/**
 * 交互按钮。
 *
 * 动作由 OpenUI Runtime 解释成 ActionEvent，再经 features/generative-ui/library/actions
 * 白名单转发；组件本身不执行任何 URL 或请求逻辑，避免把安全边界放在渲染层。
 * 位于 Form 内时通过 useFormName 取到表单名，提交会带上全部字段值。
 */
export const Button = defineComponent({
  name: 'Button',
  description: '可点击按钮；没有配置 action 时把按钮文案作为继续对话的消息',
  props: z.object({
    label: z.string().describe('按钮文案'),
    action: action().optional().describe('点击动作，仅支持 @OpenUrl 与 @ToAssistant'),
    variant: z.enum(['primary', 'secondary', 'outline', 'ghost']).optional().describe('视觉样式'),
    confirm: z.boolean().optional().describe('为 true 时需再次点击确认，用于删除、提交等操作'),
    confirmMessage: z.string().optional().describe('确认态的按钮文案，默认「再次点击确认」'),
  }),
  // 具名函数表达式让 react-hooks 按组件识别，避免把渲染函数误判为普通函数
  component: function ButtonView({ props }) {
    const isStreaming = useIsStreaming()
    const triggerAction = useTriggerAction()
    const formName = useFormName()
    const [isConfirming, setIsConfirming] = useState(false)
    const langVariant = props.variant ?? 'primary'
    // 官方主按钮默认用强调色描边；CDS 主操作是纯色 pill，因此去掉这条描边
    const borderClass = langVariant === 'primary' || isConfirming ? 'border-transparent' : ''

    useEffect(() => {
      if (!isConfirming) {
        return undefined
      }

      const timer = window.setTimeout(() => setIsConfirming(false), CONFIRM_RESET_MS)
      return () => window.clearTimeout(timer)
    }, [isConfirming])

    const handleClick = (): void => {
      // 首次点击只进入确认态，第二次点击才真正回传动作
      if (props.confirm === true && !isConfirming) {
        setIsConfirming(true)
        return
      }

      setIsConfirming(false)
      // 无 action 时 Runtime 会用 label 作为 humanFriendlyMessage 继续对话
      void triggerAction(props.label, formName, props.action)
    }

    return (
      <OpenUiButton
        type="button"
        size="small"
        variant={VARIANT_MAP[langVariant]}
        // 确认态复用官方 destructive 配色，避免自写红色样式
        buttonType={isConfirming ? 'destructive' : 'normal'}
        disabled={isStreaming}
        onClick={handleClick}
        // w-fit 让按钮保持内容宽度，不被父级 flex 拉伸
        className={`w-fit ${borderClass}`}
      >
        {isConfirming ? (props.confirmMessage ?? DEFAULT_CONFIRM_MESSAGE) : props.label}
      </OpenUiButton>
    )
  },
})
