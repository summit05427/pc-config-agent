# 前端生成式 UI（OpenUI）

- 状态：Current（P1-P5 已完成；原验收报告已于 2026-11-05 清理，历史见 Git）
- 跨端契约：[api-contract.md §7.1](../../api-contract.md)

## 1. 定位与边界

生成式 UI 是 Assistant 文本的可选渲染能力，不是新的消息类型，也不替换现有聊天工作区。

- 不新增 SSE 事件，不修改 `token` / `tool_call` / `tool_result` / `done` / `error` 语义。
- 不新增服务端存储，不迁移数据库；UI 状态只存浏览器 `sessionStorage`。
- 不启用 OpenUI 的 `toolProvider`、Query、Mutation，不执行模型生成的任意 JavaScript 或业务 API。
- 开关关闭时整条消息按原有 Markdown 渲染，行为与接入前一致。

阅读顺序：[architecture.md](architecture.md) → 本文 → [ui-design-system.md](ui-design-system.md)；跨端内容约定见 [api-contract.md §7.1](../../api-contract.md)。

## 2. 渲染链路

```text
Assistant content
  → splitUiBlocks（纯函数，按 fence 切分）
      ├─ Markdown 段 → MessageContent → MarkdownContent
      └─ openui 段 → OpenUiBlock（懒加载 Renderer）
                        ├─ useOpenUiState（sessionStorage）
                        ├─ OpenUiErrorBoundary
                        ├─ OPENUI_LIBRARY（32 个已注册组件）
                        └─ Action → onContinueConversation / onOpenUrl
```

| 文件 | 职责 |
| --- | --- |
| `features/generative-ui/index.ts` | 域公共出口；`chat` 只能经此引用 |
| `components/openui-block.tsx` | 单块三态：已闭合渲染 / 流式中占位 / 终态未闭合降级原文 |
| `components/openui-renderer.tsx` | OpenUI Renderer 包装、错误边界、原文兜底 |
| `components/openui-error-boundary.tsx` | 单块异常隔离，避免影响同条消息的 Markdown |
| `hooks/use-openui.ts` | 读取 `VITE_OPENUI_ENABLED`，关闭时整条消息走 Markdown |
| `hooks/use-openui-state.ts` | 表单状态 sessionStorage 持久化 |
| `utils/split-ui-blocks.ts` | fence 切分与规模上限 |
| `library/index.ts` | 唯一组件注册入口；Prompt 由此生成 |
| `library/actions/index.ts` | Action 白名单解析 |

## 3. 消息内容约定

- 只识别 info string 为 `openui` 的 Markdown 围栏（反引号或波浪线），块外内容继续走 Markdown。
- 块内为 openui-lang DSL，首行必须是 `root = ...`。
- 实时消息与历史消息共用同一套切分与渲染逻辑，历史渲染不自动执行 Action。
- 流式期间只渲染已闭合块；未闭合尾块显示「正在生成动态界面…」，消息终态仍未闭合时显示原文与提示。
- 同条消息可混排多个 UI 块与 Markdown。

## 4. 规模上限

`split-ui-blocks.ts` 在切分阶段做硬限制，超限块整段保留为 Markdown 代码块，不进入 Renderer：

| 限制 | 值 | 说明 |
| --- | --- | --- |
| 单条消息 UI 块数 | 8 | Agent 提示词上限 `OPENUI__MAX_BLOCKS` ≤ 10，前端留余量 |
| 单块字符数 | 20000 | 覆盖正常组件树，阻断异常超长输出 |
| 单块行数 | 400 | 同上 |
| 括号嵌套深度 | 32 | 粗略扫描，跳过双引号字符串 |

组件层另有上限：`Table` 超过 10 行前端翻页；表单单次提交最多 50 个标量字段。

## 5. 状态持久化

- 键：`openui-state:v1:<threadId>:<contentHash>`；`contentHash` 为块内容的 FNV-1a 32 位哈希。
- 记录格式：`{ version: 1, values: {...} }`；版本不匹配或 JSON 损坏时删除记录并按无状态渲染。
- 只存表单标量值，不存 Token、消息正文或服务端数据。
- 上限 100 条，超出按 sessionStorage 键顺序淘汰最旧记录。
- 写入失败（配额耗尽、隐私模式）静默降级：表单仍可交互，只是刷新后不恢复。
- 不写 URL、Cookie 与服务端；关闭标签页即丢弃，不跨设备恢复。

## 6. 安全边界

| 项 | 实现 |
| --- | --- |
| 未注册组件 | Renderer 只解析 `OPENUI_LIBRARY` 中已注册名称，其余降级 |
| 未注册 Action | `library/actions/index.ts` 白名单，仅 `continue_conversation` / `open_url` |
| JavaScript | 全链路无 `eval` / `new Function` / `dangerouslySetInnerHTML` |
| 网络与鉴权 | 组件不发请求、不接收 Header 或凭证；`open_url` 仅 http/https |
| XSS | 文本经 React 转义；Markdown 走既有白名单渲染 |
| 权限 | 前端校验只用于交互，真实权限由 Java 服务端判定 |
| 异常隔离 | 单块解析/渲染失败由 ErrorBoundary 兜底，不影响其他段落 |

## 7. 组件库

- 唯一注册入口：`library/index.ts`；新增组件只在此登记，Prompt 由 `OPENUI_LIBRARY.prompt()` 生成。
- 官方 `@openuidev/react-ui` 组件只经单组件子路径引入，由 `library/components/` 适配层注册；禁止包根入口与 `genui-lib` 聚合库。
- 自定义组件与官方适配组件统一用 `defineComponent` 声明 Props Schema、描述与渲染。
- 禁止手改 `agent-service/app/agent/prompts/openui.md`；修改后执行 `corepack pnpm --dir frontend openui:prompt`，CI 用 `openui:prompt:check` 检查漂移。

## 8. 开关与发布

- 前端 `VITE_OPENUI_ENABLED`、Agent `OPENUI__ENABLED`（Compose 由宿主 `OPENUI_ENABLED` 注入），默认均为 `false`。
- 两端没有启动期比对，发布时必须同时置为 `true`：只开前端会拿到纯文本，只开 Agent 会让 UI 内容退化为原始代码块。
- `VITE_*` 在构建期写入静态产物，修改后必须重建镜像，不能只重启容器。
- 安装、构建与 CI 设置 `OPENUI_TELEMETRY_DISABLED=1`。

## 9. 测试与门禁

- 单测覆盖：切分器（混排、未闭合、CRLF、普通代码块、块数/字符/行数/嵌套上限）、状态持久化（重挂载、版本、损坏、配额、淘汰）、单块三态、消息渲染开关、Renderer 未知组件与非法 Props、Action 白名单。
- 质量门禁：`lint:ci`、`type-check`、`test:coverage`（lines ≥ 80%）、`build-only`、`openui:prompt:check`。
- 原验收报告与真实模型记录已于 2026-11-05 清理，历史见 Git；当前行为以本文与代码为准。
