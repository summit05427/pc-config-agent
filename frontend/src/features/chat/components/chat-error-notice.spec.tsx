import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ChatErrorNotice } from './chat-error-notice'

describe('ChatErrorNotice', () => {
    it('以 alert 播报错误，重试按钮触发回调', async () => {
        const user = userEvent.setup()
        const onRetry = vi.fn()

        render(<ChatErrorNotice message="模型不可用" onRetry={onRetry} />)

        expect(screen.getByRole('alert')).toHaveTextContent('模型不可用')

        await user.click(screen.getByRole('button', { name: '重试' }))

        expect(onRetry).toHaveBeenCalledTimes(1)
    })
})
