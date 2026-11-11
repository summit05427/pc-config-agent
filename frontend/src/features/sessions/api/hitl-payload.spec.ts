import { describe, expect, it } from 'vitest'

import { parseHitlInterrupt } from './hitl-payload'

const RAW_PAYLOAD = {
  interrupt_id: 'int-1',
  interaction_type: 'confirm_compatibility',
  question: '是否继续查看这份方案？',
  input_schema: {
    fields: [
      {
        name: 'decision',
        label: '是否继续查看方案',
        type: 'radio',
        required: true,
        options: [
          { value: 'continue', label: '继续查看' },
          { value: 'abort', label: '终止本轮' },
        ],
      },
      {
        name: 'budget_yuan',
        label: '预算上限（元）',
        type: 'number',
        required: false,
        min: 1,
      },
    ],
    submit_label: '确认',
  },
  context: { overall_status: 'UNKNOWN' },
  schema_version: '1',
}

describe('parseHitlInterrupt', () => {
  it('把历史/SSE 共用的原始载荷解析为表单结构', () => {
    expect(parseHitlInterrupt(RAW_PAYLOAD)).toEqual({
      interruptId: 'int-1',
      interactionType: 'confirm_compatibility',
      question: '是否继续查看这份方案？',
      submitLabel: '确认',
      context: { overall_status: 'UNKNOWN' },
      schemaVersion: '1',
      fields: [
        {
          name: 'decision',
          label: '是否继续查看方案',
          type: 'radio',
          required: true,
          options: [
            { value: 'continue', label: '继续查看' },
            { value: 'abort', label: '终止本轮' },
          ],
        },
        {
          name: 'budget_yuan',
          label: '预算上限（元）',
          type: 'number',
          required: false,
          min: 1,
        },
      ],
    })
  })

  it('缺 interrupt_id / interaction_type / question 时返回 null', () => {
    expect(parseHitlInterrupt({})).toBeNull()
    expect(parseHitlInterrupt({ ...RAW_PAYLOAD, interrupt_id: '' })).toBeNull()
    expect(parseHitlInterrupt({ ...RAW_PAYLOAD, interaction_type: undefined })).toBeNull()
    expect(parseHitlInterrupt({ ...RAW_PAYLOAD, question: '' })).toBeNull()
    expect(parseHitlInterrupt(null)).toBeNull()
    expect(parseHitlInterrupt('not-a-payload')).toBeNull()
  })

  it('缺 input_schema 时给出空字段与默认提交文案，不抛错', () => {
    const interrupt = parseHitlInterrupt({
      interrupt_id: 'int-2',
      interaction_type: 'clarify_requirements',
      question: '请补充预算',
    })

    expect(interrupt?.fields).toEqual([])
    expect(interrupt?.submitLabel).toBe('提交')
    expect(interrupt?.context).toEqual({})
    expect(interrupt?.schemaVersion).toBeUndefined()
  })

  it('丢弃缺 name/label 的字段与缺 value/label 的选项', () => {
    const interrupt = parseHitlInterrupt({
      ...RAW_PAYLOAD,
      input_schema: {
        fields: [
          { name: '', label: '缺 name', type: 'text', required: false },
          { name: 'ok', label: '正常字段', type: 'select', required: true },
          {
            name: 'choice',
            label: '选项',
            type: 'select',
            required: false,
            options: [{ value: 'a', label: 'A' }, { value: 'b' }, 'bad'],
          },
        ],
      },
    })

    expect(interrupt?.fields.map((field) => field.name)).toEqual(['ok', 'choice'])
    expect(interrupt?.fields[1]?.options).toEqual([{ value: 'a', label: 'A' }])
  })
})
