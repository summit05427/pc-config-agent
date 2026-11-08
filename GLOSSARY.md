# Agent 平台前端

本仓库的前端术语。用户端与管理端是两个独立应用；术语以用户端为准，管理端接入后再补充。

## 文档入口导航

| 文档 | 内容 |
| --- | --- |
| [`README.md`](./README.md) | 项目定位、目录结构、启动命令与文档总入口 |
| [`docs/README.md`](./docs/README.md) | 文档地图与信息状态标签 |
| [`docs/services/frontend/architecture.md`](./docs/services/frontend/architecture.md) | 前端目录、路由、数据流、状态与已知偏差 |
| [`docs/services/frontend/development-guide.md`](./docs/services/frontend/development-guide.md) | 前端命令、命名与提交门禁 |
| [`docs/services/frontend/ui-design-system.md`](./docs/services/frontend/ui-design-system.md) | UI Token 与组件规范 |
| [`docs/services/frontend/generative-ui.md`](./docs/services/frontend/generative-ui.md) | OpenUI 渲染链路、状态持久化与安全边界 |
| [`.trae/rules-on-demand/10-frontend.md`](./.trae/rules-on-demand/10-frontend.md) | 前端编码硬约束 |

术语与代码不一致时，以代码为准并修正本文件。

## 语言

**会话（Session / Thread）**：
一次连续的对话上下文，服务端以 `thread_id` 标识，前端从 `thread_id` 派生路由参数 `sessionId`。
_避免_: 使用「对话」「chat」来指代该实体

**回合（Turn）**：
一次「用户提问 → 助手回复」的完整执行，包含流式 token、工具调用与终态。
_避免_: 把单个 token 事件或单次工具调用称为一轮对话

**活动回合（Active Turn）**：
当前正在执行、尚未到达 `done` / `error` / 取消状态的回合。同一会话同一时刻最多一个。

**Agent Runtime（对话运行时）**：
独立于 UI 组件树的执行层，负责流连接、事件分发、中断控制与回合状态迁移。
_避免_: 「聊天 store」「SSE hook」

**服务端状态（Server State）**：
由 Java 或 Agent 拥有的数据（用户资料、偏好、会话列表、历史消息、模型目录），前端只读缓存。

**客户端状态（Client State）**：
由浏览器交互产生、服务端不持有的数据（主题、语言、侧边栏、当前选中会话）。

**设计基线（CDS）**：
现有的 `--cds-*` Token 体系与控件规范，是迁移时的视觉事实源，不是可重新设计的起点。

**设备会话（Device Session）**：
用户在设置页可见的登录设备记录，属于 Java 认证域，与会话（Session / Thread）不是同一概念。

**迁移基线（Migration Baseline）**：
被替换前的 Vue 实现，存在于 Tag 与 Worktree 中，用于回滚与功能对等比对。

## Generative UI

**生成式 UI（Generative UI）**：
由 Agent 按约定语言描述、前端用已注册组件渲染的动态界面。它不是模型生成可执行代码，也不是任意 HTML。
_避免_: 把模型生成的文本直接称为「生成页面」

**OpenUI Lang**：
Agent 用来描述组件树的声明式语言。模型只能使用已注册组件与已声明参数。
_避免_: 「UI 代码」「模板」

**UI 块（Generative UI Block）**：
Assistant 消息中一段以 `openui` 围栏标记的 OpenUI Lang 内容；块外内容仍是普通 Markdown。
_避免_: 把整条 Assistant 消息称为一个 UI 块

**UI 块切分器（UI Block Splitter）**：
把 Assistant 内容切分为 Markdown 段与 UI 块的纯函数组件。实时消息与历史消息共用同一实现。
_避免_: 「解析器插件」「渲染中间件」

**组件库（Component Library）**：
前端注册、模型可见的组件集合，按 Core / Display / Interactive / Domain 分级。
_避免_: 把 `shared/ui` 全部组件默认暴露给模型

