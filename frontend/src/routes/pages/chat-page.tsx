import { lazy, Suspense, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from '@tanstack/react-router'
import { PanelRightOpen } from 'lucide-react'

import { useAgentRuntime } from '@/features/chat/hooks/use-agent-runtime'
import { useChatModel } from '@/features/chat/hooks/use-chat-model'
import { useChatSession } from '@/features/chat/hooks/use-chat-session'
import { ChatComposer } from '@/features/chat/components/chat-composer'
import { ChatConversation } from '@/features/chat/components/chat-conversation'
import { ChatErrorNotice } from '@/features/chat/components/chat-error-notice'
import { ModelSelector } from '@/features/chat/components/model-selector'
import { QuickPromptPicker } from '@/features/chat/components/quick-prompt-picker'
import { useCasePanel } from '@/features/computer-case/hooks/use-case-panel'
import type { HitlInterrupt } from '@/features/sessions/api'
import { Button } from '@/shared/ui/button'

/**
 * 机箱面板依赖 three 与解码器，体积较大，单独拆包：
 * 窄容器（面板不会展示）或用户隐藏时不下载这部分代码。
 */
const ComputerCasePanel = lazy(() =>
    import('@/features/computer-case/components/computer-case-panel').then((module) => ({
        default: module.ComputerCasePanel,
    })),
)

/** 动作桥已过滤 http/https，这里只负责新窗口打开并阻断来源信息 */
const openExternalUrl = (url: string): void => {
    window.open(url, '_blank', 'noopener,noreferrer')
}

interface ChatPageProps {
    readonly sessionId?: string
    readonly isNewSession: boolean
}

/** `/chat/new`：每次进入都创建新会话，并由 hook 立即替换为规范地址 */
export function ChatNewPage() {
    return <ChatPage isNewSession />
}

/** `/chat/$sessionId`：从 URL 读取会话 ID，刷新、分享与前进后退都走同一入口 */
export function ChatSessionPage() {
    const { sessionId } = useParams({ from: '/_authenticated/chat/$sessionId' })
    return <ChatPage sessionId={sessionId} isNewSession={false} />
}

/**
 * 对话页。
 *
 * URL 是会话权威来源；历史来自 Query 缓存，流式临时消息来自 Agent Runtime，
 * 两者按稳定 ID 合并。`done` 之后的交接由运行时负责，页面只消费结果。
 */
function ChatPage({ sessionId, isNewSession }: ChatPageProps) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const runtimeState = useAgentRuntime()
    // 机箱面板是否展示由「容器可用宽度 + 用户隐藏偏好」共同决定
    const caseContainerRef = useRef<HTMLDivElement | null>(null)
    const casePanel = useCasePanel(caseContainerRef)

    const onCanonicalize = useCallback(
        (threadId: string): void => {
            void navigate({ to: '/chat/$sessionId', params: { sessionId: threadId }, replace: true })
        },
        [navigate],
    )

    // 会话身份、历史合并、落库判定与 done 后的地址回写都在模块内完成
    const session = useChatSession({
        sessionId,
        isNewSession,
        runtime: runtimeState.runtime,
        snapshot: runtimeState.snapshot,
        onCanonicalize,
        untitledLabel: t('chat.untitled'),
    })

    const modelState = useChatModel({
        threadId: session.threadId,
        isPersisted: session.isPersisted,
        sessionModelKey: session.sessionModelKey,
    })
    // 目录加载中先展示禁用态选择器，失败后整体隐藏，避免它反复出现与消失
    const isModelSelectorVisible = modelState.isAvailable || modelState.isLoading

    const runtimeErrorMessage = runtimeState.snapshot.error
        ? runtimeState.snapshot.error.detail || t(runtimeState.snapshot.error.messageKey)
        : ''
    const historyErrorMessage = session.isHistoryLoadError ? t('chat.historyFailed') : ''
    const errorMessage = runtimeErrorMessage || historyErrorMessage

    // 动作按钮与输入框共用同一条提交路径；send 自身的 streaming guard 会拦重复请求
    const sendMessage = runtimeState.send
    const handleSend = useCallback(
        (text: string): void => {
            void sendMessage(text, modelState.modelKey)
        },
        [sendMessage, modelState.modelKey],
    )

    // 引用稳定：onRetry 会穿透到被 memo 的消息项，每次渲染新建函数会让历史消息失效
    const runtimeError = runtimeState.snapshot.error
    const retryRuntime = runtimeState.retry
    const refetchHistory = session.refetchHistory
    const handleRetry = useCallback((): void => {
        if (runtimeError) {
            void retryRuntime(modelState.modelKey)
            return
        }
        refetchHistory()
    }, [runtimeError, retryRuntime, modelState.modelKey, refetchHistory])

    // 重新生成复用最后一条用户提问，服务端负责替换上一条回答
    const handleRegenerate = useCallback((): void => {
        const lastUser = [...session.messages].reverse().find((message) => message.role === 'user')
        if (!lastUser) {
            return
        }
        void runtimeState.regenerate(lastUser.content, modelState.modelKey)
    }, [session.messages, runtimeState, modelState.modelKey])

    // HITL 表单提交走同一条 SSE 流，只是多带 resume；回答文本同时进入用户气泡
    const resumeRuntime = runtimeState.resume
    const handleHitlSubmit = useCallback(
        (message: string, interrupt: HitlInterrupt, answer: Record<string, unknown>): void => {
            void resumeRuntime(message, interrupt, answer, modelState.modelKey)
        },
        [resumeRuntime, modelState.modelKey],
    )

    return (
        <div ref={caseContainerRef} className="relative flex h-full min-h-0">
            <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
                {/* 顶部标题栏已移除，保留仅供读屏与测试识别的页面标题 */}
                <h1 className="sr-only">{session.title}</h1>

                <ChatConversation
                    key={session.threadId}
                    messages={session.messages}
                    threadId={session.threadId}
                    isLoadingHistory={session.isLoadingHistory}
                    isStreaming={runtimeState.snapshot.isStreaming}
                    onRetry={handleRetry}
                    onRegenerate={handleRegenerate}
                    onContinueConversation={handleSend}
                    onOpenUrl={openExternalUrl}
                    onHitlSubmit={handleHitlSubmit}
                />

                <div className="shrink-0 border-t border-border bg-background px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-8 sm:py-4">
                    <div className="mx-auto w-full max-w-[var(--app-content-width)]">
                        {errorMessage ? (
                            <ChatErrorNotice message={errorMessage} onRetry={handleRetry} />
                        ) : null}

                        <ChatComposer
                            isStreaming={runtimeState.snapshot.isStreaming}
                            modelPicker={
                                isModelSelectorVisible ? (
                                    <ModelSelector
                                        models={modelState.models}
                                        modelKey={modelState.modelKey}
                                        isLoading={modelState.isLoading}
                                        disabled={runtimeState.snapshot.isStreaming}
                                        onChange={modelState.setModel}
                                    />
                                ) : null
                            }
                            onSend={handleSend}
                            onStop={runtimeState.stop}
                            quickPicker={(insertPrompt) => (
                                <QuickPromptPicker onConfirm={insertPrompt} />
                            )}
                        />

                        <p className="mt-2 text-center text-[0.6875rem] leading-relaxed text-muted-foreground">
                            {t('chat.disclaimer')}
                        </p>
                    </div>
                </div>
            </section>

            {casePanel.shouldRenderCase ? (
                // 代码分包加载期间先占住面板宽度，避免对话区先铺满再被挤回左侧
                <Suspense
                    fallback={
                        <div
                            className="min-h-0 min-w-[380px] flex-1 border-l border-border bg-canvas"
                            aria-hidden="true"
                        />
                    }
                >
                    <ComputerCasePanel onHide={casePanel.hideCase} />
                </Suspense>
            ) : null}

            {/* 隐藏后保留恢复入口：窄容器下不展示，避免与对话内容争抢空间 */}
            {casePanel.canRestoreCase ? (
                <Button
                    variant="outline"
                    size="icon"
                    className="absolute top-1/2 right-4 z-10 -translate-y-1/2 bg-surface shadow-sm"
                    aria-label={t('chat.casePanel.show')}
                    title={t('chat.casePanel.show')}
                    onClick={casePanel.showCase}
                >
                    <PanelRightOpen className="size-4" />
                </Button>
            ) : null}
        </div>
    )
}
