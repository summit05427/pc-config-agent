# UI 设计系统与界面规范（前端）

> 本文件是 `frontend/**` 的 UI 唯一参考依据（SSOT）。
> 新增页面、组件或调整视觉前，先查本文件；实现与本文冲突时，以代码为事实先登记差异，再在文档治理中决定修正哪一方。
> 修改 Token 或布局尺寸时，必须同步更新本文件。

## 权威文档导航

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](../../README.md) | 文档地图与状态标签（总入口） |
| [docs/architecture-overview.md](../../architecture-overview.md) | 三端职责、拓扑、信任边界 |
| [docs/api-contract.md](../../api-contract.md) | 对外 HTTP / SSE / 内部接口契约 |
| [docs/services/frontend/architecture.md](./architecture.md) | 前端目录、路由、数据流、状态、环境变量（实现事实） |
| [docs/services/frontend/development-guide.md](./development-guide.md) | 命令、命名、新增页面/接口、SSE 扩展、提交门禁 |
| [.trae/rules-on-demand/10-frontend.md](../../../.trae/rules-on-demand/10-frontend.md) | 前端编码硬约束（含控件高度与圆角阶梯） |

Token 事实源是 `frontend/src/styles/cds-theme.css`（`--cds-*`），语义映射在 `frontend/src/styles/main.css`；本文表格与这两个文件不一致时，以文件为准并修正本文。

- ## 1. 权威来源与落地链路

  ### 1.1 来源优先级与采信规则

  本规范服务于 `frontend/**`，是项目 UI 的唯一执行依据（SSOT）。外部资料负责提供经核实的设计依据，项目本地规范负责将这些依据固化为可执行的工程约束。

  外部来源按以下优先级采信：

  | 优先级 | 来源                                | 采信范围                                                     | 使用规则                                                     |
  | ------ | ----------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | P0     | Anthropic / Claude 官方公开资料     | 官方明确公开的设计系统原则、组件规范、交互行为及无障碍要求   | 优先采信，但仅限官方资料明确支持的内容；不得将观察所得或推测所得的参数称为官方标准 |
  | P1     | `Caho1/open-claude-ui`              | Claude 桌面端 UI、Token、组件尺寸、交互行为及桌面布局的开源实现参考 | 官方资料未明确规定时，优先参考；必须核实具体文件、实现内容和版本 |
  | P2     | `catyiqian/claude-design-style`     | 排版、留白、视觉层次及 Claude 风格的设计实践                 | 用于补充视觉规范，不覆盖已核实的 P0 规则或本项目已确认的设计决策 |
  | P3     | `rinn7e/claude-desktop-theme-tuner` | Claude 桌面端主题变量、浅色/深色模式及表面颜色映射           | 用于主题机制和颜色变量的补充参考，不作为完整布局或组件规范的权威来源 |

  官方来源入口：

  - Anthropic 官方网站：https://www.anthropic.com/
  - Claude 官方产品网站：https://claude.com/
  - Claude 官方帮助中心：https://support.claude.com/

  开源参考仓库：

  - P1：https://github.com/Caho1/open-claude-ui
  - P2：https://github.com/catyiqian/claude-design-style
  - P3：https://github.com/rinn7e/claude-desktop-theme-tuner

## 2. 设计原则

1. **暖调纸面**：底层画布是带暖意的灰白，不追求纯白或冷灰；层级靠表面明度差 + 发丝边框，而不是重阴影。
2. **墨色主操作**：主按钮使用墨色（`--primary` 映射到文本主色），品牌陶土橙只承担识别（徽标、焦点环、运行指示、图表首色）。深色模式自动反相，无需第二套主色。
3. **单侧边栏**：桌面端只有一条 288px 侧边栏，导航、会话、工具都收在同一条栏内；不允许再叠加第二层会话面板。
4. **固定尺度**：界面字号、控件高度、圆角都是固定刻度，不做随视口流动的缩放。
5. **安静的状态表达**：加载用呼吸骨架、流式用光标，不做装饰性动画；动效 150–200ms（主题切换的 300ms 圆形扩散属有意例外），尊重 `prefers-reduced-motion`。
6. **先测量再优化**：布局与性能调整必须有截图、DOM 尺寸或性能数据支撑。

### 2.1 关键决策与取舍

| 决策                        | 放弃的方案                         | 原因                                                               |
| --------------------------- | ---------------------------------- | ------------------------------------------------------------------ |
| 全量采用 CDS 暖灰 + 陶土橙  | Tailwind 默认 slate/indigo 调色板  | 两套色彩来源会让“品牌色”失去唯一解释；P0 是唯一权威                |
| 主按钮用墨色                | 主按钮用陶土橙                     | Claude 的主 CTA 是墨色实心；橙色只做识别，避免每个页面都是橙色按钮 |
| `destructive` 用 `#dc2626`  | P0 的 `#ef4444`                    | 浅色下 `#ef4444` 正文对比不足，取同色阶 600 满足 AA，不引入新色相  |
| 桌面只保留一条 288px 侧边栏 | 全局侧边栏 + 页面内 272px 会话面板 | 双栏占掉 560px，正文被压缩；会话属于导航，应与全局导航同层         |
| 移动端只保留一个抽屉        | 导航抽屉 + 会话抽屉并存            | 两个抽屉语义重叠、入口混淆；合并后与桌面信息结构一致               |
| 固定控件高度 23/26/32/40    | 每个组件各写 `h-8`、`h-9`、`py-2`  | 高度漂移是界面“不整齐”的主因；阶梯化后跨页面自然对齐               |
| 使用 `100dvh`               | 固定 `100vh`                       | 移动端地址栏收放会裁切输入区或露出空白                             |
| 欢迎页挂在 `/`              | 空白占位或重定向到登录             | 根路径是产品的第一印象，必须是可用的任务入口                       |
| 会话地址即状态              | 只把会话存在 store 里              | 刷新、深链、前进后退都需要可恢复的 URL                             |

## 3. 颜色与表面

### 3.1 表面阶梯

