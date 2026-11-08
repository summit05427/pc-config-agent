import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, Square } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

const DEFAULT_MAX_LENGTH = 4000
const MAX_HEIGHT = 208
const COUNTER_THRESHOLD = 0.8
const COMPOSER_ID = 'chat-composer'

export interface ChatComposerProps {
  readonly isStreaming?: boolean
  readonly disabled?: boolean
  readonly placeholder?: string
  readonly maxLength?: number
  readonly autofocus?: boolean
  /** 发送按钮左侧的操作槽位（当前用于会话模型选择器） */
  readonly modelPicker?: ReactNode
  readonly onSend: (text: string) => void
  readonly onStop: () => void
}

/**
 * 对话输入框。
 *
 * Enter 发送、Shift+Enter 换行，输入法组合期间不触发发送；生成中把发送按钮
 * 换成停止按钮，提交态由 streaming 直接禁用，避免重复请求。
 */
export function ChatComposer({
  isStreaming = false,
  disabled = false,
  placeholder,
  maxLength = DEFAULT_MAX_LENGTH,
  autofocus = false,
  modelPicker = null,
  onSend,
  onStop,
}: ChatComposerProps) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const isComposingRef = useRef(false)

  const canSubmit = text.trim().length > 0 && !isStreaming && !disabled
  const showCounter = text.length > maxLength * COUNTER_THRESHOLD

  // 高度只能由 DOM 写入：控制的是内容自适应，与样式 Token 无关
  const resize = useCallback((): void => {
    const element = textareaRef.current
    if (!element) {
      return
    }
    element.style.height = 'auto'
    const nextHeight = Math.min(element.scrollHeight, MAX_HEIGHT)
    element.style.height = `${nextHeight}px`
    element.style.overflowY = element.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'
  }, [])

  useEffect(() => {
    resize()
  }, [text, resize])

  useEffect(() => {
    if (autofocus) {
      textareaRef.current?.focus()
    }
  }, [autofocus])

  const submit = (): void => {
    if (!canSubmit) {
      return
    }
    onSend(text)
    setText('')
    window.requestAnimationFrame(() => {
      resize()
      textareaRef.current?.focus()
    })
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key !== 'Enter' || event.shiftKey || isComposingRef.current) {
      return
    }
    event.preventDefault()
    submit()
  }

  return (
    <div className="rounded-[var(--cds-radius-composer)] bg-surface p-2 shadow-[var(--cds-shadow-composer)] transition-shadow duration-200 hover:shadow-[var(--cds-shadow-composer-hover)] focus-within:shadow-[var(--cds-shadow-composer-focus)]">
      <label htmlFor={COMPOSER_ID} className="sr-only">
        {t('chat.composer.label')}
      </label>
      <textarea
        id={COMPOSER_ID}
        ref={textareaRef}
        rows={1}
        maxLength={maxLength}
        placeholder={placeholder || t('chat.composer.placeholder')}
        disabled={disabled}
        className="block max-h-52 min-h-11 w-full resize-none bg-transparent px-2 py-2.5 text-[0.9375rem] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          isComposingRef.current = true
        }}
        onCompositionEnd={() => {
          isComposingRef.current = false
        }}
      />

      <div className="mt-1 flex items-center gap-2 pl-2">
        {showCounter ? (
          <span
            className={cn(
              'tabular text-[0.6875rem]',
              text.length >= maxLength ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            {text.length} / {maxLength}
          </span>
        ) : null}

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {modelPicker}

          {isStreaming ? (
            <Button
              variant="outline"
              size="icon"
              className="rounded-full"
              aria-label={t('chat.composer.stop')}
              onClick={onStop}
            >
              <Square className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon"
              className="rounded-full"
              disabled={!canSubmit}
              aria-label={t('chat.composer.send')}
              onClick={submit}
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