**官方 UI 原语（Official UI Primitive）**：
`@openuidev/react-ui` 通过单组件子路径导出的展示层组件（如 Tabs、Table），只负责渲染，不携带 OpenUI Lang 契约。
_避免_: 把官方聚合库 `openuiLibrary` 当作原语逐个引用

**组件适配层（Component Adapter）**：
在 `library/components/` 中用 `defineComponent` 把官方 UI 原语包装成本项目组件契约的薄封装，名称、Props 与描述由本项目维护。
_避免_: 复制官方实现、直接修改 `node_modules`

**组件注册表（Component Registry）**：
`library/index.ts` 中注册的组件集合，是 React 渲染与 Agent 提示词的唯一事实来源；提示词由 `OPENUI_LIBRARY.prompt()` 生成。
_避免_: 另建 `manifest.ts` 或人工维护第二份组件定义

**提示词产物（Prompt Artifact）**：
由组件注册表构建生成、供 Agent 读取的提示词文件。它是产物，不是第二个事实来源。
_避免_: 人工维护的第二份组件定义

**UI 状态（UI State）**：
UI 块内部的表单值与交互状态，只属于当前浏览器会话，不属于服务端业务数据。
_避免_: 与「服务端状态」「客户端状态」混用

**UI 状态键（UI State Key）**：
表单状态在 `sessionStorage` 中的索引，格式 `openui-state:v1:<threadId>:<contentHash>`。使用块内容哈希而非消息 ID，保证实时消息被历史消息替换后仍能恢复。
_避免_: 用会变化的消息 ID 或流式中的半截内容做键

**规模上限（UI Block Limits）**：
切分阶段对块数、字符数、行数与括号嵌套深度的硬限制。超限块整段降级为 Markdown 原文，不进入 Renderer。
_避免_: 只依赖提示词约束模型输出

**动作（Action）**：
UI 块中由用户手势触发、经前端白名单校验后才执行的交互。它不等同于模型可任意调用的函数。
_避免_: 「工具调用」「命令」

## Agent 模板

**Agent Profile（Agent 配置档）**：
描述一个 Agent 的身份与运行参数的配置文件，包含提示词、工具集、模型参数与上下文预算。它是模板的一等扩展点，由请求级 `agent_id` 选择。
_避免_: 「机器人配置」「人格文件」

**扩展点（Extension Point）**：
接入方在不修改核心代码的前提下增加能力的固定入口，如工具注册表、Provider 适配器、Agent Profile、钩子。
_避免_: 「插件」「回调」（后者仅指钩子的具体实现）

**机制 / 内容（Mechanism / Content）**：
模板只提供可复用的机制（注册表、治理、接口、验证框架），具体业务内容（工具实现、评测用例、知识库）由接入方提供。
_避免_: 把业务实现称为「模板能力」

**模板成熟度（Template Maturity）**：
按可运行、可配置、可扩展、可裁剪、可治理五个等级衡量模板，而不是按内置功能数量。
_避免_: 用「功能清单」评价模板

**Solo 模式（Solo Mode）**：
只启动 `agent-service`、使用内存存储与开发令牌的最小运行形态，用于五分钟内体验模板；不包含额度、BYOK 与会话级模型选择。
_避免_: 「本地模式」「单机版」（含义过宽）

**工具注册表（Tool Registry）**：
工具声明与治理参数的唯一登记处；未登记的工具不会被模型看到，同名登记视为配置错误。
_避免_: 「工具列表」「工具集合」

**Provider 适配器（Provider Adapter）**：
把某个模型提供商的客户端装配方式封装成可注册的适配器；Agent 只依赖适配器接口，不直接依赖具体 SDK。
_避免_: 「模型驱动」「客户端」

**契约快照（Contract Snapshot）**：
由代码生成、纳入版本控制的接口契约副本（如 OpenAPI JSON），用于在评审中显式看到契约变化。
_避免_: 手工维护的接口文档副本
