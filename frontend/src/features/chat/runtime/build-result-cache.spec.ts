import { describe, expect, it } from 'vitest'

import type { BuildResult, SessionMessage } from '@/features/sessions/api'

import { forgetBuildResult, readBuildResult, rememberBuildResult } from './build-result-cache'
import { mapHistoryMessages } from './history-messages'

const THREAD_ID = 'thread-cache'

const createBuild = (overrides: Partial<BuildResult> = {}): BuildResult => ({
    buildId: 'b-1',
    components: [],
    totalPriceFen: 100,
    budgetMaxFen: null,
    budgetStatus: 'NO_BUDGET',
    overallCompatibility: 'PASS',
    compatibility: [],
    reasonSummary: '',
    offerDataStatus: null,
    verifiedOfferCount: null,
    demoOfferCount: null,
    ...overrides,
})

describe('build-result-cache', () => {
    it('同一会话同一正文命中缓存', () => {
        rememberBuildResult(THREAD_ID, '回答正文', createBuild())

        expect(readBuildResult(THREAD_ID, '回答正文')?.buildId).toBe('b-1')
        forgetBuildResult(THREAD_ID)
    })

    it('正文不一致或会话不同时不命中，避免错挂到其他回答', () => {
        rememberBuildResult(THREAD_ID, '回答正文', createBuild())

        expect(readBuildResult(THREAD_ID, '另一条回答')).toBeUndefined()
        expect(readBuildResult('other-thread', '回答正文')).toBeUndefined()
        forgetBuildResult(THREAD_ID)
    })

    it('forget 后不再命中', () => {
        rememberBuildResult(THREAD_ID, '回答正文', createBuild())
        forgetBuildResult(THREAD_ID)

        expect(readBuildResult(THREAD_ID, '回答正文')).toBeUndefined()
    })

    it('超过容量时淘汰最早会话', () => {
        for (let index = 0; index < 21; index += 1) {
            rememberBuildResult(`cap-${index}`, '正文', createBuild())
        }

        expect(readBuildResult('cap-0', '正文')).toBeUndefined()
        expect(readBuildResult('cap-20', '正文')?.buildId).toBe('b-1')

        for (let index = 0; index < 21; index += 1) {
            forgetBuildResult(`cap-${index}`)
        }
    })

    it('历史映射把缓存结果挂回同一条助手消息', () => {
        rememberBuildResult(THREAD_ID, '回答正文', createBuild())
        const history: SessionMessage[] = [{ role: 'assistant', content: '回答正文' }]

        const messages = mapHistoryMessages(THREAD_ID, history)

        expect(messages[0]?.buildResult?.buildId).toBe('b-1')
        forgetBuildResult(THREAD_ID)
    })
})
