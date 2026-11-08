# 前端 UI 速查

| 项 | 内容 |
| --- | --- |
| 源文件 | `docs/services/frontend/ui-design-system.md` |
| 性质 | 派生速查（权威以源文件为准，冲突时以源文件为准） |
| 核对日期 | 2026-11-03 |

## 颜色变量
| 语义变量（Token） | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| `--canvas` / `--sidebar`（`--cds-surface-0`） | `#f9f9f7` | `#0b0b0b` | 侧边栏、抽屉、底层画布 |
| `--background`（`--cds-surface-1`） | `#fcfcfb` | `#151515` | 主工作区、页面背景 |
| `--surface` / `--card`（`--cds-surface-2`） | `#ffffff` | `#1a1a19` | 消息卡片、面板、输入容器 |
| `--surface-raised`（`--cds-surface-3`） | `#ffffff` | `#20201f` | 输入框、高层浮层、悬停抬升面 |
| `--popover`（`--cds-surface-popover`） | `#ffffff` | `#2c2c2a` | 下拉菜单、Popover |
| `--foreground` | `#151515` | `#f5f5f5` | 正文、标题、主按钮底色 |
| `--muted-foreground` | `#525252` | `#a3a3a3` | 辅助说明、时间、占位符 |
| `--cds-text-muted` | `#8a8a8a` | `#666666` | 极弱信息（仅装饰性标签） |
| `--border` | `hsla(0,0%,8%,.10)` | `hsla(0,0%,100%,.09)` | 常规发丝线、分隔、输入边框 |
| `--border-strong` | `hsla(0,0%,8%,.20)` | `hsla(0,0%,100%,.18)` | 悬停/聚焦边框、强调分隔 |
| `--cds-clay`（陶土橙） | `#d97757` | `#d97757` | 徽标、焦点环、运行指示、图表首色 |
| 陶土悬停 / 陶土浅底 | `#cc5a36` / `#fbf3ef` | `#e08264` / 不适用（仅浅色模式） | 品牌元素 hover / 极浅品牌底 |
| `--primary` | `--cds-text-primary` | 自动反相 | 墨色主按钮 |
| `--secondary` | `--cds-bg-user-message` | 同浅色 | 用户气泡底色 |
| `--accent` | `--cds-fill-ghost-selected` | 同浅色 | 选中态（导航、会话行） |
| `--destructive` | `#dc2626` | `--cds-fill-danger` | 危险操作（取色阶 600 满足 AA） |
| `--success` | `#047857` | `#34d399` | 成功、复制完成 |
| `--warning` | `--cds-orange-500` | `--cds-orange-250` | 警告 |
| `--info` | `--cds-blue-450` | `#5b9fe3` | 信息 |
## 圆角阶梯
| Token | 值 | 用途 |
| --- | --- | --- |
| `--radius-xs` | 2px | 标签内角、极小元素 |
| `--radius-sm` | 4px | 行内代码、骨架 |
| `--radius-md`（`--cds-radius-btn-xs`） | 6px | `xs` / `sm` 按钮 |
| `--radius-lg`（`--cds-radius-btn-md`） | 8px | 默认按钮、输入框、卡片 |
| `--cds-panel-radius` | 10px | 示例卡片、会话空状态、提示面板 |
| `--radius-xl`（`--cds-radius-code`） | 12px | 消息气泡、代码块；用户气泡右下角收为 4px |
| `--cds-radius-dialog` | 16px | 对话框 |
| `--cds-radius-composer` | 20px | 输入终端 |
| `--radius-3xl` | 24px | 大容器 |
| `--cds-radius-pill` | 9999px | 头像、圆形图标按钮 |
## 间距与几何
| 项 | 值 | 说明 |
| --- | --- | --- |
| `--app-sidebar-width` | 288px（18rem） | 桌面展开侧边栏 |
| `--app-sidebar-rail-width` | 56px（3.5rem） | 折叠侧边栏 |
| `--app-titlebar-height` | 48px（3rem） | 侧边栏品牌行 |
| `--app-content-width` | 720px（45rem） | 对话页阅读宽度；欢迎页例外 736px |
| `--app-gutter-x` | 32px（2rem） | 桌面页面沟槽；移动端 16px |
| 移动抽屉宽度 | `min(288px, 85vw)` | 窄屏仍露出可点击遮罩 |
| 高度基准 | `100dvh` | `@supports` 降级到 `100vh` |
| 卡片/面板内边距 | 14–16px | 面板内容留白 |
| 列表行高 | 32px | 会话行、列表行 |
| 区块间距 | 24–32px | 区块之间 |
| 消息间距 | 16px | 连续同角色可收紧到 4px |
| 文本域最小高 / Composer 文本区 | 88px / 44–208px | 文本域只允许纵向拉伸；Composer 超出滚动 |
| 侧边栏导航行高 | 36px | `--app-sidebar-row-height` |
| 通用间距刻度 | 源文件未定义 | 源文件只给出上列离散值，无统一间距阶梯 |
## 控件高度阶梯
| 尺寸 | 高度 | 字号 | 圆角 | 用途 |
| --- | --- | --- | --- | --- |
| `xs` / `icon-xs` | 23px | 12px | 6px | 密集工具条、标签内操作 |
| `sm` / `icon-sm` | 26px | 12px | 6px | 次要按钮、图标按钮、会话行操作 |
| `default` / `icon` | 32px | 13px | 8px | 常规按钮、输入框、下拉触发器 |
| `lg` / `icon-lg` | 40px | 13px | 8px | 登录页主操作、强调入口 |
## 字号刻度
| Token | 字号 | 行高 | 典型用途 |
| --- | --- | --- | --- |
| `text-xs` | 12px | 1.5 | 时间、辅助标签、计数 |
| `text-sm` | 13px | 1.55 | 次要正文、按钮小号、表单说明 |
| `text-nav` | 14px | 1.5 | 侧边栏导航、会话标题、账户行 |
| `text-base` | 15px | 1.65 | 正文、消息、输入框 |
| `text-lg` | 17px | 1.55 | 区块标题 |
| `text-xl` | 20px | 1.4 | 页面标题（移动） |
| `text-2xl` | 24px | 1.3 | 页面标题 |
| `text-3xl` | 30px | 1.2 | 大标题备用 |
## 组件状态（按钮）
| 状态 | 表达 |
| --- | --- |
| default | `bg-primary`（墨色）或 `outline` + `bg-surface` |
| hover | 主按钮 `primary/90`；outline / ghost 用 `--muted` 底 |
| active / expanded | `aria-expanded` 时使用 `--muted` |
| focus-visible | 2px `--ring` 环（陶土橙），`ring/35` 柔光 |
| disabled | `opacity-45` + `pointer-events-none` |
| loading | 禁用交互，文案保持不变以避免宽度跳动 |
| 非按钮组件状态 | 源文件未定义（仅输入框、文本域、消息有零散状态描述，无完整状态矩阵） |
## 响应式断点
| 视口 | 侧边栏 | 导航入口 | 会话入口 |
| --- | --- | --- | --- |
| `<768px` | 隐藏 | 左上角悬浮按钮 → 抽屉 | 同一抽屉内的会话区 |
| `≥768px` | 常驻，可拖拽 220–`min(420px, 40vw)`，可折叠到 56px | 侧边栏品牌位 + 新建对话 | 侧边栏「最近」会话列表 |
| 欢迎页 / 登录页 | 无侧边栏 | 页内顶栏 | 页内入口 |