| 语义变量                 | Token                   | 浅色      | 深色      | 使用位置                     |
| ------------------------ | ----------------------- | --------- | --------- | ---------------------------- |
| `--canvas` / `--sidebar` | `--cds-surface-0`       | `#f9f9f7` | `#0b0b0b` | 侧边栏、抽屉、底层画布       |
| `--background`           | `--cds-surface-1`       | `#fcfcfb` | `#151515` | 主工作区、页面背景           |
| `--surface` / `--card`   | `--cds-surface-2`       | `#ffffff` | `#1a1a19` | 消息卡片、面板、输入容器     |
| `--surface-raised`       | `--cds-surface-3`       | `#ffffff` | `#20201f` | 输入框、高层浮层、悬停抬升面 |
| `--popover`              | `--cds-surface-popover` | `#ffffff` | `#2c2c2a` | 下拉菜单、Popover            |

规则：

- 同一屏最多出现 3 级表面；相邻表面必须同时有色差或边框，避免“白上白”。
- 卡片/面板用 `--surface`，不要用纯白 `#fff` 硬编码。
- 侧边栏永远用 `--sidebar`，与主区形成整块色差。

### 3.2 文本与边框

| 语义变量                                    | 浅色                | 深色                  | 用途                       |
| ------------------------------------------- | ------------------- | --------------------- | -------------------------- |
| `--foreground`                              | `#151515`           | `#f5f5f5`             | 正文、标题、主按钮底色     |
| `--muted-foreground`                        | `#525252`           | `#a3a3a3`             | 辅助说明、时间、占位符     |
| `--cds-text-muted`                          | `#8a8a8a`           | `#666666`             | 极弱信息（仅装饰性标签）   |
| `--border`                                  | `hsla(0,0%,8%,.10)` | `hsla(0,0%,100%,.09)` | 常规发丝线、分隔、输入边框 |
| `--border-strong`（`border-border-strong`） | `hsla(0,0%,8%,.20)` | `hsla(0,0%,100%,.18)` | 悬停/聚焦边框、强调分隔    |

### 3.3 品牌与状态

| 语义                | 值                                            | 说明                                     |
| ------------------- | --------------------------------------------- | ---------------------------------------- |
| 陶土橙 `--cds-clay` | `#d97757`                                     | 徽标、焦点环、运行指示灯、图表 1         |
| 陶土悬停            | 浅 `#cc5a36` / 深 `#e08264`                   | 品牌元素的 hover                         |
| 陶土浅底            | `#fbf3ef`                                     | 极浅品牌底（浅色模式）                   |
| `--primary`         | `--cds-text-primary`                          | 墨色主按钮，深浅自动反相                 |
| `--secondary`       | `--cds-bg-user-message`                       | 用户气泡底色（中性 alpha-1）             |
| `--accent`          | `--cds-fill-ghost-selected`                   | 选中态（导航、会话行）                   |
| `--destructive`     | 浅 `#dc2626` / 深 `--cds-fill-danger`         | P0 的 `#ef4444` 对比不足，改用同色阶 600 |
| `--success`         | 浅 `#047857` / 深 `#34d399`                   | 成功、复制完成                           |
| `--warning`         | 浅 `--cds-orange-500` / 深 `--cds-orange-250` | 警告                                     |
| `--info`            | 浅 `--cds-blue-450` / 深 `#5b9fe3`            | 信息                                     |

禁止引入第三组色相；状态色只允许在上述色阶内取档位。

### 3.4 圆角

| Token                   | 值     | 用途                                            |
| ----------------------- | ------ | ----------------------------------------------- |
| `--radius-xs`           | 2px    | 标签内角、极小元素                              |
| `--radius-sm`           | 4px    | 行内代码、骨架                                  |
| `--radius-md`           | 6px    | `xs/sm` 按钮（`--cds-radius-btn-xs`）           |
| `--radius-lg`           | 8px    | 默认按钮（`--cds-radius-btn-md`）、输入框、卡片 |
| `--cds-panel-radius`    | 10px   | 示例卡片、会话空状态、提示面板                  |
| `--radius-xl`           | 12px   | 消息气泡、代码块（`--cds-radius-code`）         |
| `--cds-radius-dialog`   | 16px   | 对话框                                          |
| `--cds-radius-composer` | 20px   | 输入终端                                        |
| `--radius-3xl`          | 24px   | 大容器                                          |
| `--cds-radius-pill`     | 9999px | 头像、圆形图标按钮                              |

消息气泡特殊规则：整体 12px，右下角（用户侧）收为 4px（`--cds-message-bubble-radius-meeting`），形成“贴着发送者”的方向感。

### 3.5 阴影

| Token                         | 用途                                                   |
| ----------------------------- | ------------------------------------------------------ |
| `--cds-shadow-sm`             | 卡片轻微抬升                                           |
| `--cds-shadow-md`             | 下拉、浮层                                             |
| `--cds-shadow-lg`             | 对话框                                                 |
| `--cds-shadow-composer`       | 输入终端默认：`0 4px 20px rgba(0,0,0,.035)` + 1px 内环 |
| `--cds-shadow-composer-hover` | 悬停：扩散加大 + `--border-strong` 内环                |
| `--cds-shadow-composer-focus` | 聚焦：再叠加 1px 外环                                  |

阴影只用于“离开页面平面”的元素；普通卡片优先用边框，不用阴影。

## 4. 几何与布局

| 变量                       | 值                 | 说明                           |
| -------------------------- | ------------------ | ------------------------------ |
| `--app-sidebar-width`      | 288px（18rem）     | 桌面展开侧边栏                 |
| `--app-sidebar-rail-width` | 56px（3.5rem）     | 折叠侧边栏                     |
| `--app-titlebar-height`    | 48px（3rem）       | 侧边栏品牌行                   |
| `--app-content-width`      | 720px（45rem）     | 对话页阅读宽度                 |
| `--app-gutter-x`           | 32px（2rem）       | 桌面页面沟槽；移动端 16px      |
| 移动抽屉宽度               | `min(288px, 85vw)` | 保证窄屏仍露出遮罩可点击       |
| 高度基准                   | `100dvh`           | `@supports` 降级到 `100vh`     |

布局结构（`DefaultLayout.tsx`）：

