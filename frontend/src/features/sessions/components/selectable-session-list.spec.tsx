import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SessionSummary } from '../api/types'
import { SelectableSessionList } from './selectable-session-list'

const createSession = (index: number, isPinned = false): SessionSummary => ({
  thread_id: `thread-${index}`,
  title: `会话 ${index}`,
  model_key: null,
  last_active_at: '2026-10-30T08:00:00Z',
  is_pinned: isPinned,
  is_archived: false,
})

const renderList = (overrides: {
  sessions?: readonly SessionSummary[]
  selectedIds?: ReadonlySet<string>
  onToggle?: (threadId: string) => void
  onToggleAll?: () => void
  onOpen?: (threadId: string) => void
}) => {
  const onToggle = overrides.onToggle ?? vi.fn()
  const onToggleAll = overrides.onToggleAll ?? vi.fn()
  const onOpen = overrides.onOpen ?? vi.fn()

  render(
    <SelectableSessionList
      sessions={overrides.sessions ?? [createSession(1), createSession(2)]}
      emptyMessageKey="settings.chats.listEmpty"
      selectedIds={overrides.selectedIds ?? new Set<string>()}
      onToggle={onToggle}
      onToggleAll={onToggleAll}
      onOpen={onOpen}
    />,
  )

  return { onToggle, onToggleAll, onOpen }
}

describe('SelectableSessionList', () => {
  it('勾选行与全选分别回调', () => {
    const { onToggle, onToggleAll } = renderList({})

    fireEvent.click(screen.getByRole('checkbox', { name: '选择会话 会话 1' }))
    expect(onToggle).toHaveBeenCalledWith('thread-1')

    fireEvent.click(screen.getByRole('checkbox', { name: '全选当前列表' }))
    expect(onToggleAll).toHaveBeenCalledTimes(1)
  })

  it('展示已选数量，点击标题进入会话', () => {
    const { onOpen } = renderList({ selectedIds: new Set(['thread-1']) })

    expect(screen.getByText('已选择 1 项')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /会话 2/ }))
    expect(onOpen).toHaveBeenCalledWith('thread-2')
  })

  it('没有会话时展示空态且禁用全选', () => {
    renderList({ sessions: [] })

    expect(screen.getByText('还没有可管理的会话。')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '全选当前列表' })).toBeDisabled()
  })
})
