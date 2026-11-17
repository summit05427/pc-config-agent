import { render, screen } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: true,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import { COMPONENT_FIXTURES } from '../testing/component-fixtures'
import { OpenUiRenderer } from './openui-renderer'

beforeAll(async () => {
  // 预热懒加载运行时，避免首个用例把 OpenUI 的首次转换时间算进断言超时
  await import('./openui-renderer-runtime')
})

/**
 * 逐组件渲染契约。
 *
 * 与 `openui-renderer.spec.tsx` 的分工：那边验证整块渲染链路（流式、错误隔离、Action），
 * 这里保证注册表里的每个组件都至少被真实渲染并断言过一次。
 */
describe('组件库渲染契约', () => {
  beforeEach(() => {
    envMock.openUiEnabled = true
  })

  it.each(COMPONENT_FIXTURES)('$name 能独立渲染', async ({ dsl, expectText, expectRole }) => {
    render(<OpenUiRenderer response={dsl} />)

    const [firstText, ...restText] = expectText
    if (firstText) {
      expect(await screen.findByText(firstText)).toBeInTheDocument()
      for (const text of restText) {
        expect(screen.getByText(text)).toBeInTheDocument()
      }
    } else if (expectRole) {
      // 无可见文本的组件（Image）用角色等待渲染完成
      expect(await screen.findAllByRole(expectRole.role)).toHaveLength(expectRole.count ?? 1)
    }

    if (expectRole && firstText) {
      expect(screen.getAllByRole(expectRole.role)).toHaveLength(expectRole.count ?? 1)
    }
  })

  it('Table 的 image 列渲染缩略图，非 http 地址渲染占位', async () => {
    const dsl = [
      'root = Table([',
      'Col("图片", ["https://cdn.example.com/cpu.jpg", "javascript:alert(1)"], "image"),',
      'Col("型号", ["CPU A", "CPU B"])',
      '])',
    ].join('\n')

    render(<OpenUiRenderer response={dsl} />)

    // 先等表格数据渲染完成，再检查图片单元格
    expect(await screen.findByText('CPU A')).toBeInTheDocument()
    const image = document.querySelector('img')
    expect(image).toHaveAttribute('src', 'https://cdn.example.com/cpu.jpg')
    // 非法协议不能进入 img src，只能显示占位
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
