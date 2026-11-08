"""输出审核钩子：模型输出命中验收暗号时阻断本轮。

启用方式：`AGENT__HOOKS_MODULES=acceptance.hooks`。
"""

from app.agent.hooks import HookBlockedError, HookContext, HookPoint, register_hook

CANARY = "审核演示"


@register_hook(
    HookPoint.AFTER_MODEL,
    priority=10,
    blocking=True,
    name="acceptance.output_guard",
)
async def guard_output(context: HookContext) -> None:
    """阻断命中暗号的输出；提示文案对用户安全，不包含规则细节。"""
    if CANARY in (context.text or ""):
        raise HookBlockedError("输出命中验收审核规则")
