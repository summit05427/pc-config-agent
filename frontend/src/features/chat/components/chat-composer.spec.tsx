import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ChatComposer } from './chat-composer'

describe('ChatComposer', () => {
    it('Enter 发送并清空输入，空的输入框不能提交', async () => {
        const user = userEvent.setup()
        const onSend = vi.fn()

        render(<ChatComposer onSend={onSend} onStop={vi.fn()} />)

        const textarea = screen.getByLabelText('消息输入框')
        const sendButton = screen.getByRole('button', { name: '发送' })
        expect(sendButton).toBeDisabled()
        expect(textarea).toHaveAttribute('maxlength', '4000')

        await user.type(textarea, '你好')
        expect(sendButton).toBeEnabled()

        await user.keyboard('{Enter}')

        expect(onSend).toHaveBeenCalledWith('你好')
        expect(textarea).toHaveValue('')
    })

    it('Shift+Enter 只换行，不触发发送', async () => {
        const user = userEvent.setup()
        const onSend = vi.fn()

        render(<ChatComposer onSend={onSend} onStop={vi.fn()} />)

        const textarea = screen.getByLabelText('消息输入框')
        await user.type(textarea, '第一行{Shift>}{Enter}{/Shift}第二行')

        expect(onSend).not.toHaveBeenCalled()
        expect(textarea).toHaveValue('第一行\n第二行')
    })

    it('生成中展示停止按钮并禁用发送', async () => {
        const user = userEvent.setup()
        const onStop = vi.fn()

        render(<ChatComposer isStreaming onSend={vi.fn()} onStop={onStop} />)

        expect(screen.queryByRole('button', { name: '发送' })).toBeNull()
        const stopButton = screen.getByRole('button', { name: '停止生成' })

        await user.click(stopButton)

        expect(onStop).toHaveBeenCalledTimes(1)
    })

    it('快捷选择生成的描述写入输入框但不自动发送', async () => {
        const user = userEvent.setup()
        const onSend = vi.fn()

        render(
            <ChatComposer
                onSend={onSend}
                onStop={vi.fn()}
                quickPicker={(insertPrompt) => (
                    <button type="button" onClick={() => insertPrompt('预算：8000 元')}>
                        生成描述
                    </button>
                )}
            />,
        )

        await user.click(screen.getByRole('button', { name: '生成描述' }))

        expect(screen.getByLabelText('消息输入框')).toHaveValue('预算：8000 元')
        expect(onSend).not.toHaveBeenCalled()
    })

    it('快捷选择追加在已有输入之后，不覆盖用户已写内容', async () => {
        const user = userEvent.setup()

        render(
            <ChatComposer
                onSend={vi.fn()}
                onStop={vi.fn()}
                quickPicker={(insertPrompt) => (
                    <button type="button" onClick={() => insertPrompt('主要用途：游戏')}>
                        生成描述
                    </button>
                )}
            />,
        )

        await user.type(screen.getByLabelText('消息输入框'), '帮我配台电脑')
        await user.click(screen.getByRole('button', { name: '生成描述' }))

        expect(screen.getByLabelText('消息输入框')).toHaveValue(
            '帮我配台电脑\n主要用途：游戏',
        )
    })
})
