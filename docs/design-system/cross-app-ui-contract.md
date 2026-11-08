# 跨端 UI 契约（frontend / admin）

- 日期：2026-11-02
- 状态：已确认（Q15 选 A，Q16 新建本文档）
- 适用范围：`frontend/`（用户端）与 `admin/`（管理端）
- 性质：L0 品牌层与 L1 语义层的唯一权威来源（SSOT）；L2 尺度层与 L3 组件层由各应用规则维护

---

## 1. 结论与分层模型

两端**不共享 Token 代码、不共享组件源码**，只共享设计语言与语义定义。

| 层级 | 是否统一 | 内容 | 维护方式 |
|---|---|---|---|
| L0 品牌层 | **必须统一** | 品牌色、Logo、字体、图标库、文案语气 | 本文档 + 两端 theme |
| L1 语义层 | **必须对齐，数值可不同** | `primary / muted / border / destructive / success / warning / info` 的含义与状态映射 | 本文档 + 两端 theme |
| L2 尺度层 | **各自独立** | 圆角、间距、控件高度、字号、阴影强度 | `.trae/rules/10-frontend.md`、`.trae/rules/40-admin.md` |
| L3 组件层 | **各自独立** | 组件源码与 API | `frontend/src/shared/ui`、`admin/src/components/ui` |

决策理由：Q15 选 A（主操作按钮不使用品牌色）、Q16 新建本文档；原始讨论记录已随 2026-11-05 文档清理删除，历史见 Git。

---

## 2. L0 品牌层

### 2.1 品牌色

| Token | 值 | 来源 | 用途 |
|---|---|---|---|
| `--brand` | `#c6613f` | `frontend/src/styles/cds-theme.css` | 品牌主色（徽标、品牌标识） |
| `--brand-hover` | `#cc5a36`（`--cds-clay-hover`） | 同上 | 品牌元素悬停态 |
| `--brand-soft` | `#fbf3ef`（`--cds-clay-light`） | 同上 | 极少量的品牌浅底 |

### 2.2 使用矩阵（Q15-A）

| 位置 | 用户端 frontend | 管理端 admin |
|---|---|---|
| 主操作按钮（primary） | **墨色中性**，非品牌色 | **保持近黑**，不改用品牌色 |
| Logo / 品牌标识 | 允许品牌色 | 允许品牌色 |
| 链接 hover | 允许品牌色强调 | 允许品牌色强调 |
| 选中态 / 当前项 | 允许品牌色或语义 accent | 允许品牌色或语义 accent |
| 焦点环（`--ring`） | 品牌色（`--cds-clay`） | 目标使用品牌色，P1 实施时视觉验收 |
| 运行指示灯 / 图表首色 | 允许品牌色 | 允许品牌色 |
| 大面积背景 / 卡片填充 | 禁止 | 禁止 |
| 表格整行 / 整列着色 | 禁止 | 禁止 |

**依据**：用户端 `frontend/src/styles/main.css` 已明确注明「主操作 = 墨色中性，不是品牌色；陶土橙只承担品牌识别」，Q15-A 与此保持一致，两端 design 哲学不冲突。

> 管理端现状：`admin/src/styles/theme.css` 尚无 `--brand` 变量，需在 P1 补齐（见计划任务 P1-10）。`--primary` 已为近黑，符合契约。

### 2.3 字体

| 项 | 用户端 | 管理端 |
|---|---|---|
| 西文 | Inter（`@fontsource/inter`） | Inter（`index.html` 加载） |
| 中文 | Noto Sans SC（`@fontsource/noto-sans-sc`） | 系统回退 |
| 字体变量 | `--font-sans` | `--font-inter` / `--font-manrope` |

契约要求：**西文主字体统一为 Inter**；中文回退链保持可读；字号刻度属 L2，不在此约束。

### 2.4 图标与文案

- 图标库统一 `lucide-react`，禁止在同一界面混用第二套图标。
- 界面文案统一简体中文；协议字段名、枚举原值、Provider 名称保留英文。
- 术语统一：`用户` / `模型` / `Provider` / `用量` / `成本` / `审计日志` / `模型连接`。

---

## 3. L1 语义层

### 3.1 语义 Token 对照

| 语义 | 用户端现状 | 管理端现状 | 契约要求 |
|---|---|---|---|
| `primary` | 墨色（`--cds-text-primary`） | 近黑 oklch | 保持中性墨色，禁止改为品牌色 |
| `muted` | `--cds-fill-ghost-hover` | oklch 冷灰 | 含义一致（弱背景），数值各自维护 |
| `border` | `--cds-border`（alpha 2） | oklch 冷灰 | 含义一致（1px 分隔），数值各自维护 |
| `destructive` | `#dc2626` / dark `--cds-fill-danger` | `oklch(0.577 0.245 27.325)` | **仅表示错误、失败、破坏性操作** |
| `success` | `#047857` / dark `#34d399` | **未定义** | 管理端待补，用于成功/已结算 |
| `warning` | `--cds-orange-500` / dark `--cds-orange-250` | **未定义** | 管理端待补，用于待处理/注意 |
| `info` | `--cds-blue-450` / dark `#5b9fe3` | **未定义** | 管理端待补，用于中性提示/进行中 |

