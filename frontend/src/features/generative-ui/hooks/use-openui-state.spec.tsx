import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useOpenUiState } from './use-openui-state'

const STORAGE_PREFIX = 'openui-state:v1:'

const findStateStorageKey = (): string => {
  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index)
    if (key?.startsWith(STORAGE_PREFIX)) {
      return key
    }
  }
  throw new Error('未找到状态存储键')
}

interface StateProbeProps {
  readonly threadId: string
  readonly content: string
}

function StateProbe({ threadId, content }: StateProbeProps): ReactNode {
  const { initialState, handleStateUpdate } = useOpenUiState(threadId, content)

  return (
    <div>
      <span data-testid="state">{JSON.stringify(initialState ?? null)}</span>
      <button onClick={() => handleStateUpdate({ name: '张三' })}>保存</button>
    </div>
  )
}

describe('useOpenUiState', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('同会话同内容重挂载后恢复已保存状态', async () => {
    const props = { threadId: 'state-thread-a', content: 'root = Stack([Text("表单")])' }
    const first = render(<StateProbe {...props} />)

    expect(screen.getByTestId('state')).toHaveTextContent('null')

    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    first.unmount()

    render(<StateProbe {...props} />)

    expect(screen.getByTestId('state')).toHaveTextContent('张三')
  })

  it('不同块内容不会串用同一会话的状态', async () => {
    render(<StateProbe threadId="state-thread-b" content="block-a" />)

    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    const second = render(<StateProbe threadId="state-thread-b" content="block-b" />)

    expect(within(second.container).getByTestId('state')).toHaveTextContent('null')
  })

  it('不同会话相同内容不会互相恢复', async () => {
    render(<StateProbe threadId="state-thread-c" content="shared-block" />)

    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    const second = render(<StateProbe threadId="state-thread-d" content="shared-block" />)

    expect(within(second.container).getByTestId('state')).toHaveTextContent('null')
  })

  it('版本不匹配的记录被丢弃', async () => {
    const props = { threadId: 'state-thread-version', content: 'versioned-block' }
    render(<StateProbe {...props} />)
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    const storageKey = findStateStorageKey()
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify({ version: 0, values: { name: '李四' } }),
    )

    const second = render(<StateProbe {...props} />)

    expect(within(second.container).getByTestId('state')).toHaveTextContent('null')
    expect(window.sessionStorage.getItem(storageKey)).toBeNull()
  })

  it('损坏的存储内容不影响渲染', async () => {
    const props = { threadId: 'state-thread-broken', content: 'broken-block' }
    render(<StateProbe {...props} />)
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    const storageKey = findStateStorageKey()
    window.sessionStorage.setItem(storageKey, '{')

    const second = render(<StateProbe {...props} />)

    expect(within(second.container).getByTestId('state')).toHaveTextContent('null')
  })

  it('sessionStorage 写入失败时交互不受影响', async () => {
    const setItemSpy = vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })

    render(<StateProbe threadId="state-thread-quota" content="quota-block" />)

    await expect(
      userEvent.click(screen.getByRole('button', { name: '保存' })),
    ).resolves.toBeUndefined()
    expect(screen.getByTestId('state')).toHaveTextContent('null')

    setItemSpy.mockRestore()
  })

  it('状态条目超过上限时淘汰最旧记录', async () => {
    for (let index = 0; index < 100; index += 1) {
      window.sessionStorage.setItem(
        `${STORAGE_PREFIX}seed-thread:seed-${index}`,
        JSON.stringify({ version: 1, values: { index } }),
      )
    }

    render(<StateProbe threadId="state-thread-prune" content="prune-block" />)
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    let stateKeyCount = 0
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const key = window.sessionStorage.key(index)
      if (key?.startsWith(STORAGE_PREFIX)) {
        stateKeyCount += 1
      }
    }

    expect(stateKeyCount).toBe(100)
  })
})
