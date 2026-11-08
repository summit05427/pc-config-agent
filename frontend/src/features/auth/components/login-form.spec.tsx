import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LoginForm } from './login-form'

const createSubmitHandler = () => vi.fn(async (_values: { username: string; password: string }) => {})

describe('LoginForm', () => {
    it('提交空表单时在字段上提示且不调用提交', async () => {
        const onSubmit = createSubmitHandler()
        const user = userEvent.setup()
        render(<LoginForm onSubmit={onSubmit} />)

        await user.click(screen.getByRole('button', { name: '登录' }))

        expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
        expect(screen.getByText('请输入密码')).toBeInTheDocument()
        expect(onSubmit).not.toHaveBeenCalled()
    })

    it('用户名只有空格时按空值拦截', async () => {
        const onSubmit = createSubmitHandler()
        const user = userEvent.setup()
        render(<LoginForm onSubmit={onSubmit} />)

        await user.type(screen.getByLabelText('用户名'), '   ')
        await user.type(screen.getByLabelText('密码'), 'secret')
        await user.click(screen.getByRole('button', { name: '登录' }))

        expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
        expect(onSubmit).not.toHaveBeenCalled()
    })

    it('合法输入提交 trim 后的用户名并在成功后清空凭证', async () => {
        const onSubmit = createSubmitHandler()
        const user = userEvent.setup()
        render(<LoginForm onSubmit={onSubmit} />)

        await user.type(screen.getByLabelText('用户名'), 'alice')
        await user.type(screen.getByLabelText('密码'), 'secret')
        await user.click(screen.getByRole('button', { name: '登录' }))

        await waitFor(() => {
            expect(onSubmit).toHaveBeenCalledWith({ username: 'alice', password: 'secret' })
        })
        await waitFor(() => {
            expect(screen.getByLabelText('用户名')).toHaveValue('')
            expect(screen.getByLabelText('密码')).toHaveValue('')
        })
    })
})
