import type { AgentRuntimeDeps } from './types'

export interface HandoffOptions {
    readonly threadId: string
    readonly runId: number
    readonly deps: AgentRuntimeDeps
    readonly isCurrentRun: (runId: number) => boolean
    readonly onSuccess: () => void
    readonly onFailure: (error: unknown) => void
}

/**
 * D-09 交接：done 之后才确认落库、重新同步历史、清理临时状态，最后刷新会话列表。
 *
 * 顺序刻意把「清理临时消息」放在「刷新会话列表」之前：
 * 侧栏插入新行与消息区被历史替换若落在同一帧，视觉上会叠加成一次明显抖动。
 *
 * 每一步之后都校验运行序号，避免切换会话后旧交接覆盖新会话；
 * 历史同步失败会保留已生成内容并标记为可重试，绝不提前 invalidate。
 */
export async function handoffTurn(options: HandoffOptions): Promise<void> {
    const { threadId, runId, deps, isCurrentRun, onSuccess, onFailure } = options

    try {
        await deps.confirmPersisted(threadId)
        if (!isCurrentRun(runId)) {
            return
        }

        await deps.invalidateHistory(threadId)
        if (!isCurrentRun(runId)) {
            return
        }

        await deps.syncHistory(threadId)
        if (!isCurrentRun(runId)) {
            return
        }

        onSuccess()

        // 侧栏列表只影响导航，刷新失败不该把已经完成的一轮标成失败
        await deps.invalidateSessions().catch(() => undefined)
    } catch (error) {
        if (isCurrentRun(runId)) {
            onFailure(error)
        }
    }
}
