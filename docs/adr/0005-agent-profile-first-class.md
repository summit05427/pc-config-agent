# Agent Profile 是模板的一等扩展点

模板接入方需要在一个进程内运行多个不同人格、工具集与模型参数的 Agent。我们选择把 Agent Profile（YAML：提示词 + 工具集 + 模型参数 + 上下文预算）建成一等概念，由请求级 `agent_id` 选择，缺省 `default`。没有这一层时，唯一的区分手段是部署多份服务，模板会退化成"一次性脚手架"。

## Consequences

- `ChatRequest` 新增可选 `agent_id`，不传时等价于 `default`，保证向后兼容；
- ChatModel 与 LangGraph 的缓存键必须包含 `agent_id`，否则同模型不同 Profile 会串扰；
- Profile 在启动期校验（提示词存在、工具已注册、参数范围），非法配置直接拒绝启动；
- 第一版只做请求级选择，会话级默认留到后续，避免数据库迁移与前端改动阻塞。