```text
┌───────────┬──────────────────────────────┐
│ Sidebar   │ 内容 max-width 720px          │
│ 288/56px  │ 居中，沟槽 16/32px            │
│ 品牌行 48 │                              │
│ 新建对话  │ 窄屏左上角悬浮导航入口        │
│ 导航      │ （仅 <768px，不占布局高度）   │
│ 会话列表  │                              │
│ 工具区    │                              │
└───────────┴──────────────────────────────┘
```

断点与行为：

| 视口            | 侧边栏                                             | 导航入口              | 会话入口           |
| --------------- | -------------------------------------------------- | --------------------- | ------------------ |
| `<768px`        | 隐藏                                               | 左上角悬浮按钮 → 抽屉 | 同一抽屉内的会话区 |
| `≥768px`        | 常驻，可拖拽 220–`min(420px, 40vw)`，可折叠到 56px | 侧边栏品牌位 + 新建对话 | 侧边栏「最近」会话列表 |
| 欢迎页 / 登录页 | 无侧边栏                                           | 页内顶栏              | 页内入口           |

移动端安全区：底部输入区必须保留 `env(safe-area-inset-bottom)`；页面根使用 `dvh`，避免地址栏收起时裁切。

### 4.1 可拖拽侧边栏

桌面端（`≥768px`）侧边栏宽度由用户控制，参数集中在 `frontend/src/app/layouts/lib/sidebar.ts` 的 `SIDEBAR_LAYOUT`（已核对：`defaultWidth` 288、`minWidth` 220、`maxWidth` 420、`maxViewportRatio` 0.4、`collapseThreshold` 200、`railWidth` 56、`resizerHitWidth` 6、`keyboardStep` 16、`keyboardLargeStep` 48），组件不得另写魔法值。

| 参数           | 值                        | 说明                                                        |
| -------------- | ------------------------- | ----------------------------------------------------------- |
| 默认展开宽度   | 288px                     | 与 `--app-sidebar-width` 一致；首次使用与非法持久化值的回退 |
| 展开最小宽度   | 220px                     | 正常展开态的宽度下限，保证导航与会话行可读                  |
| 展开最大宽度   | `min(420px, floor(40vw))` | 1440→420、1280→420、1024→409、768→307                       |
| 折叠阈值       | 200px                     | 拖动中达到 `≤200` 立即折叠；释放时 `201–219` 吸附回 220     |
| 折叠 rail 宽度 | 56px                      | 折叠后仅保留图标栏                                          |
| 拖拽命中区     | 6px                       | 覆盖侧边栏右缘，视觉只保留 1px 发丝线                       |
| 键盘步长       | 16px / Shift 48px         | ArrowLeft / ArrowRight 调整宽度                             |

交互规则：

- 分隔条使用 Pointer Events + `setPointerCapture`，指针移出窗口、失焦、`pointercancel`、组件卸载都必须结束拖动并清理 `select-none` / `cursor-col-resize`。
- 拖动期间只写侧边栏 DOM 宽度（`style.width`），不更新响应式状态；`requestAnimationFrame` 合并高频 move。
- 松开与阈值两条结算路径都复用同一套 `finish`：释放指针捕获、移除全局监听、清理 body 类、取消 rAF，再提交宽度。
- 拖动时侧边栏不启用 `transition`；折叠/展开使用 200ms 宽度过渡，`prefers-reduced-motion: reduce` 下不产生可见动画。
- 拖动中宽度达到 `≤200px` 时立即结束拖动并折叠，不需要等待鼠标释放；拖动下限即阈值，不会渲染出更窄的侧栏。
- 释放时按提交规则结算：`≥220` 保留、`201–219` 吸附到 220；拖动中已折叠时释放不再改变状态；宽度始终夹取到视口上限。
- 拖动结束后的合成 `click` 一律忽略，直到下一次按下才恢复“点击边界展开”，避免折叠后同一次释放立刻把侧栏重新展开。
- 折叠后焦点自动移到品牌行内的展开按钮（折叠态下品牌图标在悬浮 / 键盘聚焦时切换为展开图标，点击即展开）；展开恢复 `app-state.sidebarWidth` 记录的上次有效宽度。
- 折叠态下同一条 6px 边界改为 `role="button"` 的点击展开入口（`cursor: pointer`），单击或 Enter/Space 展开，不启动拖拽；展开态才恢复 separator 语义与 `col-resize`。
- 侧边栏所有导航文本统一 `truncate`（nowrap + ellipsis），图标 `shrink-0`；New Chat 与「最近」标题行在任何拖动宽度下都必须保持单行。
- 侧边栏导航文字统一 14px（`text-nav`），行高独立取 36px（`--app-sidebar-row-height`）；「最近」与设置分组标题、会话时间戳取 `text-xs`（12px），禁止再写 11px 任意字号。
- 键盘调整与鼠标共用同一提交规则：向左调整导致 `next < 220` 时提交折叠，Shift 使用 48px 大步长。
- 分隔条语义：`role="separator"`、`aria-orientation="vertical"`、`aria-valuenow/min/max`、`aria-valuetext`，聚焦时显示 2px 陶土橙描边。
- 持久化字段：`app-state` 中的 `sidebarWidth`、`isSidebarCollapsed` 与 `showAccountMenuIcon`，只存 UI 偏好，不存会话内容或凭据；非法值回退默认宽度，视口变窄只夹取实际宽度、不覆盖偏好。`showAccountMenuIcon` 控制侧边栏底部账户入口右侧的菜单图标（`Ellipsis`），关闭时仅隐藏图标，账户入口仍可点击，开关位于设置页「外观」分区。

## 5. 字体与排版

字体栈：

```text
sans:    Anthropic Sans → Inter → Noto Sans SC → system-ui → PingFang SC → Microsoft YaHei
heading: 同 sans
serif:   Anthropic Serif → Noto Serif SC → Songti SC → SimSun → ui-serif → Georgia
mono:    Anthropic Mono → ui-monospace → SFMono-Regular → JetBrains Mono → Menlo → Consolas
```

分工规则：

| 字体 | 负责范围 |
| --- | --- |
| Anthropic Sans | 全部 UI 控件与操作型文字：导航、按钮、表单、表格、区块小标题、表单标题 |
| Anthropic Serif | 展示型文案与长文：AI 正文 `.prose-agent`、登录页大标题与副标题、空会话标题、页面级标题（404、错误页、受保护占位页） |
| Anthropic Mono | 代码块、行内代码、执行轨迹、模型 ID、耗时等需等宽对齐的标识 |

