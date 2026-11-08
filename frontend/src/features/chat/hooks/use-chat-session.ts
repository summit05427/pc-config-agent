import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'

import {
    mapHistoryMessages,
    mergeMessages,
} from '@/features/chat/runtime'
import type { RuntimeMessage } from '@/features/chat/runtime/types'
import type { AgentRuntime } from '@/features/chat/runtime/agent-runtime'
import {
    createThreadId,
    isDraftThread,
    markDraftThread,
    resolveSessionThread,
    writeAgentThreadId,
} from '@/features/chat/runtime/agent-thread'
import type { AgentRuntimeSnapshot } from '@/features/chat/runtime/types'
import {
    sessionMessagesQueryOptions,
    sessionsListQueryOptions,
} from '@/features/sessions/api'

/** 侧栏、落库判定与模型选择共用同一页大小，只在这里维护 */
const SESSIONS_PAGE_SIZE = 20
const SHORT_THREAD_ID_LENGTH = 8

/** 去掉历史末尾的一组提问与回答；重新生成时由运行时临时消息接管 */
function dropLastTurn(messages: readonly RuntimeMessage[]): readonly RuntimeMessage[] {
    let end = messages.length
    if (messages[end - 1]?.role === 'assistant') {
        end -= 1
    }
    if (messages[end - 1]?.role === 'user') {
        end -= 1
    }
    return end === messages.length ? messages : messages.slice(0, end)
}

export interface UseChatSessionOptions {
    /** URL 中的会话 ID（`/chat/$sessionId`）；新建入口没有该参数 */
    readonly sessionId: string | undefined
    /** 当前路由是否命中 `/chat/new` */
    readonly isNewSession: boolean
    readonly runtime: AgentRuntime
    /** 运行时快照；`done` 后可能带回服务端真实 thread_id */
    readonly snapshot: AgentRuntimeSnapshot
    /** 需要把权威会话 ID 写成规范 URL 时调用，由页面转成路由 replace */
    readonly onCanonicalize: (threadId: string) => void
    /** 还没有服务端标题且无消息时展示的兜底文案 */
    readonly untitledLabel: string
}

export interface UseChatSessionResult {
    readonly threadId: string
    readonly title: string
    /** 历史与流式消息按稳定 ID 合并后的视图数据 */
    readonly messages: readonly RuntimeMessage[]
    readonly isLoadingHistory: boolean
    /** 会话已可读（历史成功或列表命中）且已离开草稿阶段，模型选择此时才允许持久化 */
    readonly isPersisted: boolean
    /** 历史加载失败；草稿不查询历史，此处的 404 表示会话确实不存在 */
    readonly isHistoryLoadError: boolean
    /** 已落库会话的模型；新会话从列表里查不到时为 null */
    readonly sessionModelKey: string | null
    readonly refetchHistory: () => void
}

/**
 * 会话身份与对账的唯一归属。
 *
 * `sessionId` 是唯一权威：有值就直接采用；`/chat/new` 每次生成新会话；
 * 其它缺失场景才回退 `agent-thread` 镜像。本地生成的 ID 在服务端首轮结束前
 * 并不存在，因此标记为草稿并跳过历史查询；落库确认后由运行时清除标记。
 * 会话列表查询只在这里发起，历史合并、落库判定、标题推导与 `done` 后的
 * URL 回写都由本模块完成，页面只消费结果。
 */
