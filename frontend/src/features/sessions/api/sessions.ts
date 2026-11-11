import type { PageResult } from '@/shared/types/http'

import { parseBuildResult } from './build-result'
import { parseHitlInterrupt } from './hitl-payload'
import { requestAgentJson, requestAgentVoid, type AgentRequestInit } from './request'
import type {
  SessionMessage,
  SessionMessageOrder,
  SessionMessagesResult,
  SessionModelResult,
  SessionRenameResult,
  SessionStateResult,
  SessionSummary,
} from './types'

const JSON_HEADERS: Record<string, string> = { 'Content-Type': 'application/json' }

/** 分页查询当前用户的会话列表；归档列表传 archived=true */
export const listSessions = (
  page = 1,
  size = 20,
  archived = false,
): Promise<PageResult<SessionSummary>> =>
  requestAgentJson(
    '/sessions',
    { method: 'GET' },
    { page, size, archived: archived ? 'true' : 'false' },
  )

/**
 * 历史消息里的 `hitl` 与 `build_result` 都是服务端原始载荷，必须在接口边界解析。
 * 解析失败说明数据不完整，直接省略对应字段，让消息按普通文本展示。
 */
const toSessionMessage = ({
  hitl,
  build_result: rawBuildResult,
  ...message
}: SessionMessage): SessionMessage => {
  const parsedHitl = hitl ? parseHitlInterrupt(hitl) : null
  const parsedBuildResult = rawBuildResult ? parseBuildResult(rawBuildResult) : undefined
  return {
    ...message,
    ...(parsedHitl ? { hitl: parsedHitl } : {}),
    ...(parsedBuildResult ? { buildResult: parsedBuildResult } : {}),
  }
}

/** 查询指定会话的历史消息；会话尚未落库或不存在时服务端返回 404，草稿会话由调用方跳过查询 */
export const getSessionMessages = async (
  threadId: string,
  page = 1,
  size = 20,
  order: SessionMessageOrder = 'asc',
): Promise<SessionMessagesResult> => {
  const result = await requestAgentJson<SessionMessagesResult>(
    `/sessions/${encodeURIComponent(threadId)}/messages`,
    { method: 'GET' },
    { page, size, order },
  )
  return { ...result, list: result.list.map(toSessionMessage) }
}

/** 重命名会话；服务端会去掉首尾空白并校验 1..80 字符 */
export const renameSession = (threadId: string, title: string): Promise<SessionRenameResult> =>
  requestAgentJson(`/sessions/${encodeURIComponent(threadId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
    headers: JSON_HEADERS,
  })

/** 置顶或取消置顶会话；只影响列表排序 */
export const setSessionPinned = (
  threadId: string,
  pinned: boolean,
): Promise<SessionStateResult> =>
  requestAgentJson(`/sessions/${encodeURIComponent(threadId)}/pin`, {
    method: 'PUT',
    body: JSON.stringify({ pinned }),
    headers: JSON_HEADERS,
  })

const requestArchiveSession = (
  threadId: string,
  archived: boolean,
  silent = false,
): Promise<SessionStateResult> =>
  requestAgentJson(`/sessions/${encodeURIComponent(threadId)}/archive`, {
    method: 'PUT',
    body: JSON.stringify({ archived }),
    headers: JSON_HEADERS,
    ...(silent ? { silent: true } : {}),
  })

/** 归档或恢复会话；归档后从默认列表移除 */
export const setSessionArchived = (
  threadId: string,
  archived: boolean,
): Promise<SessionStateResult> => requestArchiveSession(threadId, archived)

const requestDeleteSession = (threadId: string, silent = false): Promise<void> =>
  requestAgentVoid(`/sessions/${encodeURIComponent(threadId)}`, {
    method: 'DELETE',
    ...(silent ? { silent: true } : {}),
  })

/** 删除会话及其消息；成功返回 204，重复删除返回 404 */
export const deleteSession = (threadId: string): Promise<void> =>
  requestDeleteSession(threadId)

/** 批量操作结果：成功与失败分开返回，页面据此给出汇总提示 */
export interface BatchSessionResult {
  succeeded: string[]
  failed: string[]
}

/**
 * 逐个调用单条接口完成批量操作。
 *
 * 服务端没有批量端点，这里用 `allSettled` 并发提交：单条失败不影响其余条目，
 * 批量场景关闭单条自动 toast，由页面统一汇总，避免一次弹出十几个错误提示。
 */
const runSessionBatch = async (
  threadIds: readonly string[],
  action: (threadId: string) => Promise<unknown>,
): Promise<BatchSessionResult> => {
  const results = await Promise.allSettled(threadIds.map((threadId) => action(threadId)))
  const summary: BatchSessionResult = { succeeded: [], failed: [] }
  threadIds.forEach((threadId, index) => {
    if (results[index]?.status === 'fulfilled') {
      summary.succeeded.push(threadId)
    } else {
      summary.failed.push(threadId)
    }
  })
  return summary
}

/** 批量归档（archived=true）或批量恢复（archived=false） */
export const setSessionsArchived = (
  threadIds: readonly string[],
  archived: boolean,
): Promise<BatchSessionResult> =>
  runSessionBatch(threadIds, (threadId) => requestArchiveSession(threadId, archived, true))

/** 批量删除会话及其消息 */
export const deleteSessions = (threadIds: readonly string[]): Promise<BatchSessionResult> =>
  runSessionBatch(threadIds, (threadId) => requestDeleteSession(threadId, true))

/**
 * 设置会话级模型（持久化）。
 *
 * `modelKey` 传 null 表示恢复 Auto。失败由调用方根据错误码提示并回滚界面，
 * 因此这里关闭自动 toast，避免与回滚提示重复。
 */
export const setSessionModel = (
  threadId: string,
  modelKey: string | null,
): Promise<SessionModelResult> =>
  requestAgentJson(`/sessions/${encodeURIComponent(threadId)}/model`, {
    method: 'PUT',
    body: JSON.stringify({ model_key: modelKey }),
    headers: JSON_HEADERS,
    silent: true,
  } satisfies AgentRequestInit)
