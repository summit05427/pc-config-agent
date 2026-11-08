"""阶段 3 实机联调验收夹具（非产品代码）。

包含四类可重复使用的验收资产：

- `hooks.py`：输出审核钩子（`AGENT__HOOKS_MODULES=acceptance.hooks`）；
- `retriever.py`：内存检索器（`RAG__RETRIEVER_MODULE=acceptance.retriever`）；
- `mock_mcp_server.py`：本地远程 MCP Server（Streamable HTTP，127.0.0.1:9100）。
  MCP 只支持网关拓扑，验收时先在 `deploy/litellm/config.yaml` 的 `mcp_servers`
  注册它，再设置 `MCP__ENABLED=true`，Agent 通过网关聚合端点访问。

本包不参与运行时装配，只有显式配置对应环境变量时才会被导入。
"""