判定规则：**用户需要“扫读并操作”的用 Sans，需要“阅读并感受”的用 Serif。** 展示型标题统一用 `text-display` 刻度（`--text-display` / `--text-display--line-height` / `--text-display--letter-spacing` / `--text-display--font-weight`），字号大时 `opsz` 自动推到 Display 档，笔画变细，靠近官方观感。

加载方式：

```text
Anthropic 三族：frontend/src/assets/fonts/*.woff2，由 src/styles/fonts.css 声明
Inter / Noto Sans SC / Noto Serif SC：@fontsource 本地打包，不依赖外部 CDN
```

- 三个 Anthropic 文件都是可变字体，单文件覆盖 `wght 300–800`，`@font-face` 必须声明字重区间；`Sans`/`Serif` 另带 `opsz 16–48` 光学尺寸轴，由 `font-optical-sizing: auto` 自动插值。
- 三者只含拉丁字符，没有 CJK 也没有 Italic：中文由 Noto Sans SC（界面）/ Noto Serif SC（正文）接管，斜体为浏览器合成，正文不依赖真斜体。
- Inter 保留为 Anthropic Sans 的兜底，仅当出现希腊、西里尔、箭头、数学符号等缺失字形时才会命中。
- 字体为 Anthropic 品牌字体（版权 Anthropic PBC），对外分发前需确认授权。

字号刻度（固定值，不随视口缩放）：

| Token       | 字号 | 行高 | 典型用途                     |
| ----------- | ---- | ---- | ---------------------------- |
| `text-xs`   | 12px | 1.5  | 时间、辅助标签、计数         |
| `text-sm`   | 13px | 1.55 | 次要正文、按钮小号、表单说明 |
| `text-nav`  | 14px | 1.5  | 侧边栏导航、会话标题、账户行 |
| `text-base` | 15px | 1.65 | 正文、消息、输入框           |
| `text-lg`   | 17px | 1.55 | 区块标题                     |
| `text-xl`   | 20px | 1.4  | 页面标题（移动）             |
| `text-2xl`  | 24px | 1.3  | 页面标题                     |
| `text-3xl`  | 30px | 1.2  | 大标题备用                   |
| `text-display` | 32px | 1.12 | 衬线展示型标题（登录页主标题、页面级标题） |

补充规则：

- `body` 基准 15px / 1.6，`font-kerning: normal`；不再叠加 Inter 的 `cv11`/`ss01` 特性。
- 展示型标题统一用 `font-serif text-display`（32px / 1.12 / -0.02em / 400），不再手写字号与字距；`display` 只给衬线大标题，UI 标题仍取 `text-xl`、`text-lg` 等阶梯，禁止再写任意字号。
- 展示型标题不加粗：衬线大字号本身已足够醒目，`font-semibold` 会让笔画糊成一团。
- 品牌文字标统一用 `brand-wordmark` 工具类（衬线 / 17px / 500 / -0.015em），侧栏、登录页、欢迎页顶栏共用；不要各自写 `text-sm font-semibold`，否则品牌位会退回普通后台观感。
- AI 输出区 `.prose-agent`：15px / 1.72，字体取 `--font-serif`；`h1` 20px、`h2` 18px、`h3/h4` 16px，字重 600；块内代码与行内代码显式回到 `--font-mono`。
- 数字（时间、用量、耗时）加 `tabular` 工具类，保证等宽对齐。
- 正文链接用墨色下划线，hover 才转陶土橙；不把橙色当常驻链接色。

## 6. 控件规范

### 6.1 高度阶梯

| 尺寸               | 高度 | 字号 | 圆角 | 用途                           |
| ------------------ | ---- | ---- | ---- | ------------------------------ |
| `xs` / `icon-xs`   | 23px | 12px | 6px  | 密集工具条、标签内操作         |
| `sm` / `icon-sm`   | 26px | 12px | 6px  | 次要按钮、图标按钮、会话行操作 |
| `default` / `icon` | 32px | 13px | 8px  | 常规按钮、输入框、下拉触发器   |
| `lg` / `icon-lg`   | 40px | 13px | 8px  | 登录页主操作、强调入口         |

- 水平内边距：`xs` 6px、`sm` 8px、`default` 12px、`lg` 16px；带图标时按方向减 4px。
- 图标默认 16px，`xs/sm` 内 12–14px，始终 `shrink-0`。

### 6.2 按钮状态

| 状态              | 表达                                               |
| ----------------- | -------------------------------------------------- |
| default           | `bg-primary`（墨色）或 `outline` + `bg-surface`    |
| hover             | 主按钮 `primary/90`；outline/ghost 用 `--muted` 底 |
| active / expanded | `aria-expanded` 时使用 `--muted`                   |
| focus-visible     | 2px `--ring` 环（陶土橙），`ring/35` 柔光          |
| disabled          | `opacity-45` + `pointer-events-none`               |
| loading           | 禁用交互，文案保持不变，避免按钮宽度跳动           |

### 6.3 输入与文本域

- 高度 32px，圆角 8px，边框 `--border`，聚焦切 `--ring`。
- 文本域最小高 88px（`5.5rem`），只允许纵向拉伸。
- 占位符用 `--muted-foreground`；错误态用 `--destructive` 边框 + 文案，不只靠颜色。

### 6.4 输入终端（Composer）

- 外框 20px 圆角，底色 `--surface`，三态阴影见 3.5。
- 文本区最小 44px、最大 208px，超出滚动；输入 15px / 1.6。
- 发送/停止按钮 32px 正圆，图标 16px；流式时切换为停止按钮，位置不移动。
- 底部提示 11px；字符计数仅在超过 80% 后出现，等宽数字。
- 左下角为「需求向导」入口（`sm` 尺寸 ghost 按钮，26px）：打开结构化需求面板，勾选条件后把组合好的描述写入输入框，不直接发送；面板内互斥组（预算、分辨率、品牌组合）只保留一个选项并标注「单选」，选项按钮沿用 `xs/sm` 的 6px 圆角。
- Enter 发送、Shift+Enter 换行；输入法组合态不发送。

