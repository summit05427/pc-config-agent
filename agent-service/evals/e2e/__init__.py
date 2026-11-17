"""HTTP/SSE 端到端评测。

与 `evals/runners/real_model.py` 的区别：后者在进程内直接调用图节点，只验证
「图跑得对不对」；这里经过真实的 FastAPI 路由、SSE 编码与会话落库，验证
「客户端看到的事件流与落库结果对不对」。

两种模式：
- `local`：进程内 ASGI + 确定性假图，零费用，用于 CI 契约门禁；
- `service`：真实登录 + 真实 HTTP/SSE，用于人工单例验收。

入口：`python -m evals.e2e --mode local|service`。
"""
