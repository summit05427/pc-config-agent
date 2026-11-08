# frontend 代码地图
用途：只做定位索引，不是规范；编码约束见 .trae/rules-on-demand/10-frontend.md，接口契约见 docs/api-contract.md。

## 入口
| 用途 | 路径 |
| --- | --- |
| 启动与挂载 | src/main.tsx |
| 应用装配（Provider / 布局） | src/app/app.tsx、src/app/query-client.ts |
| 路由树 | src/routes/router.tsx |
| 路径常量与路由守卫 | src/routes/paths.ts、src/routes/guards.ts |
| 环境变量读取 | src/shared/lib/env.ts、.env.example |

## 目录职责
| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| src/app | Provider、layouts、全局 stores、QueryClient | 业务域组件与请求逻辑 |
| src/routes | 路由树、守卫、pages 页面组装 | 具体业务实现 |
| src/features | 按域拆分的 api / model / components / hooks / runtime | 跨域私有实现（跨域只经 api/index.ts） |
| src/core/http | HTTP、SSE、Token 门面与错误归一 | 业务领域逻辑 |
| src/shared | ui 封装、lib 纯函数、query-keys、types | 业务数据与请求 |
| src/i18n、src/locales、src/styles、src/constants | 文案、设计 Token、常量 | 业务逻辑与运行时状态 |

## 常见改动落点
| 需求 | 落点 |
| --- | --- |
| 新增一个前端页面 | src/routes/pages/<x>-page.tsx、src/routes/router.tsx、src/routes/paths.ts |
| 新增一个后端接口调用 | src/features/<域>/api/*.ts、src/shared/lib/query-keys.ts、src/core/http |
| 新增或修改 SSE 事件消费 | src/features/sessions/api/stream-chat.ts、src/features/chat/runtime/* |
| 修改聊天消息渲染 | src/features/chat/components/message-item.tsx、message-content.tsx |
| 新增生成式 UI 组件 | src/features/generative-ui/library/components、library/index.ts |
| 新增全局状态字段 | src/app/stores/app-store.ts、src/shared/lib/app-storage.ts |
| 调整文案或语言 | src/i18n/index.ts、src/locales |
| 修改登录与鉴权交互 | src/features/auth/api、src/features/auth/model/auth-session.ts、src/core/http/token.ts |

## 测试
测试与被测文件同目录的 *.spec.ts(x)，配置见 vitest.config.ts 与 src/test/setup.ts，E2E 在 e2e/；命令 `corepack pnpm --dir frontend test:coverage`、`corepack pnpm --dir frontend e2e:critical`。
