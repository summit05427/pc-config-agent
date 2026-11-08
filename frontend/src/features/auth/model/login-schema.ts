import { z } from 'zod'

export interface LoginFormValues {
    username: string
    password: string
}

type Translate = (key: string) => string

/**
 * 登录表单 Schema。
 *
 * 错误文案在创建时注入当前语言的 t()，切换语言后重新创建即可；
 * 用户名校验先 trim，避免只输入空格被当作有效值。
 */
export function createLoginSchema(t: Translate) {
    return z.object({
        username: z.string().trim().min(1, { message: t('login.usernameRequired') }),
        password: z.string().min(1, { message: t('login.passwordRequired') }),
    })
}