### 6.5 消息

| 角色 | 规则                                                                       |
| ---- | -------------------------------------------------------------------------- |
| 用户 | 右对齐，最大宽 85%，12px 圆角 + 右下 4px，内边距 16×12，底色 `--secondary` |
| 助手 | 不做气泡，占满 720px 阅读宽度；顶部显示助手名与状态                        |
| 流式 | 末尾 2px 光标闪烁；同时通过 `aria-live="polite"` 播报                      |
| 失败 | 状态文字用 `--destructive`，提供重试；不隐藏原始内容                       |

消息之间默认 16px 间距；连续同角色可收紧到 4px（`--cds-message-bubble-stack-gap`）。

### 6.6 会话列表

- 侧栏默认模式的信息结构固定为：品牌位 → 新建对话 → 「最近」会话列表 → 用户菜单，不再有主导航。
- 「最近」标题行 26px，右侧箭头随状态切换：展开为 `ChevronDown`、折叠为 `ChevronRight`；标题按钮带 `aria-expanded` / `aria-controls`，折叠后列表区域让出高度。
- 会话行 32px，单行省略，选中用 `--accent`；行内不放左侧图标与时间，右侧改用「⋯」菜单按钮（26px）。该按钮默认 `opacity-0` 且不接收指针事件，仅在行悬浮、行内键盘聚焦时淡入；无 hover 能力的触屏设备常显。
- 「⋯」菜单项固定为：重命名、置顶、归档、删除。重命名与删除调用真实接口（重命名 1–80 字符，删除二次确认）；置顶与归档置灰并标注「暂未支持」。
- 置顶分组只靠分组标题表达状态，置顶行不再额外渲染 `Pin` 图标。
- 加载、错误、空三种状态都必须有明确文案与下一步动作；错误不显示原始堆栈，重试复用 `common.retry`。
- 删除当前会话后地址回退到 `/chat/new`；欢迎页复用只读行样式（无「⋯」菜单，保留时间）。

### 6.7 焦点与光标

- 全局 `:focus-visible`：2px 陶土橙描边，偏移 2px。
- 光标颜色 `caret-color: var(--cds-clay)`。
- 选中文本：陶土橙 26% 混色底。
- 滚动条宽 10px，滑块为前景色 18% 透明，悬停 30%。
- 页面级滚动容器固定声明 `scrollbar-gutter: stable both-edges`（居中的消息区与设置页），有边框的固定高度列表面板用 `stable`；否则滚动条出现瞬间占宽 10px，内容会横向位移并重新换行。

## 7. 信息架构与路由

| 路径               | 名称        | 布局             | 登录                  | 说明                                            |
| ------------------ | ----------- | ---------------- | --------------------- | ----------------------------------------------- |
| `/`                | `welcome`   | `blank-layout`   | 否                    | 产品入口：标题 + 输入终端 + 示例提示 + 最近会话 |
| `/welcome`         | —           | —                | —                     | 旧地址，`beforeLoad` 重定向到 `/`（非 HTTP 301） |
| `/login`           | `login`     | `blank-layout`   | 否（已登录回 `/chat/new`） | 登录                                            |
| `/chat/new`        | `chat-new`  | `default-layout` | 是                    | 创建会话后立即 `replace` 为 `/chat/:sessionId`  |
| `/chat/:sessionId` | `chat`      | `default-layout` | 是                    | 具体会话，隐藏于菜单                            |
| `/settings/:section` | `settings` | `default-layout`（设置模式） | 是 | 侧边栏切换为设置目录；缺省或非法分类 `replace` 到 `/settings/general` |
| `/403`             | `forbidden` | `default-layout` | 是                    | 无权限                                          |
| `*`                | `not-found` | `blank-layout`   | 否                    | 兜底，保留导航能力                              |

路由约定：

- 静态段必须先于动态段声明（`chat/new` 在 `chat/:sessionId` 之前）。
- 会话地址是唯一入口：前进/后退、点击列表、服务端返回新 `thread_id` 都通过同一处同步逻辑回写 URL。
- 页面内不重复判权；登录态与角色在全局守卫统一处理。

设置模式：

- 设置复用 `DefaultLayout`，不新增布局。设置路由下，`app-sidebar` 与移动抽屉把默认内容整体替换为设置目录（`src/features/settings/components/settings-nav.tsx`），返回对话通过目录顶部的返回入口完成。
- 右侧内容区只渲染当前分类组件，不再输出第二份目录。分类与选中态的唯一来源是路由参数 `section`，`resolveSettingsSection`（`src/features/settings/model/settings-sections.ts`）统一处理缺省值与非法值。
- `/settings` 与非法分类统一 `replace` 到 `/settings/general`；刷新、直接访问与前进/后退都落到同一份状态。
- 分类顺序固定：账户（个人资料、账户安全与登录、聊天与数据、已归档的聊天、存储、账单、模型与密钥、使用统计）在上，偏好设置（常规、外观、个性化）在下；已归档的聊天同时保留「聊天与数据」内的快捷块与独立分区。模型与密钥涉及账户级凭证，归在账户分组；使用统计聚合应用用量、Token 活动与模型调用明细，与模型与密钥只读分离。
- 折叠时设置目录退化为图标 rail，保留 `title` 与 `sr-only` 文本；窄屏由抽屉承担同一份目录。
- 表单草稿保存在 `useSettingsDraftStore` 内存中，切换分类不丢失；资料、安全、个性化、模型与密钥提交到服务端（失败回滚到服务端确认值），常规、外观、聊天与数据仍是本地草稿，内容区顶部常驻说明。
- 模型与密钥分区：分区内三态钻取（已接入供应商列表 → 选择供应商 → 供应商详情）。Provider 展示名与 logo 由本地品牌表补齐（`frontend/public/logo/`），未知 Provider 回退首字母；添加视图里已接入项禁用并标注状态。详情展示凭证掩码、连接状态、接入地址与目录模型（固定高度滚动）；模型用量面板已移至「使用统计」分区。Provider 选项来自模型目录；接入地址留空时后端回落到 Provider 默认地址，自定义 Provider 必须填写，否则创建返回 400。校验按钮触发真实上游探测，成功后状态变为「已验证」。

