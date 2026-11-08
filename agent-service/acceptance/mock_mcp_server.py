"""本地远程 MCP Server（Streamable HTTP），用于验证接入与「挂掉不影响主流程」。

启动：`uv --directory agent-service run python -m acceptance.mock_mcp_server`。
"""

from mcp.server.fastmcp import FastMCP

HOST = "127.0.0.1"
PORT = 9100

mcp = FastMCP("acceptance", host=HOST, port=PORT)


@mcp.tool()
def echo(text: str) -> str:
    """回显文本；用于确认 MCP 工具已被发现并调用。"""
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
