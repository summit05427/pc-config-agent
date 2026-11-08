import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { RuntimeToolStep } from '../runtime/types'
import { ExecutionTrace } from './execution-trace'

const createStep = (overrides: Partial<RuntimeToolStep> & Pick<RuntimeToolStep, 'id' | 'name'>): RuntimeToolStep => ({
    args: '{"q":"x"}',
    result: '',
    status: 'done',
    startedAt: 0,
    finishedAt: null,
    ...overrides,
})

describe('ExecutionTrace', () => {
    it('展开步骤后展示参数、结果与耗时', async () => {
        const user = userEvent.setup()
        const steps = [
            createStep({
                id: 'step-1',
                name: 'search',
                result: '结果 A',
                startedAt: 1000,
                finishedAt: 1600,
            }),
            createStep({ id: 'step-2', name: 'summarize', status: 'error' }),
        ]

        render(<ExecutionTrace steps={steps} />)

        // 两步属于短轨迹，结束后默认保持展开
        expect(screen.getByText('search')).toBeVisible()
        expect(screen.getByText('失败')).toBeVisible()
        // 轨迹总耗时与步骤耗时都应展示 600ms
        expect(screen.getAllByText('600ms')).toHaveLength(2)

        await user.click(screen.getByRole('button', { name: /search/ }))

        expect(screen.getByText('参数')).toBeVisible()
        expect(screen.getByText('结果 A')).toBeVisible()
    })

    it('长轨迹结束后默认收起，点击标题可展开', async () => {
        const user = userEvent.setup()
        const steps = [
            createStep({ id: 'step-1', name: 'first' }),
            createStep({ id: 'step-2', name: 'second' }),
            createStep({ id: 'step-3', name: 'third' }),
        ]

        render(<ExecutionTrace steps={steps} />)

        expect(screen.queryByText('first')).toBeNull()

        await user.click(screen.getByRole('button', { name: /执行轨迹/ }))

        expect(screen.getByText('first')).toBeVisible()
    })

    it('运行中的步骤展示等待结果提示', async () => {
        const user = userEvent.setup()
        const steps = [createStep({ id: 'step-1', name: 'search', status: 'running' })]

        render(<ExecutionTrace steps={steps} live />)

        expect(screen.getAllByText('执行中').length).toBeGreaterThan(0)

        // 步骤详情默认收起，点击后才展示参数与等待结果的提示
        await user.click(screen.getByRole('button', { name: /search/ }))

        expect(screen.getByText('等待工具返回…')).toBeVisible()
    })
})