## 8. 响应式与内容密度

- 内容宽度 720px 是阅读基准；欢迎页允许 736px（46rem）以容纳示例卡片的两列，属于已登记偏差。
- 页面纵向：移动端 `py-8`，桌面 `py-12`；欢迎页顶部用 `clamp(3rem, 12vh, 7rem)` 保持留白弹性。
- 卡片/面板内边距 14–16px；列表行 32px；区块间距 24–32px。
- 移动端只保留一个抽屉入口；抽屉内提供新建对话、会话与账户，避免多层抽屉。设置模式下抽屉改为设置目录。
- 设置模式沿用侧边栏宽度、折叠与拖拽；右侧内容最大宽度 720px，窄屏只显示内容，分类通过抽屉访问，不再出现横向分类胶囊。
- 桌面侧边栏可拖拽 220–`min(420px, 40vw)`；窗口缩放时重新夹取实际宽度，不覆盖用户保存的偏好。
- 平板（768–1024px）侧边栏与内容同时存在时，上限随视口收缩（1024→409、768→307），不出现横向溢出。
- `<768px` 不渲染拖拽条，只保留抽屉导航；不允许为了拖拽而压缩主内容。
- 所有页面必须通过 390×844 无横向溢出检查（`documentElement.scrollWidth === clientWidth`）。

## 9. 无障碍基线

- 图标按钮必须有 `aria-label`；纯装饰图标 `aria-hidden`。
- 流式回复用 `sr-only` + `aria-live="polite"` 播报开始/完成状态，不逐字播报内容。
- 抽屉/对话框：`role="dialog"` + `aria-modal="true"` + 可读 `aria-label`，Esc 可关闭。
- 键盘可达：焦点顺序按视觉顺序；抽屉打开后焦点进入关闭按钮（关闭后自动归还触发按钮尚未实现，属待补项）。
- 侧边栏分隔条：`role="separator"` + `aria-orientation="vertical"` + `aria-valuenow/min/max/valuetext`，`tabindex="0"`，ArrowLeft / ArrowRight 调整、Shift 大步长；聚焦时 2px 陶土橙描边。
- 折叠与展开按钮必须有 `aria-label`；折叠后焦点转移到展开按钮，避免焦点落回 body。
- 对比度：正文与主按钮按 WCAG AA；状态色不单独承载信息，必须配文字或图标。
- 尊重 `prefers-reduced-motion`：动画降至 0.001ms，流式光标改为静态 70% 透明度。

## 10. 主题切换

- 模式：`light` / `dark` / `system`，持久化键 `app-state`，字段 `theme`。
- 切换通过根节点 `.dark` 类完成；`color-scheme` 同步设置，保证原生控件与滚动条正确。
- `index.html` 首屏内联脚本在框架加载前读取 `app-state` 并打上 `.dark`，避免闪白（FOUC）。
- 切换时以触发位置为圆心做 300ms 圆形扩散（View Transitions + WAAPI 驱动 `clip-path`）；浏览器不支持或 `prefers-reduced-motion: reduce` 时直接切换，不做动画；解析结果与当前一致时不触发。圆心取触发元素的点击坐标，键盘操作回退到元素中心。
- 品牌陶土橙在两种模式下不变；主按钮通过 `--cds-text-primary` 自动反相。
- 设置页「外观」分区使用三张主题预览卡：指针悬浮或键盘聚焦时该卡放大到 1.6 倍、其余卡压暗并轻微虚化；指针移开或完成选择后立即退出预览态，选中卡保持同样的 1.6 倍宽度；浅色 / 深色 / 跟随系统分别用固定灰度 Token 绘制的微缩界面表达，不依赖图片资源；原生 radio 保留方向键与读屏语义，`prefers-reduced-motion` 下取消过渡。

## 11. 实现映射

| 文件                                                  | 职责                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `frontend/src/styles/cds-theme.css`                   | `--cds-*` Token 事实源，不新增语义层                     |
| `frontend/src/styles/main.css`                        | 语义映射、几何 Token、排版刻度、`.prose-agent`、光标与滚动条 |
| `frontend/src/shared/ui/button.tsx`                   | 按钮尺寸与圆角阶梯（cva variants）                           |
| `frontend/src/shared/ui/input.tsx`                    | 32px 输入框                                                  |
| `frontend/src/shared/ui/textarea.tsx`                 | 文本域圆角与最小高                                           |
| `frontend/src/app/layouts/DefaultLayout.tsx`          | 外壳：侧边栏 + 窄屏悬浮入口 + 抽屉 + 内容                    |
| `frontend/src/app/layouts/components/app-sidebar.tsx` | 288/56px 侧边栏；品牌位（折叠态悬浮/聚焦切换为展开入口）、新建对话、「最近」会话列表与用户菜单；宽度编排与折叠提交 |
| `frontend/src/features/settings/components/settings-nav.tsx` | 设置模式目录：分组、选中态、返回对话、折叠 rail 图标与标题 |
| `frontend/src/features/settings/components/theme-mode-selector.tsx` | 外观分区主题预览卡：悬浮 / 聚焦放大、其余压暗、原生 radio 语义 |
| `frontend/src/features/settings/components/theme-preview-art.tsx` | Token 绘制的浅色 / 深色微缩界面，system 左右拼接 |
| `frontend/src/features/settings/model/settings-sections.ts`  | 设置分类顺序、图标、默认分类与路由参数解析（纯函数，含单测） |
| `frontend/src/app/layouts/components/sidebar-resizer.tsx`    | 6px 拖拽分隔条：Pointer Events、rAF、折叠预览、键盘与清理    |
| `frontend/src/app/layouts/lib/sidebar.ts`                    | 宽度夹取、视口上限、拖拽提交规则（纯函数，含单测）            |
| `frontend/src/app/stores/app-store.ts`                       | `sidebarWidth` / `isSidebarCollapsed` 持久化到 `app-state`   |
| `frontend/src/app/layouts/components/mobile-nav.tsx`  | 移动抽屉，复用同一信息结构；设置模式下切换为设置目录 |
| `frontend/src/routes/pages/settings-page.tsx`         | 设置内容壳：按 URL 规范化分区，只渲染当前分类组件 |
| `frontend/src/features/settings/components/sections/*.tsx` | 十一类设置分区（agent / appearance / archived-chats / billing / chats / general / model / profile / security / storage / usage）；资料、安全、个性化、模型与密钥已接服务端，其余为占位说明；使用统计上段为指标条 + Token 活动日历，下段复用模型用量面板 |
| `frontend/src/features/settings/model/settings-draft.ts` | 设置页本地草稿，切换分类保留未提交内容 |
| `frontend/src/features/settings/api/preferences.ts`   | Agent 偏好读写（Query 为唯一事实源），保存失败回滚到服务端确认值 |
| `frontend/src/app/layouts/components/user-menu.tsx`   | 用户入口与下拉菜单（个人资料、设置、登录或退出） |
| `frontend/src/features/chat/components/chat-composer.tsx` | 20px 输入终端与三态阴影                                      |
| `frontend/src/features/chat/components/message-item.tsx`  | 气泡规则与状态                                               |
| `frontend/src/features/sessions/components/session-list.tsx` | 会话列表四态（加载 / 错误 / 空 / 列表）；侧栏开启「⋯」菜单与选中高亮 |
| `frontend/src/routes/pages/welcome-page.tsx`          | 根路径产品入口                                               |
| `frontend/src/routes/paths.ts`                        | 路由路径常量（页面引用，不写字面量）                           |

