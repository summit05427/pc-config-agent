import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SessionSummary } from '../api/types'
import { SessionList } from './session-list'

const createSession = (index: number): SessionSummary => ({
    thread_id: `thread-${index}`,
    title: `会话 ${index}`,
    model_key: null,
    last_active_at: '2026-10-30T08:00:00Z',
})

describe('SessionList', () => {
    it('没有会话时展示空态文案', () => {
        render(
            <SessionList
                sessions={[]}
                emptyMessageKey="chat.sessions.empty"
                onSelect={vi.fn()}
            />,
        )

        expect(
            screen.getByText('暂无历史会话。开始一次任务后，这里会记录会话。'),
        ).toBeInTheDocument()
    })

    it('请求失败时展示错误并提供重试入口', () => {
        const onRetry = vi.fn()
        render(
            <SessionList
                sessions={[]}
                errorMessage="加载失败"
                emptyMessageKey="chat.sessions.empty"
                onSelect={vi.fn()}
                onRetry={onRetry}
            />,
        )

        expect(screen.getByText('加载失败')).toBeInTheDocument()
        fireEvent.click(screen.getByRole('button', { name: '重试' }))

        expect(onRetry).toHaveBeenCalledTimes(1)
    })

    it('加载中不渲染空态，避免列表高度先塌再撑开', () => {
        render(
            <SessionList
                sessions={[]}
                isLoading
                emptyMessageKey="chat.sessions.empty"
                onSelect={vi.fn()}
            />,
        )

        expect(
            screen.queryByText('暂无历史会话。开始一次任务后，这里会记录会话。'),
        ).not.toBeInTheDocument()
    })

    it('有会话时点击行回传对应 thread_id', () => {
        const onSelect = vi.fn()
        render(
            <SessionList
                sessions={[createSession(1)]}
                emptyMessageKey="chat.sessions.empty"
                onSelect={onSelect}
            />,
        )

        fireEvent.click(screen.getByRole('button', { name: /会话 1/ }))

        expect(onSelect).toHaveBeenCalledWith('thread-1')
    })

    it('侧栏模式提供重命名、置顶、归档与删除菜单', async () => {
        render(
            <QueryClientProvider client={new QueryClient()}>
                <SessionList
                    sessions={[createSession(1)]}
                    emptyMessageKey="chat.sessions.empty"
                    showActions
                    onSelect={vi.fn()}
                />
            </QueryClientProvider>,
        )

        fireEvent.pointerDown(screen.getByRole('button', { name: '更多操作' }), { button: 0 })

        expect(await screen.findByRole('menu')).toBeInTheDocument()
        expect(screen.getByRole('menuitem', { name: /重命名/ })).toBeInTheDocument()
        expect(screen.getByRole('menuitem', { name: /置顶/ })).toBeInTheDocument()
        expect(screen.getByRole('menuitem', { name: /归档/ })).toBeInTheDocument()
        expect(screen.getByRole('menuitem', { name: /删除/ })).toBeInTheDocument()
    })
})
