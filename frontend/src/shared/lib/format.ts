import dayjs from 'dayjs'

type DateInput = string | number | Date | null | undefined

/**
 * 绝对时间：设备会话、用量记录等需要精确到秒的场景统一使用该格式。
 * 与 Vue 基线保持一致，保证迁移前后同一份数据展示差异只来自语言。
 */
export function formatDateTime(value: DateInput): string {
    if (value === null || value === undefined || value === '') {
        return ''
    }

    const instance = dayjs(value)
    return instance.isValid() ? instance.format('YYYY-MM-DD HH:mm:ss') : ''
}

/**
 * 耗时读数：小于 1 秒按毫秒展示，避免出现「0.0s」这种丢失精度的读数。
 * 执行轨迹的单步与总耗时共用同一套格式，保证同一块区域内的读数一致。
 */
export function formatElapsedDuration(elapsed: number): string {
    if (elapsed <= 0) {
        return ''
    }

    return elapsed < 1000 ? `${elapsed}ms` : `${(elapsed / 1000).toFixed(1)}s`
}

/**
 * 工具步骤耗时：历史消息没有真实耗时（startedAt 为 0），此时不展示。
 */
export function formatDuration(startedAt: number, finishedAt: number | null): string {
    if (!startedAt || !finishedAt || finishedAt < startedAt) {
        return ''
    }

    return formatElapsedDuration(finishedAt - startedAt)
}

/**
 * 消息时间：当天只显示时刻，当年补月日，跨年补完整日期，始终保留时分。
 * 与会话行的相对时间不同，回复末尾需要可读的准确时间。
 */
export function formatMessageTimestamp(value: DateInput): string {
    if (value === null || value === undefined || value === '') {
        return ''
    }

    const instance = dayjs(value)
    if (!instance.isValid()) {
        return ''
    }

    const now = dayjs()
    if (instance.isSame(now, 'day')) {
        return instance.format('HH:mm')
    }
    if (instance.isSame(now, 'year')) {
        return instance.format('MM-DD HH:mm')
    }

    return instance.format('YYYY-MM-DD HH:mm')
}

/**
 * 会话行尾的时间：当天显示时刻，当年显示月日，跨年才显示完整日期。
 * 与 Vue 基线保持一致，避免会话列表在迁移前后出现两种时间表达。
 */
export function formatSessionTimestamp(value: DateInput): string {
    if (value === null || value === undefined || value === '') {
        return ''
    }

    const instance = dayjs(value)
    if (!instance.isValid()) {
        return ''
    }

    const now = dayjs()
    if (instance.isSame(now, 'day')) {
        return instance.format('HH:mm')
    }
    if (instance.isSame(now, 'year')) {
        return instance.format('MM-DD')
    }

    return instance.format('YYYY-MM-DD')
}