> 管理端补齐语义色属于 P1 任务；补齐前不得用 `destructive` 替代 `warning` 或 `info`。

### 3.2 业务状态映射（两端共用）

| 业务状态 | 语义 | 允许的视觉 | 禁止 |
|---|---|---|---|
| 启用 / `ACTIVE` | 正常 | `secondary` / `outline` 中性徽标 | 使用 `destructive` |
| 停用 / `DISABLED` / 已吊销 | 非错误 | `secondary` / `outline` + 明确文案 | 使用 `destructive` 红色 |
| 失败 / 错误 / 拒绝 | 异常 | `destructive` | 用中性色淡化 |
| 已结算 / 成功 | 成功 | `success` | 用 `destructive` |
| 待结算 / 待处理 / 未知 | 警告 | `warning` | 用 `success` 或 `destructive` |
| 进行中 / 处理中 | 信息 | `info` / `muted` | 用 `success` |
| 无数据 | 中性 | `muted` + 空态 | 空白无提示 |

---

## 4. L2 尺度层（各自独立，禁止跨端复制）

| 项 | 用户端 | 管理端 |
|---|---|---|
| 侧边栏 | `288px` / rail `56px` | `16rem`（256px）/ 折叠 `3rem`（48px） |
| 顶栏 | `48px`（`--app-titlebar-height`） | `h-16`（64px） |
| 内容宽度 | 对话区 `720px` + gutter `32px` | `max-w-7xl`（1280px）+ `px-4` |
| 控件高度 | `23 / 26 / 32 / 40px` | `32 / 36 / 40px`（`h-8 / h-9 / h-10`） |
| 圆角 | `2 / 4 / 6 / 8 / 12 / 16 / 24px`，气泡 `20px` | `6 / 8 / 10 / 14px`（`--radius: 10px`） |
| 字号刻度 | `13 / 15 / 17 / 20 / 24px` 自定义 | Tailwind 默认（`text-sm` 14px 起） |

规则：

- 禁止把管理端的 `h-9`、`max-w-7xl`、`rounded-xl` 抄进用户端；
- 禁止把用户端的 `20px` 气泡圆角、`720px` 版心抄进管理端；
- 跨端只对齐"同一控件在同一层级下的相对大小关系"，不复制具体数值。

---

## 5. L3 组件层

### 5.1 组件归属

| 类别 | 数量 | 清单 |
|---|---|---|
| 两端都有（实现独立） | 20 | `alert-dialog` `avatar` `badge` `button` `card` `checkbox` `dialog` `dropdown-menu` `input` `label` `popover` `scroll-area` `select` `separator` `sheet` `skeleton` `switch` `tabs` `textarea` `tooltip` |
| 仅管理端 | 8 | `alert` `collapsible` `command` `form` `radio-group` `sidebar` `sonner` `table` |
| 仅用户端 | 1 | `brand-mark` |

### 5.2 约定

- 同名组件必须保持**语义一致**（`Button` 的 variant 含义、`Badge` 的状态语义、`Input` 的尺寸档位），但 API 与实现各自维护。
- 禁止 `frontend` 与 `admin` 互相 import 源码；禁止抽共享包。
- 文件命名 kebab-case，组件导出 PascalCase；一个文件一个组件（`brand-mark` 等业务组件除外，按各端规则）。
- 管理端 `components/ui/**` 为 shadcn 生成件，业务定制写在业务组件内，不直接改生成件语义。

### 5.3 空态 / 加载 / 错误

两端都必须提供三态，且语义一致：

| 状态 | 要求 |
|---|---|
| Loading | 骨架或 `Loader2` 旋转；按钮内 loading 必须禁用 |
| Empty | 图标 + 一句说明 + 可选操作；禁止只有一行灰字 |
| Error | 说明 + 重试入口；禁止直接暴露堆栈或英文报错 |

---

## 6. 变更流程

1. **改 L0 品牌色或 L1 语义**：必须同时更新 `frontend/src/styles/main.css`、`admin/src/styles/theme.css` 与本文档，并在 PR 描述中列出两端影响页面。
2. **改 L2 尺度**：只改单端 theme，不需要跨端评审，但要说明是否影响既有截图验收。
3. **新增组件**：先判断属于 L0–L3 哪一层；同名组件在两端出现时必须核对语义。
4. **新增状态色**：只能使用 L1 表格中的语义名，禁止新增 `--color-xxx` 之外的临时色。

### 评审清单

- [ ] 品牌色只出现在 2.2 允许的位置，未做大面积填充。
- [ ] `primary` 仍为中性墨色。
- [ ] 停用/禁用未使用 `destructive`。
- [ ] 新增文案为简体中文，术语与 2.4 一致。
- [ ] 未跨应用 import，未新增共享包。
- [ ] 三态（Loading / Empty / Error）完整。

---

## 7. 与其他规则的关系

- 本文件不覆盖 `.trae/rules/00-monorepo-common.md`、`10-frontend.md`、`40-admin.md`；冲突时以更严格的规则为准。
- 事实优先级：代码 > 可执行配置 > 本文件 > 口头约定。
- 本文档只约束"跨端一致性"，不替代各端组件与页面的具体实现规范。
