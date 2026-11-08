# admin 代码地图
用途：只做定位索引，不是规范；编码约束见 .trae/rules-on-demand/40-admin.md，接口契约见 docs/api-contract.md。

## 入口
| 用途 | 路径 |
| --- | --- |
| 启动与 Provider 装配 | src/main.tsx |
| 根路由与错误页 | src/routes/__root.tsx、src/routes/(errors)/*.tsx |
| 文件式路由 | src/routes/_authenticated/<模块>/index.tsx、src/routes/(auth)/sign-in.tsx |
| 生成路由树 | src/routeTree.gen.ts（由插件生成，禁止手改） |
| HTTP 门面 | src/core/http/client.ts、src/core/http/errors.ts |
| 环境变量 | src/lib/env.ts、.env.example |

## 目录职责
| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| src/routes | 文件式路由、鉴权布局、错误页 | 业务实现 |
| src/features | 按模块拆分的 api / components / types | 跨模块状态与直接 axios 调用 |
| src/components/ui | shadcn 基础组件 | 业务逻辑 |
| src/components/layout | 布局、侧边栏、导航数据 | 数据请求 |
| src/core/http | axios 实例、错误归一、401 处理 | 业务规则 |
| src/stores | 认证等全局状态 | 服务端数据镜像 |
| src/lib | env、query-keys、format、cookies、redirect | 组件与 JSX |
| src/context | theme / font / direction / layout / search Provider | 业务接口 |

## 常见改动落点
| 需求 | 落点 |
| --- | --- |
| 新增一个管理页面 | src/routes/_authenticated/<模块>/index.tsx、src/features/<模块>/components/*-page.tsx、src/components/layout/data/sidebar-data.ts |
| 新增一个后端接口调用 | src/features/<模块>/api/*-api.ts、src/lib/query-keys.ts、src/core/http/client.ts |
| 修改登录与令牌刷新 | src/features/auth/sign-in、src/features/auth/api/auth-api.ts、src/stores/auth-store.ts |
| 修改侧边栏导航 | src/components/layout/data/sidebar-data.ts、src/components/layout/app-sidebar.tsx |
| 修改表格分页或空态 | src/components/pagination-bar.tsx、src/components/table-state.tsx |
| 修改错误页 | src/routes/(errors)/*.tsx、src/features/errors/* |
| 修改主题与全局样式 | src/styles、src/context/theme-provider.tsx |

## 测试
测试与被测文件同目录的 *.test.ts(x)，Vitest browser mode 配置见 vite.config.ts；命令 `corepack pnpm --dir admin test`，首次执行 `corepack pnpm --dir admin test:browser:install`。
