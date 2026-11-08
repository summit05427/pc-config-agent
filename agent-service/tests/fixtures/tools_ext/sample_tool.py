"""WP1.1 验收用外部工具样例。

放在 `tests/fixtures/tools_ext/` 而不是 `app/`，用于证明：
新增工具只需新增一个模块，不改核心代码即可被注册表发现。
"""

from app.agent.registry import register_tool


@register_tool(
    name="sample_echo",
    description="原样返回输入文本；仅用于验证外部工具模块的自动发现。",
    timeout_seconds=3.0,
    max_retries=0,
    source="ext",
)
def sample_echo(text: str) -> str:
    return f"echo: {text}"
