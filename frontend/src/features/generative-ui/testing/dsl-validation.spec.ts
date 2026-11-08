import { createParser } from '@openuidev/react-lang'
import { describe, expect, it } from 'vitest'

import { OPENUI_LIBRARY } from '../library'
import { COMPONENT_FIXTURES } from './component-fixtures'
import { SCENARIO_FIXTURES } from './scenario-fixtures'

/**
 * OpenUI Lang 静态校验。
 *
 * 渲染测试只能证明「当前这些 DSL 能渲染」，一旦夹具写错（组件名拼错、
 * 参数缺失、变量不可达），渲染器会静默丢弃节点，测试仍然可能通过。
 * 这里直接用组件库 Schema 解析，把解析器记录的 errors / unresolved / orphaned
 * 当成硬门槛，确保夹具本身是合法程序。
 */
const parser = createParser(OPENUI_LIBRARY.toJSONSchema(), 'Stack')

const ALL_FIXTURES: readonly { name: string; dsl: string }[] = [
  ...COMPONENT_FIXTURES,
  ...SCENARIO_FIXTURES,
]

describe('OpenUI Lang 静态校验', () => {
  it.each(ALL_FIXTURES)('$name 解析后没有错误或悬空引用', ({ dsl }) => {
    const result = parser.parse(dsl)

    expect(result.root?.typeName).toBe('Stack')
    expect(result.meta.incomplete).toBe(false)
    expect(result.meta.errors).toEqual([])
    expect(result.meta.unresolved).toEqual([])
    expect(result.meta.orphaned).toEqual([])
  })

  it('能检出未注册组件，防止校验形同虚设', () => {
    const result = parser.parse('root = Stack([bad])\nbad = Unknown("未注册组件")')

    expect(result.meta.errors.map((error) => error.code)).toContain('unknown-component')
  })

  it('能检出缺失必填参数', () => {
    const result = parser.parse('root = Stack([empty])\nempty = Table()')

    expect(result.meta.errors.map((error) => error.code)).toContain('missing-required')
  })
})
