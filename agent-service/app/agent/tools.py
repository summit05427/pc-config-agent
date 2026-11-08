"""内置工具集。

工具 = 普通 Python 函数 + 名称 + 描述 + 参数结构。
模型只能看到「名称 + 描述 + 参数 schema」，靠这些决定要不要调用、传什么参数，
所以描述必须写清楚"什么时候用、参数是什么"。

新增工具不需要改这里：放到 `app/agent/tools_ext/`，或通过 `AGENT__TOOL_MODULES`
声明额外的模块路径，启动时会自动注册。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent.registry import register_tool


@register_tool(
    name="get_current_time",
    description=(
        "获取指定时区的当前时间。\n\n"
        "当用户询问“现在几点”“今天几号”等与当前时间相关的问题时使用。\n"
        "timezone 使用 IANA 时区名，例如 Asia/Shanghai、America/New_York。"
    ),
    timeout_seconds=5.0,
    max_retries=0,
)
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """返回格式化后的当前时间；非法时区返回提示文本，不抛异常给模型。"""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return f"无法识别的时区：{timezone}"
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
