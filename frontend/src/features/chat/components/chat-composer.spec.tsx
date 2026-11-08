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
})
