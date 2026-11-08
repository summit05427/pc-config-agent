import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm, type FieldErrors } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'

import { ApiError } from '@/core/http'
import { createLoginSchema, type LoginFormValues } from '@/features/auth/model/login-schema'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

export interface LoginFormProps {
    /** 由页面负责调用认证 store 与跳转；抛出的错误在这里转为内联提示 */
    onSubmit: (values: LoginFormValues) => Promise<void>
}

/**
 * 登录表单。
 *
 * 校验失败时聚焦第一个非法字段，提交中禁用全部输入与按钮，成功后才清空凭证；
 * 失败保留已填内容，用户不必重新输入密码。
 */
export function LoginForm({ onSubmit }: LoginFormProps) {
    const { t } = useTranslation()
    const [showPassword, setShowPassword] = useState(false)
    const [submitError, setSubmitError] = useState('')
    const {
        register,
        handleSubmit,
        reset,
        setFocus,
        formState: { errors, isSubmitting },
    } = useForm<LoginFormValues>({
        resolver: zodResolver(createLoginSchema(t)),
        defaultValues: { username: '', password: '' },
    })

    const focusFirstInvalidField = (invalidErrors: FieldErrors<LoginFormValues>): void => {
        const firstKey = (Object.keys(invalidErrors) as (keyof LoginFormValues)[])[0]
        if (firstKey) {
            setFocus(firstKey)
        }
    }

    const submit = async (values: LoginFormValues): Promise<void> => {
        setSubmitError('')
        try {
            await onSubmit(values)
            // 登录成功后密码不再留在内存与表单状态里
            reset()
        } catch (error) {
            // 登录失败不触发全局跳转与刷新，统一由表单内联提示，便于直接修改重试
            setSubmitError(error instanceof ApiError ? error.message : t('login.failed'))
        }
    }

    return (
        <form
            className="mt-7 space-y-5"
            noValidate
            onSubmit={(event) => void handleSubmit(submit, focusFirstInvalidField)(event)}
        >
            <div className="space-y-2">
                <Label htmlFor="login-username" className="text-xs">
                    {t('login.username')}
                </Label>
                <Input
                    id="login-username"
                    autoComplete="username"
                    autoFocus
                    placeholder={t('login.usernamePlaceholder')}
                    disabled={isSubmitting}
                    aria-invalid={Boolean(errors.username)}
                    aria-describedby={errors.username ? 'login-username-error' : undefined}
                    {...register('username')}
                />
                {errors.username?.message ? (
                    <p id="login-username-error" className="text-xs text-destructive">
                        {errors.username.message}
                    </p>
                ) : null}
            </div>

            <div className="space-y-2">
                <Label htmlFor="login-password" className="text-xs">
                    {t('login.password')}
                </Label>
                <div className="relative">
                    <Input
                        id="login-password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="current-password"
                        placeholder={t('login.passwordPlaceholder')}
                        disabled={isSubmitting}
                        className="pr-10"
                        aria-invalid={Boolean(errors.password)}
                        aria-describedby={errors.password ? 'login-password-error' : undefined}
                        {...register('password')}
                    />
                    <button
                        type="button"
                        className="absolute right-1 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-[var(--cds-radius-btn-xs)] text-muted-foreground hover:text-foreground"
                        aria-label={showPassword ? t('login.hidePassword') : t('login.showPassword')}
                        aria-pressed={showPassword}
                        onClick={() => setShowPassword((current) => !current)}
                    >
                        {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                </div>
                {errors.password?.message ? (
                    <p id="login-password-error" className="text-xs text-destructive">
                        {errors.password.message}
                    </p>
                ) : null}
            </div>

            {submitError ? (
                <div
                    role="alert"
                    className="flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
                >
                    <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                    <p className="leading-relaxed">{submitError}</p>
                </div>
            ) : null}

            <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : null}
                {isSubmitting ? t('login.submitting') : t('login.submit')}
            </Button>
        </form>
    )
}
