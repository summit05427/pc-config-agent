import type { ActionEvent } from '@openuidev/react-lang'
import { describe, expect, it, vi } from 'vitest'

import { dispatchOpenUiAction, extractOpenUiFormSubmission, isSafeOpenUrl } from './index'

const createEvent = (patch: Partial<ActionEvent> = {}): ActionEvent => ({
  type: 'open_url',
  params: {},
  humanFriendlyMessage: '',
  ...patch,
})

describe('isSafeOpenUrl', () => {
  it.each(['https://example.com', 'http://example.com/path?x=1', '  https://example.com  '])(
    '放行 http/https 绝对地址：%s',
    (value) => {
      expect(isSafeOpenUrl(value)).toBe(true)
    },
  )

  it.each([
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'file:///etc/passwd',
    '/relative/path',
    '//evil.com',
    '',
    'not a url',
  ])('拒绝危险或非绝对地址：%s', (value) => {
    expect(isSafeOpenUrl(value)).toBe(false)
  })
})

describe('dispatchOpenUiAction', () => {
  it('open_url 放行并规范化首尾空白', () => {
    const onOpenUrl = vi.fn()
    const result = dispatchOpenUiAction(
      createEvent({ type: 'open_url', params: { url: '  https://example.com  ' } }),
      { onOpenUrl },
    )

    expect(result).toBe('handled')
    expect(onOpenUrl).toHaveBeenCalledWith('https://example.com')
  })

  it('open_url 遇到 javascript 协议直接拒绝且不触发回调', () => {
    const onOpenUrl = vi.fn()
    const result = dispatchOpenUiAction(
      createEvent({ type: 'open_url', params: { url: 'javascript:alert(1)' } }),
      { onOpenUrl },
    )

    expect(result).toBe('rejected')
    expect(onOpenUrl).not.toHaveBeenCalled()
  })

  it('未提供 open_url 回调时按忽略处理', () => {
    const result = dispatchOpenUiAction(
      createEvent({ type: 'open_url', params: { url: 'https://example.com' } }),
      {},
    )

    expect(result).toBe('ignored')
  })

  it('continue_conversation 转发去除空白的消息', () => {
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(
      createEvent({ type: 'continue_conversation', humanFriendlyMessage: '  继续聊聊  ' }),
      { onContinueConversation },
    )

    expect(result).toBe('handled')
    expect(onContinueConversation).toHaveBeenCalledWith('继续聊聊')
  })

  it('空消息不会触发新一轮对话', () => {
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(
      createEvent({ type: 'continue_conversation', humanFriendlyMessage: '   ' }),
      { onContinueConversation },
    )

    expect(result).toBe('ignored')
    expect(onContinueConversation).not.toHaveBeenCalled()
  })

  it('未注册的动作类型一律忽略', () => {
    const onOpenUrl = vi.fn()
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(createEvent({ type: 'delete_user' }), {
      onOpenUrl,
      onContinueConversation,
    })

    expect(result).toBe('ignored')
    expect(onOpenUrl).not.toHaveBeenCalled()
    expect(onContinueConversation).not.toHaveBeenCalled()
  })

  it('OpenBuildDetail 是纯前端动作：只触发详情回调，不发消息也不跳转', () => {
    const onOpenBuildDetail = vi.fn()
    const onOpenUrl = vi.fn()
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(
      createEvent({ type: 'OpenBuildDetail' }),
      { onOpenBuildDetail, onOpenUrl, onContinueConversation },
    )

    expect(result).toBe('handled')
    expect(onOpenBuildDetail).toHaveBeenCalledTimes(1)
    expect(onOpenUrl).not.toHaveBeenCalled()
    expect(onContinueConversation).not.toHaveBeenCalled()
  })

  it('宿主未提供详情回调时按忽略处理', () => {
    const result = dispatchOpenUiAction(createEvent({ type: 'OpenBuildDetail' }), {})

    expect(result).toBe('ignored')
  })
})

describe('extractOpenUiFormSubmission', () => {
  const formEvent = (): ActionEvent =>
    createEvent({
      type: 'continue_conversation',
      humanFriendlyMessage: '提交',
      formName: 'contact',
      formState: {
        contact: {
          name: { value: '张三', componentType: 'TextInput' },
          plan: { value: 'pro', componentType: 'Select' },
          tags: { value: ['导出', 'API'], componentType: 'CheckboxGroup' },
        },
      },
    })

  it('按表单名展平字段并生成可读消息', () => {
    const submission = extractOpenUiFormSubmission(formEvent())

    expect(submission?.formName).toBe('contact')
    expect(submission?.fields).toEqual({ name: '张三', plan: 'pro', tags: ['导出', 'API'] })
    expect(submission?.message).toBe('- name: 张三\n- plan: pro\n- tags: 导出、API')
  })

  it('无表单名时直接以字段名为键', () => {
    const submission = extractOpenUiFormSubmission(
      createEvent({
        type: 'continue_conversation',
        formState: { name: { value: '李四' } },
      }),
    )

    expect(submission?.formName).toBeUndefined()
    expect(submission?.fields).toEqual({ name: '李四' })
  })

  it('丢弃嵌套对象等不可安全序列化的值', () => {
    const submission = extractOpenUiFormSubmission(
      createEvent({
        type: 'continue_conversation',
        formName: 'contact',
        formState: {
          contact: {
            name: { value: '张三' },
            detail: { value: { nested: true } },
            callback: { value: () => 'x' },
          },
        },
      }),
    )

    expect(submission?.fields).toEqual({ name: '张三' })
  })

  it('没有有效字段时返回 null', () => {
    expect(
      extractOpenUiFormSubmission(createEvent({ type: 'continue_conversation', formState: {} })),
    ).toBeNull()
    expect(extractOpenUiFormSubmission(createEvent())).toBeNull()
  })

  it('提供 onSubmitForm 时走专用回调，不再触发继续对话', () => {
    const onSubmitForm = vi.fn()
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(formEvent(), { onSubmitForm, onContinueConversation })

    expect(result).toBe('handled')
    expect(onSubmitForm).toHaveBeenCalledWith(
      expect.objectContaining({ formName: 'contact', fields: expect.objectContaining({ name: '张三' }) }),
    )
    expect(onContinueConversation).not.toHaveBeenCalled()
  })

  it('未提供 onSubmitForm 时把字段文本并入继续对话消息', () => {
    const onContinueConversation = vi.fn()
    const result = dispatchOpenUiAction(formEvent(), { onContinueConversation })

    expect(result).toBe('handled')
    expect(onContinueConversation).toHaveBeenCalledWith('提交\n\n- name: 张三\n- plan: pro\n- tags: 导出、API')
  })

  it('无表单值的继续对话保持原有行为', () => {
    const onContinueConversation = vi.fn()
    dispatchOpenUiAction(
      createEvent({ type: 'continue_conversation', humanFriendlyMessage: '普通消息' }),
      { onContinueConversation },
    )

    expect(onContinueConversation).toHaveBeenCalledWith('普通消息')
  })
})
