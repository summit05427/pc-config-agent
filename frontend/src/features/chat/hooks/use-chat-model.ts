import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { modelCatalogQueryOptions, type ModelCatalogItem } from '@/features/models/api'
import { setSessionModel } from '@/features/sessions/api'

interface SelectionState {
    readonly threadId: string
    readonly modelKey: string | null
}

interface PendingModel {
    readonly threadId: string
    readonly modelKey: string
}

export interface UseChatModelOptions {
    readonly threadId: string
    /** 会话已落库才允许直接持久化；新会话等待首轮完成后回写 */
    readonly isPersisted: boolean
    /** 已落库会话的模型，由会话模块从同一份列表查询中取出 */
    readonly sessionModelKey: string | null
}

export interface UseChatModelResult {
    readonly models: readonly ModelCatalogItem[]
    readonly isLoading: boolean
    readonly isAvailable: boolean
    readonly modelKey: string | null
    readonly setModel: (modelKey: string | null) => void
}

/**
 * 会话模型选择。
 *
 * 目录 404 或请求失败时整体隐藏选择器，不影响对话主流程；已有会话的选择取自
 * 会话列表，新会话先记在本地，等首轮完成、历史可读后再持久化，失败则回滚。
 */
export function useChatModel(options: UseChatModelOptions): UseChatModelResult {
    const { t } = useTranslation()
    const catalogQuery = useQuery(modelCatalogQueryOptions)
    const [selection, setSelection] = useState<SelectionState | null>(null)
    const [pending, setPending] = useState<PendingModel | null>(null)
    const attemptedRef = useRef<string | null>(null)

    const modelKey =
        selection?.threadId === options.threadId ? selection.modelKey : options.sessionModelKey

    const commitModel = useCallback(
        async (value: string | null, fallback: string | null): Promise<boolean> => {
            try {
                const result = await setSessionModel(options.threadId, value)
                setSelection({ threadId: options.threadId, modelKey: result.model_key })
                return true
            } catch {
                setSelection({ threadId: options.threadId, modelKey: fallback })
                toast.error(t('chat.model.switchFailed'))
                return false
            }
        },
        [options.threadId, t],
    )

    const setModel = useCallback(
        (nextModelKey: string | null): void => {
            if (nextModelKey === modelKey) {
                return
            }

            const previous = modelKey
            setSelection({ threadId: options.threadId, modelKey: nextModelKey })

            if (!options.isPersisted) {
                setPending(
                    nextModelKey === null
                        ? null
                        : { threadId: options.threadId, modelKey: nextModelKey },
                )
                return
            }

            setPending(null)
            void commitModel(nextModelKey, previous)
        },
        [modelKey, options.threadId, options.isPersisted, commitModel],
    )

    // 首轮完成、会话可读后自动补写新会话的选择；用 ref 保证 StrictMode 只提交一次
    useEffect(() => {
        if (!options.isPersisted || pending === null || pending.threadId !== options.threadId) {
            return
        }

        const attemptKey = `${pending.threadId}:${pending.modelKey}`
        if (attemptedRef.current === attemptKey) {
            return
        }
        attemptedRef.current = attemptKey

        void commitModel(pending.modelKey, modelKey).then((isSaved) => {
            if (isSaved) {
                setPending((current) => (current?.threadId === options.threadId ? null : current))
            }
        })
    }, [options.isPersisted, options.threadId, pending, modelKey, commitModel])

    const models = catalogQuery.data?.list ?? []
    const isLoading = catalogQuery.isPending
    // 目录成功后即使为空也要渲染选择器，由组件展示「请先配置 API Key」而不是整体消失；
    // 只有请求失败（如运行时未启用 404）才隐藏
    const isAvailable = catalogQuery.data !== undefined ? true : isLoading

    return { models, isLoading, isAvailable, modelKey, setModel }
}
