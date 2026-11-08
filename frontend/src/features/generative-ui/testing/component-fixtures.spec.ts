import { describe, expect, it } from 'vitest'

import { OPENUI_LIBRARY } from '../library'
import { COMPONENT_FIXTURES } from './component-fixtures'

/**
 * 覆盖率守卫。
 *
 * 这是「新增组件必须同时补测试」的唯一强制点：只要注册表里有、夹具里没有，
 * 或者夹具引用了不存在的组件名，本文件就会失败，避免组件库悄悄膨胀而无人验证。
 */
describe('component fixtures', () => {
  const registeredNames = Object.keys(OPENUI_LIBRARY.components).sort()

  it('夹具覆盖全部已注册组件', () => {
    const coveredNames = [
      ...new Set(COMPONENT_FIXTURES.flatMap((fixture) => fixture.covers)),
    ].sort()

    expect(coveredNames).toEqual(registeredNames)
  })

  it('夹具引用的组件名都已注册', () => {
    const unknownNames = COMPONENT_FIXTURES.flatMap((fixture) => fixture.covers).filter(
      (name) => !registeredNames.includes(name),
    )

    expect(unknownNames).toEqual([])
  })

  it('夹具名称唯一且都提供了断言', () => {
    const names = COMPONENT_FIXTURES.map((fixture) => fixture.name)

    expect(new Set(names).size).toBe(names.length)
    expect(
      COMPONENT_FIXTURES.filter(
        (fixture) => fixture.expectText.length === 0 && fixture.expectRole === undefined,
      ),
    ).toEqual([])
  })
})
