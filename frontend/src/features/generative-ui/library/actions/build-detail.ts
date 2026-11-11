import { defineAction } from '@openuidev/react-lang'
import { z } from 'zod'

/** 详情面板动作名：DSL 中写作 `@OpenBuildDetail()`，必须与白名单字符串完全一致 */
export const OPEN_BUILD_DETAIL_ACTION = 'OpenBuildDetail'

/**
 * 打开配置详情面板。
 *
 * 这是纯前端动作：不请求后端、不追加对话，宿主用当前消息里的 buildResult 渲染固定面板。
 * 之所以不让模型用 `@ToAssistant` 代替，是为了避免"点详情"产生一次新的模型调用与计费。
 */
export const OpenBuildDetailAction = defineAction({
  name: OPEN_BUILD_DETAIL_ACTION,
  description: '打开当前推荐配置的详情面板：兼容性校验、八件硬件参数与 CPU/GPU 跑分',
  params: z.object({}),
})
