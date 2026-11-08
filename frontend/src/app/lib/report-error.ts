import { env } from '@/shared/lib/env'

export type GlobalErrorSource = 'error' | 'unhandledrejection'

export type GlobalErrorReportHandler = (error: unknown, source: GlobalErrorSource) => void

const NOOP_REPORT_HANDLER: GlobalErrorReportHandler = () => undefined

let reportHandler: GlobalErrorReportHandler = NOOP_REPORT_HANDLER
let isInstalled = false

/** 生产上报由发布方注入；默认空实现，避免在未接入监控时把异常写进控制台日志 */
export const setGlobalErrorReportHandler = (handler: GlobalErrorReportHandler): void => {
    reportHandler = handler
}

const handleGlobalError = (error: unknown, source: GlobalErrorSource): void => {
    if (env.appEnv === 'development') {
        console.error(`[global ${source}]`, error)
        return
    }
    reportHandler(error, source)
}

/**
 * 注册全局异常兜底。
 *
 * 模块级标记挡住 HMR 重复执行，保证同一份 window 只挂一组监听；
 * 渲染期异常交给路由 errorComponent，这里只兜住事件回调与未处理的 Promise。
 */
export function installGlobalErrorHandlers(): void {
    if (isInstalled) {
        return
    }
    isInstalled = true

    window.addEventListener('error', (event) => {
        handleGlobalError(event.error ?? event.message, 'error')
    })

    window.addEventListener('unhandledrejection', (event) => {
        handleGlobalError(event.reason, 'unhandledrejection')
    })
}