新增 UI 的落地顺序：

1. 先查本文件与 `main.css`，确认是否有现成 Token / 语义类。
2. 需要新值时，先加 Token，再写组件；组件内不出现裸 `px` 高度、裸 `hex`、裸圆角。
3. 同步补 `zh-CN` / `en-US` 文案，不在模板里写死中文。
4. 覆盖 default / hover / focus / disabled / loading / empty / error 状态。
5. 跑质量门禁并做浏览器矩阵检查（见第 12 节）。

## 12. 验证清单

提交前必须全部通过：

```powershell
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test
corepack pnpm --dir frontend build
```

命令语义以 `frontend/package.json` 的 `scripts` 为准；`lint` 带 `--fix` 会改写源码，只检查用 `lint:ci`。

浏览器矩阵（Chrome，至少覆盖）：

| 场景       | 视口                | 检查点                                                                                     |
| ---------- | ------------------- | ------------------------------------------------------------------------------------------ |
| 桌面浅色   | 1440×900            | 侧边栏 288、内容 720、无第二侧栏                                                           |
| 桌面深色   | 1440×900            | 表面 0–3 可区分、主按钮反相正确                                                            |
| 折叠       | 1440×900            | 侧边栏 56px、品牌图标悬浮/聚焦显示展开图标并可点击展开、工具区贴底、图标有 tooltip/aria |
| 侧边栏拖拽 | 1440×900            | 288→360 主区同步 1080、无横向溢出、仅一个分隔条                                            |
| 折叠阈值   | 1440×900            | 拖到 195px 未松开即折叠为 56px、指针捕获与监听已清理；释放不重新展开；215px 释放吸附回 220 |
| 折叠态边界 | 1440×900            | `role="button"`、`cursor: pointer`、单击展开并恢复上次宽度；Enter/Space 同样可展开         |
| 导航文本   | 1440×900            | 持续左拖到 205/215px 时 New Chat 与「最近」标题行均保持单行，高度 32 / 26px                 |
| 重新展开   | 1440×900            | 恢复上次宽度、分隔条恢复、无布局跳动                                                       |
| 键盘       | 1440×900            | ArrowLeft 16px、Shift 48px、连续左移触发折叠                                               |
| 平板       | 768×1024 / 1024×768 | 上限 307 / 409，无横向溢出                                                                 |
| 移动       | 390×844             | 无横向溢出、输入区不被安全区遮挡、抽屉单层                                                 |
| 设置模式   | 1440×900            | 侧边栏为设置目录、右侧只有当前分类内容、开关可见、折叠 rail 有 title                       |
| 设置路由   | 1440×900            | 直接访问 `/settings/appearance`、刷新与前进/后退后分类和选中态一致                        |
| 设置窄屏   | 768×1024 / 390×844  | 768 无横向溢出；390 抽屉内为设置目录，切换分类后抽屉自动关闭                              |
| 交互       | —                   | 示例提示填入、`/chat/new` 重定向、会话切换 URL 同步、访客不报错                            |

验收数据要留痕：DOM 尺寸、`scrollWidth/clientWidth`、控制台错误为 0。

## 13. 已知偏差与待决事项

| 项                 | 现状                                              | 处理                                               |
| ------------------ | ------------------------------------------------- | -------------------------------------------------- |
| 品牌名             | `VITE_APP_TITLE` 默认值已统一为 `Agent`（`.env.example` 与 `src/shared/lib/env.ts`） | 产品定名后只改环境变量与文案 |
| 移动端顶栏         | 已移除全局顶栏与对话页标题栏，仅保留左上角悬浮抽屉入口 | 页面用窄屏顶部内边距避让按钮；对话页保留 sr-only `h1` |
| 登录态会话列表     | 仅完成结构与类型验证，未用真实账号联调            | 联调阶段补真实会话回归                             |
| 受保护路由         | 登录态与角色由 `src/routes/guards.ts` 统一处理（TanStack Router `beforeLoad`） | 已完成；未登录访问业务页统一跳 `/login?redirect=...` |
| 欢迎页内容宽 736px | 比 720px 基准宽 16px                              | 为容纳示例卡片两列，已登记；新页面仍用 720px       |
| 设置页未接后端     | 常规、外观、聊天与数据仍只写内存草稿；已归档的聊天、存储、账单为占位；资料、安全、个性化与模型与密钥已接服务端；使用统计的指标与 Token 活动暂无汇总接口，显示空态占位 | 剩余分类与用量汇总待接口补齐 |

## 14. 变更记录