export function useChatSession(options: UseChatSessionOptions): UseChatSessionResult {
    const { sessionId, isNewSession, runtime, snapshot, onCanonicalize, untitledLabel } = options

    // 新建入口必须每次进入都生成新 ID；其余情况按「URL → 镜像 → 新 ID」解析
    const threadId = useMemo(() => {
        if (isNewSession) {
            const nextThreadId = createThreadId()
            markDraftThread(nextThreadId)
            return nextThreadId
        }

        const resolved = resolveSessionThread({ sessionId })
        // 本地生成说明 URL 与兼容镜像都没有可用 ID，同样处于尚未落库的草稿阶段
        if (resolved.source === 'generated') {
            markDraftThread(resolved.threadId)
        }
        return resolved.threadId
    }, [isNewSession, sessionId])

    const appliedThreadRef = useRef<string | null>(null)
    const canonicalizedRef = useRef<string | null>(null)
    const boundThreadRef = useRef<string | null>(null)
    const resolvedThreadId = snapshot.sessionId

    // 会话列表同时用于标题、模型与落库判定，必须先于历史查询求值
    const sessionsQuery = useQuery(sessionsListQueryOptions(1, SESSIONS_PAGE_SIZE))
    const currentSession = sessionsQuery.data?.list.find((item) => item.thread_id === threadId)
    // 草稿：服务端首轮结束前没有记录；一旦出现在列表里说明已经落库
    const isDraft = isDraftThread(threadId) && currentSession === undefined

    // 草稿不查历史：服务端必然 404，骨架屏与错误提示都是假状态
    const historyQuery = useQuery({
        ...sessionMessagesQueryOptions(threadId),
        enabled: !isDraft,
    })
    const isPersisted = !isDraft && (historyQuery.isSuccess || currentSession !== undefined)

    useEffect(() => {
        // 同一个会话重复挂载不重复切换，StrictMode 的二次 effect 因此不会中断在途流
        if (appliedThreadRef.current !== threadId) {
            appliedThreadRef.current = threadId
            runtime.setSession(threadId)
            // 兼容镜像只写不读权威，Vue 回滚期间仍能识别当前会话
            writeAgentThreadId(threadId)
        }

        // /chat/new 与镜像回退都需要把地址替换成规范形式，保证可刷新、可分享
        if (threadId !== sessionId && canonicalizedRef.current !== threadId) {
            canonicalizedRef.current = threadId
            onCanonicalize(threadId)
        }
    }, [threadId, sessionId, runtime, onCanonicalize])

    // 服务端可能在 done 中返回真实 thread_id，需要再写成规范 URL。但首屏提交时
    // 快照仍带着上一个会话的 ID（运行时绑定是同步的，React 重新渲染要等下一帧），
    // 若直接按快照改写地址，两个会话会互相跳转形成死循环，表现为浏览器卡死。
    // 因此先确认运行时已经绑定到当前会话，再信任快照里的 ID。
    useEffect(() => {
        if (snapshot.sessionId === threadId) {
            boundThreadRef.current = threadId
        }
    }, [snapshot.sessionId, threadId])

    useEffect(() => {
        if (boundThreadRef.current !== threadId) {
            return
        }
        if (
            snapshot.status !== 'idle' ||
            resolvedThreadId === null ||
            resolvedThreadId === threadId
        ) {
            return
        }
        onCanonicalize(resolvedThreadId)
    }, [snapshot.status, resolvedThreadId, threadId, onCanonicalize])

    const historyMessages = useMemo(
        () => mapHistoryMessages(threadId, [...(historyQuery.data?.list ?? [])].reverse()),
        [historyQuery.data, threadId],
    )
    // 重新生成期间隐藏历史最后一组「提问 + 回答」，避免旧回答与新流式回答同屏
    const visibleHistory = useMemo(
        () => (snapshot.isRegenerating ? dropLastTurn(historyMessages) : historyMessages),
        [historyMessages, snapshot.isRegenerating],
    )
    const messages = useMemo(
        () => mergeMessages(visibleHistory, snapshot.messages),
        [visibleHistory, snapshot.messages],
    )

    const title =
        currentSession?.title?.trim() ||
        (messages.length > 0
            ? `#${threadId.slice(0, SHORT_THREAD_ID_LENGTH)}`
            : untitledLabel)

    const isHistoryLoadError = !isDraft && historyQuery.isError

    // 引用稳定：重试回调会传给被 memo 的消息项，函数每次重建会让历史消息全部重渲染
    const { refetch: refetchHistoryQuery } = historyQuery
    const refetchHistory = useCallback((): void => {
        void refetchHistoryQuery()
    }, [refetchHistoryQuery])

    return {
        threadId,
        title,
        messages,
        isLoadingHistory: !isDraft && historyQuery.isPending,
        isPersisted,
        isHistoryLoadError,
        sessionModelKey: currentSession?.model_key ?? null,
        refetchHistory,
    }
}
