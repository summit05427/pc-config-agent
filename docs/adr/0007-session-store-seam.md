# 会话读写收口到单一 SessionStore seam

会话目录 `session_meta` 与消息转写 `session_messages` 共用同一个连接池、同一个 `(user_id, thread_id)` 键，并有三条跨表不变量：本轮消息与活跃时间一起写、删除两表一起删、标题只首写一次。此前它们分散在两个模块里，每个函数内部各有一份 `if _pool is None` 的内存/Postgres 分支，后端选择与归属规则重复了两遍。我们选择把两张表收进一个 `SessionStore` 接口，内存与 Postgres 作为两个适配器，只在应用启动时绑定一次。

## Consequences

- 调用方只跨 `get_session_store()` 一个 seam；`setup / detach / reset` 从 6 个函数缩为 1 组绑定与解绑；
- `record_turn` 与 `delete_session` 在 Postgres 适配器内使用单事务，内存适配器天然原子；
- 三张表的归属校验统一为 `(user_id, thread_id)`，按用户隔离不再依赖调用方自觉；
- 内存适配器接收注入时钟，测试不再 monkeypatch 模块级 `_now`；
- 同一套契约测试参数化跑内存与 Postgres，Postgres 未配置时自动跳过；
- 生产环境未绑定 store 视为装配错误；非 prod 回退内存适配器，避免单元测试依赖真实数据库。

## 不并入的部分

删除墓碑 `session_deletion_tasks` 与用量 `usage_outbox` 保持独立。前者是带租约、退避与后台循环的调度器，后者是允许降级丢弃的旁路上报；它们的失败模型与生命周期和「读写会话」不同，合并会让接口重新变宽。将来若要深化这两个模块，应按「队列 + worker」的方式各自拆分，而不是并进 `SessionStore`。