| 轮次   | 内容                                                                                                                                                                                |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 第一轮 | 全量迁移到 CDS 颜色与表面 Token，清理旧配色；引入 `.prose-agent` 排版、主题切换与首屏脚本                                                                                           |
| 第二轮 | 尺寸与控件阶梯落地（23/26/32/40、6/8px 圆角）；布局几何 Token 化；补齐欢迎页、历史页与 `/chat/new` 路由；会话列表并入单侧边栏；移动抽屉合并；补齐访客态与错误态；完成浏览器矩阵验收 |
| 第三轮 | 侧边栏可拖拽：6px 分隔条、220–`min(420px,40vw)`、168px 阈值折叠与吸附、宽度记忆 `sidebarWidth`、键盘与 ARIA、拖动/折叠动画与 reduced-motion；CDP 真实浏览器 64 项检查全部通过       |
| 第四轮 | 阈值提高到 200px（201–219 吸附到 220，消除过度收窄区间）；折叠态边界改为点击展开入口；New Chat 文本 `truncate` 不再换行；CDP 81 项检查全部通过                                      |
| 第五轮 | 拖拽中达到 200px 即折叠（不再等待释放），复用同一清理路径；移除失效的折叠预览；拖动结束的合成 click 抑制到下次按下；CDP 91 项检查全部通过                                           |
| 第六轮 | 设置界面改为壳层模式：设置路由接管全局侧边栏与移动抽屉，右侧只渲染当前分类；分类配置迁至 `config/settings.ts`（**历史路径**，迁移后为 `frontend/src/features/settings/model/settings-sections.ts`）；`/settings` 规范回落到 `/settings/general`；修复 `Switch` 轨道与滑块的 `data-state` 视觉；CDP 26 项检查全部通过 |
| 第七轮 | 新增「模型与密钥」设置分区（BYOK）；模型选择器事件对齐 `update:modelValue`；目录 `contextWindow` 允许为空；补模型 API 与设置分区单测。**历史信息**：本轮处于 Vue 期，`vitest.config.ts` 当时接入 Vue 插件以支持组件测试；2026-11-01 迁移到 React 后 Vue 依赖已全部移除，当前单测配置见 `frontend/vitest.config.ts`（`@vitejs/plugin-react` + happy-dom），本条仅作历史记录，不作为当前规范 |
| 第八轮 | 移除全局顶栏与对话页标题栏，窄屏改用左上角悬浮抽屉入口；侧边栏恢复折叠宽度过渡并移除主题/语言切换；新建对话改为低对比 ghost 样式；模型目录改走 `/api/v2` 基址；设置页移除本地提示、账户信息与修改密码表单 |
| 第九轮 | 会话行移除左侧图标与时间，右侧改为「⋯」菜单（重命名 / 置顶 / 归档 / 删除，后两项标注暂未支持）；列表标题改为「最近」并支持折叠箭头；删除 `/home` 与 `/history` 页面、路由、入口与文案；折叠态移除底部展开按钮，改为品牌图标悬浮/聚焦切换为展开按钮 |
| 第十轮 | 设置页外观分区改为主题预览卡：悬浮 / 聚焦放大、其余卡压暗虚化，CSS 微缩界面表达浅色 / 深色 / 跟随系统，保留原生 radio 语义与减少动效适配；完成选择后立即退出预览态，悬浮与选中统一为 1.6 倍宽度 |
| 第十一轮 | 设置页精简：外观移除「减少动效」「显示助手头像」，常规移除「默认页面」「发送快捷键」；新增「已归档的聊天」「存储」「账单」三个占位分区（已归档同时保留「聊天与数据」快捷块）；「Agent 个性化」更名为「个性化」 |
| 第十二轮 | 输入区移除「Enter 发送 · Shift + Enter 换行」提示；账户菜单移除「个人资料」入口；账户安全移除「登录方式」卡片，登录设备改为固定高度列表（一次取满 100 台，超出滚动，撤销后不再分页回退）；外观移除「聊天显示密度」；「模型与密钥」从偏好设置移到账户分组 |
| 第十三轮 | 「模型与密钥」重构为分区内三态钻取：供应商列表（行式面板 + 状态徽标 + 掩码）、添加供应商（品牌网格，已接入项禁用）、供应商详情（凭证事实 + 验证/删除 + 目录模型固定高度滚动）；接入表单移除 Provider 下拉，改由所选供应商固定传入；新增本地 Provider 品牌表复用 `public/logo`，未知厂商回退首字母；用量面板保留在默认视图底部 |
| 第十四轮 | 新增「使用统计」分区（账户分组）：上段为五项用量指标条 + Token 活动日历（`react-activity-calendar`，空态骨架，指标接口未接入时显示「—」），下段承载从「模型与密钥」移出的模型用量面板；用量面板移除开始/结束日期与查询按钮，表格删除延迟、状态与费用三列，仅保留时间、模型、来源与 Token |
| 第十五轮 | 侧边栏字号上浮：新增 `text-nav`（14px）用于新建对话、会话标题、设置导航与账户行，行高改为独立 token 36px；「最近」/设置分组标题、会话时间戳由 11px 任意值收回 `text-xs`（12px）；移动抽屉同步该口径 |
| 第十六轮 | 登录页表单修复：用 inset 阴影覆盖浏览器自动填充注入的浅蓝底色并保留焦点环；密码掩码态固定系统字体，消除首屏圆点字距突变（U+2022 在 Noto Sans SC 为全角、Anthropic Sans 为 0.5em）；移除左栏底部「仅限授权账号使用」文案，栏内改为顶部品牌标识 + 垂直居中说明 |
| 第十七轮 | 侧边栏会话行的「⋯」菜单改为悬浮/键盘聚焦才显示（触屏常显）；置顶行移除 `Pin` 图标，仅保留分组标题；账户入口绑定真实资料接口，展示昵称（回退登录账号）与邮箱，未登录不发请求 |
| 第十八轮 | 空会话态用两行网格：标题块（品牌标 + 衬线主标题）跨两行居中，视觉重心落在整个对话区；「为你推荐」固定在第二行、紧贴输入框上方并与输入框同宽对齐；示例为 32px 高、8px 圆角、常规字重按钮；输入框左下角新增「需求向导」结构化需求面板（预算 / 用途 / 性能侧重 / 分辨率 / 品牌 / 存储 / 外观散热 / 连接接口 / 附加需求），确认后把描述写入输入框而不直接发送 |
